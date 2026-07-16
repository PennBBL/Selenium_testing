"""
Battery workflow.

Behavior:
- Reads exact p.test-name from each test landing page.
- Dispatches to the correct plugin based on exact test code.
- If the test is unknown, logs it as FAIL, saves artifacts, presses Ctrl + .,
  and continues the battery if possible.
- If a known plugin fails or raises an exception, logs it as FAIL, saves artifacts,
  presses Ctrl + ., and continues the battery if possible.
- After a known test completes successfully, briefly checks for:
    1. inter-test go.png link
    2. direct next p.test-name landing page
    3. otherwise treats the battery as complete
- When the battery is complete, waits 5 seconds before returning to runner.
"""

import re
import time
from typing import Any

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from pages.test_landing_page import TestLandingPage
from tests_catalog.common import TestRunResult
from tests_catalog.registry import TEST_REGISTRY, DEFAULT_STRATEGIES


FAIL_STATUS = "FAIL"

UNKNOWN_TEST_ERROR = "Unknown test code; skipped with Ctrl+."
PLUGIN_FAIL_SKIP_ERROR = "Known plugin failed; skipped with Ctrl+."
PLUGIN_EXCEPTION_SKIP_ERROR = "Known plugin raised exception; skipped with Ctrl+."

GO_LINK = (By.XPATH, "//a[.//img[contains(@src, 'go.png')]]")
QUIT_LINK = (By.XPATH, "//a[contains(@href, 'op=Quit') or .//img[contains(@src, 'stop.png')]]")
NEXT_TEST_TEXT = (By.XPATH, "//p[contains(normalize-space(.), 'Next test:')]")
TEST_NAME = (By.CSS_SELECTOR, "p.test-name")


def _safe_artifact_name(value: str) -> str:
    value = value or "unknown"
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return value.strip("_") or "unknown"


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

    try:
        ActionChains(ctx.driver).key_down(Keys.CONTROL).send_keys(".").key_up(Keys.CONTROL).perform()
    except Exception:
        ctx.logger.exception("ActionChains Ctrl+. failed; trying body fallback")

        try:
            body = ctx.driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.CONTROL, ".")
        except Exception:
            ctx.logger.exception("Body Ctrl+. fallback failed")
            raise

    time.sleep(1)


def _capture_failure_artifact(ctx, name: str, payload: dict[str, Any]) -> None:
    try:
        ctx.artifacts.capture_failure(ctx.driver, _safe_artifact_name(name), payload)
    except Exception as exc:
        ctx.logger.warning(f"Could not capture failure artifact {name}: {exc}")


def _record_failed_test(
    ctx,
    exact_code: str,
    errors: list[str],
    skipped: bool = True,
    scrape: bool = False,
) -> dict[str, Any]:
    """Record a failed/skipped test and do not scrape it by default."""
    record = {
        "test_name": exact_code,
        "status": FAIL_STATUS,
        "errors": errors,
        "skipped": skipped,
        "skip_method": "ctrl_period" if skipped else None,
        "scrape": scrape,
    }

    ctx.completed_tests.append(record)
    ctx.registry.mark_test_completed(ctx.subid, exact_code, FAIL_STATUS, errors)
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
    Called after a known test completes or after a test is skipped.

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

    _capture_failure_artifact(
        ctx,
        f"unknown_test_{exact_code}",
        {
            "exact_code": exact_code,
            "action": "mark_failed_and_skip_with_ctrl_period",
        },
    )

    record = _record_failed_test(ctx, exact_code, [UNKNOWN_TEST_ERROR], skipped=True, scrape=False)
    _send_ctrl_period(ctx)
    return record


def _skip_failed_known_test(ctx, exact_code: str, result) -> None:
    """
    Known test failure behavior:
    - Plugin already returned FAIL.
    - Capture artifacts.
    - Press Ctrl + . to skip current test state.
    """
    ctx.logger.error(f"Known test failed: {exact_code}; skipping with Ctrl+.")

    _capture_failure_artifact(
        ctx,
        f"failed_test_{exact_code}",
        {
            "exact_code": exact_code,
            "status": getattr(result, "status", FAIL_STATUS),
            "errors": getattr(result, "errors", []),
            "action": "skip_failed_known_test_with_ctrl_period",
        },
    )

    _send_ctrl_period(ctx)


def _run_plugin_safely(ctx, exact_code: str, plugin, strategy: str):
    """
    Run a plugin and convert unhandled exceptions into TestRunResult FAIL.

    This prevents a plugin exception from stopping the battery loop.
    """
    try:
        return plugin.run(ctx, strategy=strategy)

    except Exception as exc:
        ctx.logger.exception(f"{exact_code} plugin raised unhandled exception")

        _capture_failure_artifact(
            ctx,
            f"plugin_exception_{exact_code}",
            {
                "exact_code": exact_code,
                "error": str(exc),
                "action": "convert_exception_to_fail_and_skip",
            },
        )

        return TestRunResult(
            status=FAIL_STATUS,
            errors=[f"{PLUGIN_EXCEPTION_SKIP_ERROR} {exc}"],
        )


def _result_failed(result) -> bool:
    return getattr(result, "status", None) != "PASS"


def run_battery(ctx, registry=None):
    """
    Run an order-independent battery.

    The exact p.test-name on each landing page determines which plugin is used.
    Unknown tests are marked FAIL, skipped with Ctrl+., and the battery continues
    when possible.

    Known tests that return FAIL or raise exceptions are also marked FAIL, skipped
    with Ctrl+., and the battery continues when possible.
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
        strategy = DEFAULT_STRATEGIES.get(exact_code, "random")
        plugin = plugin_cls()

        ctx.logger.info(f"Starting {exact_code} with strategy={strategy}")

        try:
            landing.click_continue()
        except Exception as exc:
            ctx.logger.exception(f"{exact_code}: failed to click landing continue")

            result = TestRunResult(
                status=FAIL_STATUS,
                errors=[f"Failed to click landing continue: {exc}"],
            )

            record = _record_failed_test(
                ctx,
                exact_code,
                result.errors,
                skipped=True,
                scrape=False,
            )
            completed.append(record)

            _capture_failure_artifact(
                ctx,
                f"landing_continue_failure_{exact_code}",
                {
                    "exact_code": exact_code,
                    "errors": result.errors,
                    "action": "skip_after_landing_continue_failure",
                },
            )

            _send_ctrl_period(ctx)

            if _advance_after_test(ctx):
                continue

            break

        result = _run_plugin_safely(ctx, exact_code, plugin, strategy)

        if result.errors:
            ctx.logger.error(f"{exact_code} errors: {result.errors}")

        if _result_failed(result):
            errors = list(result.errors or [])
            if PLUGIN_FAIL_SKIP_ERROR not in " ".join(errors):
                errors.append(PLUGIN_FAIL_SKIP_ERROR)

            failed_result = TestRunResult(status=FAIL_STATUS, errors=errors)

            record = _record_failed_test(
                ctx,
                exact_code,
                failed_result.errors,
                skipped=True,
                scrape=False,
            )
            completed.append(record)

            ctx.logger.info(f"Completed {exact_code}: {failed_result.status}")
            _skip_failed_known_test(ctx, exact_code, failed_result)

            if _advance_after_test(ctx):
                continue

            break

        record = _record_completed_test(ctx, exact_code, result)
        completed.append(record)

        ctx.logger.info(f"Completed {exact_code}: {result.status}")

        if _advance_after_test(ctx):
            continue

        break

    return completed