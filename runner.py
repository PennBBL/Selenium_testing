from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

try:
    from core.driver_factory import build_driver
except ImportError:
    # Fallback so Chrome still works if driver_factory.py has not been updated yet.
    # Firefox/Edge require core.driver_factory.build_driver().
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
from core.artifacts import Artifacts
from core.session_context import SessionContext
from core.subid_registry import SubidRegistry
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


def env_bool(name: str, default=None):
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def resolve_headless() -> bool:
    """
    Server-safe behavior:
    - If HEADLESS is set, obey it.
    - If DISPLAY is missing, run headless automatically.
    - Otherwise run visible.
    """
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
    """
    Build SessionContext while staying compatible with older/newer versions
    of core/session_context.py.
    """
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
    print("Browser-selectable, headless-capable, default/correct strategies")
    print("=" * 70)

    browser = choose_browser()
    subid = prompt_required("Enter Subject ID / subid: ")
    battery_code = prompt_required("Enter Battery Code: ")

    headless = resolve_headless()

    print()
    print(f"Browser: {browser}")
    print(f"Headless: {headless}")
    print(f"Subid: {subid}")
    print(f"Battery Code: {battery_code}")
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
    logger.info("Output directory: %s", output_dir)

    driver = None
    completed_tests = []

    try:
        driver = build_driver(browser=browser, headless=headless)
        wait = Waits(driver)
        artifacts = Artifacts(output_dir)

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
        if "logger" in locals():
            logger.exception("Battery failed: %s", exc)

        if driver is not None and "artifacts" in locals():
            try:
                artifacts.capture_failure(
                    driver,
                    "battery_runner_failure",
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