from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

try:
    from core.driver_factory import build_driver
except ImportError:
    from core.driver_factory import build_chrome_driver

    def build_driver(browser="chrome", headless=None):
        browser = (browser or "chrome").strip().lower()
        if browser != "chrome":
            raise RuntimeError(
                "Firefox/Edge require core.driver_factory.build_driver(). "
                "Update core/driver_factory.py before choosing this browser."
            )
        return build_chrome_driver(headless=headless)

from core.logging_setup import setup_logging
from core.waits import Waits
from core.artifacts import ArtifactManager
from core.session_context import SessionContext
from core.subid_registry import SubidRegistry
from tests_catalog.registry import TEST_REGISTRY
from workflows.launch_battery import launch_battery
from workflows.run_battery import run_battery
from workflows.scrape_completed_tests import scrape_completed_tests


BROWSER_CHOICES = {
    "1": "chrome",
    "2": "firefox",
    "3": "edge",
    "chrome": "chrome",
    "firefox": "firefox",
    "ff": "firefox",
    "edge": "edge",
    "msedge": "edge",
}


def prompt_required(label: str) -> str:
    while True:
        value = input(label).strip()
        if value:
            return value
        print("This value is required.")


def choose_browser() -> str:
    print()
    print("Choose browser:")
    print("  1. Chrome")
    print("  2. Firefox")
    print("  3. Edge")

    while True:
        value = input("Browser [1/chrome, 2/firefox, 3/edge]: ").strip().lower()

        if not value:
            return "chrome"

        browser = BROWSER_CHOICES.get(value)
        if browser:
            return browser

        print("Invalid browser. Choose chrome, firefox, or edge.")


def generic_group_name(exact_code: str) -> str:
    """
    Convert exact registry codes into generic test group names.

    Examples:
      zn_CN-k-pcet-3.00-ff    -> pcet
      k-pcet-3.00-ff          -> pcet
      zn_CN-spcptnl-2.01-ff   -> spcptnl
      pmat24-a-2.00-ff        -> pmat
      medf36-a-3.06-ff        -> medf
      zn_CN-vsplot24-2.10-ff  -> vsplot
    """
    code = (exact_code or "").strip().lower()

    # Remove language prefix like zn_CN-, zh_CN-, kr_KR- after lowercasing.
    code = re.sub(r"^[a-z]{2}_[a-z]{2}-", "", code)

    # Remove common keyboard-test prefix.
    if code.startswith("k-"):
        code = code[2:]

    match = re.match(r"[a-z]+", code)
    if match:
        return match.group(0)

    return code.split("-", 1)[0]


def available_test_groups() -> list[str]:
    groups = {generic_group_name(code) for code in TEST_REGISTRY.keys()}
    return sorted(group for group in groups if group)


def prompt_run_scope():
    groups = available_test_groups()

    print()
    print("Run mode:")
    print("  1. Whole battery")
    print("  2. Particular test(s)")

    while True:
        mode = input(
            "Run whole battery or particular tests? [1/whole, 2/particular]: "
        ).strip().lower()

        if not mode or mode in {"1", "whole", "all", "battery"}:
            return "all", []

        if mode in {"2", "particular", "test", "tests", "selected"}:
            print()
            print("Available test groups:")
            for index, group in enumerate(groups, start=1):
                print(f"  {index}. {group}")

            print()
            print("Enter test names or numbers separated by commas.")
            print("Examples:")
            print("  pcet")
            print("  pcet, spcptnl")
            print("  3, 8")
            print("  zn_CN-k-pcet-3.00-ff")
            print()

            raw = input("Selected test(s): ").strip()

            selected = []
            for item in raw.split(","):
                token = item.strip()
                if not token:
                    continue

                if token.isdigit():
                    number = int(token)
                    if 1 <= number <= len(groups):
                        selected.append(groups[number - 1])
                    else:
                        print(f"Ignoring invalid test number: {token}")
                else:
                    selected.append(token.lower())

            if not selected:
                print("Please enter at least one test name or number.")
                continue

            return "selected", selected

        print("Invalid choice. Enter 1 for whole battery or 2 for particular tests.")


def env_bool(name: str, default=None):
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def resolve_headless() -> bool:
    env_headless = env_bool("HEADLESS", default=None)

    if env_headless is not None:
        return bool(env_headless)

    return not bool(os.getenv("DISPLAY"))


def build_session_context(
    driver,
    wait,
    logger,
    artifacts,
    subid,
    battery_code,
    output_dir,
    browser,
    headless,
):
    base_kwargs = {
        "driver": driver,
        "wait": wait,
        "logger": logger,
        "artifacts": artifacts,
        "subid": subid,
        "battery_code": battery_code,
        "output_dir": output_dir,
    }

    try:
        return SessionContext(
            **base_kwargs,
            browser=browser,
            headless=headless,
        )
    except TypeError:
        return SessionContext(**base_kwargs)


def main():
    print("=" * 70)
    print("PENN CNB BATTERY RUNNER")
    print("Browser-selectable, selected-test capable, headless-capable")
    print("=" * 70)

    browser = choose_browser()
    subid = prompt_required("Enter Subject ID / subid: ")
    battery_code = prompt_required("Enter Battery Code: ")
    run_scope, selected_test_tokens = prompt_run_scope()

    headless = resolve_headless()

    print()
    print(f"Browser: {browser}")
    print(f"Headless: {headless}")
    print(f"Subid: {subid}")
    print(f"Battery Code: {battery_code}")
    print(f"Run scope: {run_scope}")
    if run_scope == "selected":
        print(f"Selected test(s): {', '.join(selected_test_tokens)}")
    print()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("output") / f"{run_id}_{subid}"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_dir)
    logger.info("Starting PENN CNB Battery Runner")
    logger.info("Browser: %s", browser)
    logger.info("Headless: %s", headless)
    logger.info("Subid: %s", subid)
    logger.info("Battery code: %s", battery_code)
    logger.info("Run scope: %s", run_scope)
    logger.info("Selected test tokens: %s", selected_test_tokens)
    logger.info("Output directory: %s", output_dir)

    driver = None
    artifacts = None
    ctx = None
    completed_tests = []

    try:
        driver = build_driver(browser=browser, headless=headless)
        wait = Waits(driver)
        artifacts = ArtifactManager(driver, output_dir)

        registry = SubidRegistry(output_dir / "battery_state.json")
        registry.register_battery(subid, battery_code)

        ctx = build_session_context(
            driver=driver,
            wait=wait,
            logger=logger,
            artifacts=artifacts,
            subid=subid,
            battery_code=battery_code,
            output_dir=output_dir,
            browser=browser,
            headless=headless,
        )

        ctx.registry = registry
        ctx.run_scope = run_scope
        ctx.selected_test_tokens = selected_test_tokens

        launch_battery(ctx)
        completed_tests = run_battery(ctx)

        completed_path = output_dir / "completed_tests.json"
        completed_path.write_text(
            json.dumps(completed_tests, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info("Completed tests written to %s", completed_path)
        logger.info("Battery completed. Waiting 5 seconds before closing test browser...")
        time.sleep(5)

    except Exception as exc:
        logger.exception("Battery failed: %s", exc)

        if artifacts is not None:
            try:
                artifacts.capture_failure(
                    "battery_runner_failure",
                    str(exc),
                    {"error": str(exc)},
                )
            except Exception:
                logger.exception("Could not capture battery runner failure artifact")

        raise

    finally:
        if driver is not None:
            try:
                driver.quit()
                logger.info("Test browser closed.")
            except Exception:
                pass

    if ctx is None:
        raise RuntimeError("Session context was not created; cannot scrape results.")

    logger.info("Starting scraping for completed tests...")

    scrape_results = scrape_completed_tests(ctx, completed_tests)

    scrape_path = output_dir / "scrape_results.json"
    scrape_path.write_text(
        json.dumps(scrape_results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Scrape results written to %s", scrape_path)
    logger.info("Scrape results: %s", scrape_results)
    logger.info("All done.")


if __name__ == "__main__":
    main()
