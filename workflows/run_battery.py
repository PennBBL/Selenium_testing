"""
Battery workflow.

Behavior:
- Reads exact p.test-name from each test landing page.
- Dispatches to the correct plugin based on exact test code.
- If the test is unknown, logs it as FAIL, saves artifacts, presses Ctrl + .,
  and continues the battery if possible.
- After a known test completes, does NOT wait 60 seconds for a battery choice page.
  Instead, it briefly checks for:
    1. inter-test go.png link
    2. direct next p.test-name landing page
    3. otherwise treats the battery as complete
- When the battery is complete, waits 5 seconds before returning to runner.
"""

import time
from typing import Any

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from pages.test_landing_page import TestLandingPage
from tests_catalog.registry import TEST_REGISTRY, DEFAULT_STRATEGIES


UNKNOWN_TEST_STATUS = "FAIL"
UNKNOWN_TEST_ERROR = "Unknown test code; skipped with Ctrl+."

GO_LINK = (By.XPATH, "//a[.//img[contains(@src, 'go.png')]]")
QUIT_LINK = (By.XPATH, "//a[contains(@href, 'op=Quit') or .//img[contains(@src, 'stop.png')]]")
NEXT_TEST_TEXT = (By.XPATH, "//p[contains(normalize-space(.), 'Next test:')]")
TEST_NAME = (By.CSS_SELECTOR, "p.test-name")


def _safe_find(ctx, locator):
    try:
        return ctx.driver.find_elements(*locator)
    except WebDriverException:
        return []


def _page_has_go(ctx) -> bool:
    return bool(_safe_find(ctx, GO_LINK))


def _page_has_quit(ctx) -> bool:
    return bool(_safe_find(ctx, QUIT_LINK))


def _page_has_next_test_text(ctx) -> bool:
    return bool(_safe_find(ctx, NEXT_TEST_TEXT))


def _page_has_test_landing(ctx) -> bool:
    return bool(_safe_find(ctx, TEST_NAME))


def _click_go(ctx) -> None:
    els = _safe_find(ctx, GO_LINK)
    if not els:
        raise TimeoutException("Could not find battery go.png link.")
    ctx.driver.execute_script("arguments[0].click();", els[0])
    time.sleep(2)


def _get_next_test_label(ctx) -> str | None:
    els = _safe_find(ctx, NEXT_TEST_TEXT)
    if not els:
        return None
    text = els[0].text.strip()
    if "Next test:" in text:
        return text.split("Next test:", 1)[1].strip()
    return text


def _send_ctrl_period(ctx) -> None:
    """Send the platform shortcut for skipping a test: Ctrl + ."""
    ctx.logger.info("Sending skip shortcut: Ctrl + .")
    ActionChains(ctx.driver).key_down(Keys.CONTROL).send_keys(".").key_up(Keys.CONTROL).perform()
    time.sleep(1)


def _record_failed_test(ctx, exact_code: str, errors: list[str]) -> dict[str, Any]:
    """Record an unknown skipped test as failed, but do not scrape it."""
    record = {
        "test_name": exact_code,
        "status": UNKNOWN_TEST_STATUS,
        "errors": errors,
        "skipped": True,
        "skip_method": "ctrl_period",
        "scrape": False,
    }
    ctx.completed_tests.append(record)
    ctx.registry.mark_test_completed(ctx.subid, exact_code, UNKNOWN_TEST_STATUS, errors)
    return record


def _record_completed_test(ctx, exact_code: str, result) -> dict[str, Any]:
    """Record a known administered test."""
    record = {
        "test_name": exact_code,
        "status": result.status,
        "errors": result.errors,
        "skipped": False,
        "skip_method": None,
        "scrape": True,
    }
    ctx.completed_tests.append(record)
    ctx.registry.mark_test_completed(ctx.subid, exact_code, result.status, result.errors)
    return record


def _wait_for_landing_or_go_or_final(ctx, timeout: int = 8) -> str:
    """
    Inspect the current page after a test ends or after Ctrl+. Returns:

    "go"       -> battery inter-test page has go.png
    "landing"  -> next p.test-name landing page is already present
    "final"    -> no next controls appeared within timeout
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        if _page_has_go(ctx):
            return "go"

        if _page_has_test_landing(ctx):
            return "landing"

        # The final page may have no go/quit/buttons. Do not immediately call it final;
        # give the platform a few seconds to finish navigation.
        time.sleep(0.5)

    return "final"


def _finish_battery(ctx) -> None:
    """Mark battery complete and wait 5 seconds before returning to runner."""
    ctx.logger.info("Battery appears complete.")
    ctx.registry.mark_battery_completed(ctx.subid)
    ctx.logger.info("Waiting 5 seconds before returning to runner.")
    time.sleep(5)


def _advance_after_test(ctx) -> bool:
    """
    Called after a known test completes or after an unknown test is skipped.

    Returns True if the battery should continue.
    Returns False if the battery is complete.
    """
    state = _wait_for_landing_or_go_or_final(ctx, timeout=8)
    ctx.logger.info(f"Post-test page state: {state}")

    if state == "go":
        next_label = _get_next_test_label(ctx)
        if next_label:
            ctx.logger.info(f"Battery page says next test: {next_label}")
        else:
            ctx.logger.info("Battery go link found; next test label not found.")

        _click_go(ctx)
        return True

    if state == "landing":
        ctx.logger.info("Next test landing page already present.")
        return True

    _finish_battery(ctx)
    return False


def _skip_unknown_test(ctx, exact_code: str) -> dict[str, Any]:
    """
    Unknown test behavior:
    - Capture artifacts.
    - Mark the unknown test as FAIL.
    - Press Ctrl + . to skip.
    - Return the failure record.
    """
    ctx.logger.error(f"Unknown test encountered: {exact_code}")

    try:
        ctx.artifacts.capture_failure(
            ctx.driver,
            f"unknown_test_{exact_code}",
            {
                "exact_code": exact_code,
                "action": "mark_failed_and_skip_with_ctrl_period",
            },
        )
    except Exception as exc:
        ctx.logger.warning(f"Could not capture unknown-test artifacts: {exc}")

    record = _record_failed_test(ctx, exact_code, [UNKNOWN_TEST_ERROR])
    _send_ctrl_period(ctx)
    return record


def run_battery(ctx, registry=None):
    """
    Run an order-independent battery.

    The exact p.test-name on each landing page determines which plugin is used.
    Unknown tests are marked FAIL, skipped with Ctrl+., and the battery continues
    when possible.
    """
    registry = registry or TEST_REGISTRY
    completed = []

    while True:
        landing = TestLandingPage(ctx)
        exact_code = landing.get_exact_test_code()
        ctx.exact_code = exact_code
        ctx.logger.info(f"Detected landing test code: {exact_code}")

        if exact_code not in registry:
            record = _skip_unknown_test(ctx, exact_code)
            completed.append(record)

            if _advance_after_test(ctx):
                continue
            break

        plugin_cls = registry[exact_code]
        strategy = DEFAULT_STRATEGIES[exact_code]
        plugin = plugin_cls()

        ctx.logger.info(f"Starting {exact_code} with strategy={strategy}")
        landing.click_continue()

        result = plugin.run(ctx, strategy=strategy)
        record = _record_completed_test(ctx, exact_code, result)
        completed.append(record)

        ctx.logger.info(f"Completed {exact_code}: {result.status}")

        if _advance_after_test(ctx):
            continue
        break

    return completed