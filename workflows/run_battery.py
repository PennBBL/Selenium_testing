"""
Battery workflow.

Behavior:
- Reads exact p.test-name from each test landing page.
- Dispatches to the correct plugin based on exact test code.
- If selected-test mode is enabled, skips every unselected test with Ctrl + .
  until it reaches selected test groups/codes.
- If the test is unknown, records it as SKIPPED, saves artifacts, presses Ctrl + .,
  and continues the battery if possible.
- If a known plugin fails or raises an exception, records it as FAIL, saves artifacts,
  presses Ctrl + ., and continues the battery if possible.
- Every record includes a human-readable reason.
- After a known test completes successfully, briefly checks for:
    1. inter-test go.png link
    2. direct next p.test-name landing page
    3. otherwise treats the battery as complete
- When the battery is complete, waits 5 seconds before returning to runner.
"""
from __future__ import annotations

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


PASS_STATUS = "PASS"
FAIL_STATUS = "FAIL"
SKIP_STATUS = "SKIPPED"

UNKNOWN_TEST_ERROR = "Test does not exist in TEST_REGISTRY; skipped with Ctrl+."
PLUGIN_FAIL_SKIP_ERROR = "Known plugin failed; skipped with Ctrl+."
PLUGIN_EXCEPTION_SKIP_ERROR = "Known plugin raised exception; skipped with Ctrl+."
UNSELECTED_TEST_SKIP_ERROR = "Not in selected test list; skipped with Ctrl+."
LANDING_CONTINUE_ERROR = "Failed to click landing Continue; skipped with Ctrl+."

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


def _ensure_completed_tests(ctx) -> None:
    if not hasattr(ctx, "completed_tests") or ctx.completed_tests is None:
        ctx.completed_tests = []


def _append_record(ctx, record: dict[str, Any]) -> dict[str, Any]:
    _ensure_completed_tests(ctx)
    ctx.completed_tests.append(record)
    return record


def _reason_from_errors(errors: list[str], fallback: str) -> str:
    cleaned = [str(error).strip() for error in errors or [] if str(error).strip()]
    if cleaned:
        return "; ".join(cleaned)
    return fallback


def _mark_registry(ctx, exact_code: str, status: str, errors: list[str]) -> None:
    try:
        ctx.registry.mark_test_completed(ctx.subid, exact_code, status, errors)
    except Exception as exc:
        ctx.logger.warning(f"Could not mark test in registry: {exact_code}, status={status}, error={exc}")


def _record_failed_test(
    ctx,
    exact_code: str,
    errors: list[str],
    *,
    reason: str | None = None,
    skipped: bool = True,
    scrape: bool = False,
    strategy: str | None = None,
    skip_reason: str | None = None,
) -> dict[str, Any]:
    """Record a failed test and do not scrape it by default."""
    errors = [str(error) for error in (errors or [])]
    record = {
        "test_name": exact_code,
        "status": FAIL_STATUS,
        "reason": reason or _reason_from_errors(errors, "Test failed."),
        "errors": errors,
        "skipped": skipped,
        "skip_method": "ctrl_period" if skipped else None,
        "skip_reason": skip_reason,
        "scrape": scrape,
        "strategy": strategy,
    }

    _append_record(ctx, record)
    _mark_registry(ctx, exact_code, FAIL_STATUS, errors)
    return record


def _record_completed_test(ctx, exact_code: str, result, *, strategy: str | None = None) -> dict[str, Any]:
    """Record a known administered test that passed."""
    errors = [str(error) for error in (getattr(result, "errors", []) or [])]
    record = {
        "test_name": exact_code,
        "status": getattr(result, "status", PASS_STATUS),
        "reason": "Completed successfully.",
        "errors": errors,
        "skipped": False,
        "skip_method": None,
        "skip_reason": None,
        "scrape": True,
        "strategy": strategy,
    }

    _append_record(ctx, record)
    _mark_registry(ctx, exact_code, record["status"], errors)
    return record


def _record_skipped_test(
    ctx,
    exact_code: str,
    errors: list[str],
    *,
    reason: str,
    skip_reason: str,
    strategy: str | None = None,
) -> dict[str, Any]:
    """Record a skipped test."""
    errors = [str(error) for error in (errors or [])]
    record = {
        "test_name": exact_code,
        "status": SKIP_STATUS,
        "reason": reason,
        "errors": errors,
        "skipped": True,
        "skip_method": "ctrl_period",
        "skip_reason": skip_reason,
        "scrape": False,
        "strategy": strategy,
    }

    _append_record(ctx, record)
    _mark_registry(ctx, exact_code, SKIP_STATUS, errors)
    return record


def _record_skipped_unselected_test(ctx, exact_code: str) -> dict[str, Any]:
    """Record a test intentionally skipped because it was not selected."""
    selected = _selected_test_tokens(ctx)
    return _record_skipped_test(
        ctx,
        exact_code,
        [UNSELECTED_TEST_SKIP_ERROR],
        reason=f"Skipped because this test was not selected for this run. Selected tokens: {selected}.",
        skip_reason="not_selected",
    )


def _generic_group_name(exact_code: str) -> str:
    """
    Convert exact test codes into generic group names.

    Examples:
      zn_CN-k-pcet-3.00-ff    -> pcet
      k-pcet-3.00-ff          -> pcet
      zn_CN-spcptnl-2.01-ff   -> spcptnl
      pmat24-a-2.00-ff        -> pmat
      medf36-a-3.06-ff        -> medf
      zn_CN-vsplot24-2.10-ff  -> vsplot
    """
    code = (exact_code or "").strip().lower()
    code = re.sub(r"^[a-z]{2}_[a-z]{2}-", "", code)

    if code.startswith("k-"):
        code = code[2:]

    match = re.match(r"[a-z]+", code)
    if match:
        return match.group(0)

    return code.split("-", 1)[0]


def _selected_mode_enabled(ctx) -> bool:
    return getattr(ctx, "run_scope", "all") == "selected"


def _selected_test_tokens(ctx) -> list[str]:
    return [
        str(token).strip().lower()
        for token in getattr(ctx, "selected_test_tokens", [])
        if str(token).strip()
    ]


def _test_is_selected(ctx, exact_code: str) -> bool:
    tokens = _selected_test_tokens(ctx)

    if not tokens:
        return True

    exact_lower = (exact_code or "").lower()
    group = _generic_group_name(exact_code)

    for token in tokens:
        if token == exact_lower:
            return True

        if token == group:
            return True

        # Helpful fallback: "pcet" matches "zn_CN-k-pcet-3.00-ff".
        if token in exact_lower:
            return True

    return False


def _skip_unselected_test(ctx, exact_code: str) -> dict[str, Any]:
    ctx.logger.info(
        "Skipping unselected test %s with Ctrl+. Selected tokens=%s",
        exact_code,
        _selected_test_tokens(ctx),
    )

    record = _record_skipped_unselected_test(ctx, exact_code)
    _send_ctrl_period(ctx)
    return record


def _wait_for_landing_or_go_or_final(ctx, timeout: int = 8) -> str:
    """
    Inspect the current page after a test ends or after Ctrl+. Returns:

    "go"       -> battery inter-test page has go.png
    "landing"  -> next p.test-name landing page is already present
    "final"    -> no next controls appeared within timeout
    "quit"     -> final quit/stop link appeared
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        if _page_has_go(ctx):
            return "go"

        if _page_has_test_landing(ctx):
            return "landing"

        if _page_has_quit(ctx):
            return "quit"

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
    - Record as SKIPPED because no plugin is registered for this code.
    - Press Ctrl + . to skip.
    - Return the skipped record.
    """
    ctx.logger.error(f"Unknown test encountered: {exact_code}")

    _capture_failure_artifact(
        ctx,
        f"unknown_test_{exact_code}",
        {
            "exact_code": exact_code,
            "action": "record_skipped_and_skip_with_ctrl_period",
            "reason": UNKNOWN_TEST_ERROR,
        },
    )

    record = _record_skipped_test(
        ctx,
        exact_code,
        [UNKNOWN_TEST_ERROR],
        reason=f"Skipped because {exact_code} does not exist in TEST_REGISTRY.",
        skip_reason="not_in_registry",
    )
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
    return getattr(result, "status", None) != PASS_STATUS


def run_battery(ctx, registry=None):
    """
    Run an order-independent battery.

    The exact p.test-name on each landing page determines which plugin is used.

    If ctx.run_scope == "selected", only tests matching ctx.selected_test_tokens
    are administered. Non-selected tests are skipped with Ctrl+. Matching supports:
      - generic group name, e.g. pcet
      - exact code, e.g. zn_CN-k-pcet-3.00-ff
      - fallback substring match

    Unknown tests are marked SKIPPED, skipped with Ctrl+., and the battery continues
    when possible.

    Known tests that return FAIL or raise exceptions are marked FAIL, skipped
    with Ctrl+., and the battery continues when possible.
    """
    registry = registry or TEST_REGISTRY
    completed = []
    _ensure_completed_tests(ctx)

    while True:
        landing = TestLandingPage(ctx)
        exact_code = landing.get_exact_test_code()
        ctx.exact_code = exact_code
        ctx.logger.info(f"Detected landing test code: {exact_code}")

        if _selected_mode_enabled(ctx) and not _test_is_selected(ctx, exact_code):
            record = _skip_unselected_test(ctx, exact_code)
            completed.append(record)

            if _advance_after_test(ctx):
                continue

            break

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

            errors = [f"{LANDING_CONTINUE_ERROR} {exc}"]
            record = _record_failed_test(
                ctx,
                exact_code,
                errors,
                reason=f"Failed to click landing Continue: {exc}",
                skipped=True,
                scrape=False,
                strategy=strategy,
                skip_reason="landing_continue_failed",
            )
            completed.append(record)

            _capture_failure_artifact(
                ctx,
                f"landing_continue_failure_{exact_code}",
                {
                    "exact_code": exact_code,
                    "errors": errors,
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
                reason=_reason_from_errors(
                    failed_result.errors,
                    f"Known plugin for {exact_code} returned FAIL.",
                ),
                skipped=True,
                scrape=False,
                strategy=strategy,
                skip_reason="plugin_failed",
            )
            completed.append(record)

            ctx.logger.info(f"Completed {exact_code}: {failed_result.status}")
            _skip_failed_known_test(ctx, exact_code, failed_result)

            if _advance_after_test(ctx):
                continue

            break

        record = _record_completed_test(ctx, exact_code, result, strategy=strategy)
        completed.append(record)

        ctx.logger.info(f"Completed {exact_code}: {record['status']}")

        if _advance_after_test(ctx):
            continue

        break

    return completed
