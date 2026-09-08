from __future__ import annotations

import json
import os
import time
from pathlib import Path

from core.artifacts import ArtifactManager
from core.driver_factory import build_driver
from core.logging_setup import setup_logger
from core.session_context import SessionContext
from core.waits import Waits
from tests_catalog.registry import DEFAULT_STRATEGIES, TEST_REGISTRY
from workflows.launch_battery import launch_battery
from workflows.run_battery import run_battery
from workflows.scrape_completed_tests import scrape_completed_tests


BROWSER_CHOICES = {
    "1": "chrome",
    "2": "firefox",
    "3": "edge",
    "chrome": "chrome",
    "firefox": "firefox",
    "edge": "edge",
}


def choose_browser() -> str:
    print("\nChoose browser:")
    print("  1. Chrome")
    print("  2. Firefox")
    print("  3. Edge")

    while True:
        raw = input("Browser [1/chrome, 2/firefox, 3/edge]: ").strip().lower()

        if not raw:
            return "chrome"

        browser = BROWSER_CHOICES.get(raw)
        if browser:
            return browser

        print("Invalid browser. Please choose chrome, firefox, or edge.")


def resolve_headless() -> bool:
    """
    Server-safe default:
    - If HEADLESS env is set, obey it.
    - If no DISPLAY exists, use headless automatically.
    - Otherwise visible mode.
    """
    raw = os.getenv("HEADLESS")

    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "y", "on"}

    return not bool(os.getenv("DISPLAY"))


def main():
    print("CNB Selenium Battery Runner")
    print("===========================")

    browser = choose_browser()
    subid = input("Enter subid: ").strip()
    battery_code = input("Enter battery code/name: ").strip()

    headless = resolve_headless()

    print()
    print(f"Browser: {browser}")
    print(f"Headless: {headless}")
    print(f"Subid: {subid}")
    print(f"Battery: {battery_code}")
    print()

    run_id = time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path("output") / f"{run_id}_{subid}"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logger(output_dir)
    logger.info("Starting CNB Selenium Battery Runner")
    logger.info("Browser: %s", browser)
    logger.info("Headless: %s", headless)
    logger.info("Subid: %s", subid)
    logger.info("Battery: %s", battery_code)
    logger.info("Output directory: %s", output_dir)

    driver = build_driver(browser=browser, headless=headless)

    try:
        ctx = SessionContext(
            driver=driver,
            wait=Waits(driver),
            logger=logger,
            artifacts=ArtifactManager(driver, output_dir),
            subid=subid,
            battery_code=battery_code,
            output_dir=output_dir,
            registry=TEST_REGISTRY,
            default_strategies=DEFAULT_STRATEGIES,
            browser=browser,
            headless=headless,
        )

        launch_battery(ctx)
        completed_tests = run_battery(ctx)

        completed_path = output_dir / "completed_tests.json"
        completed_path.write_text(
            json.dumps(completed_tests, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info("Completed tests written to %s", completed_path)

    finally:
        logger.info("Closing test browser")
        driver.quit()

    logger.info("Starting results scraping")

    scrape_results = scrape_completed_tests(ctx, completed_tests)

    scrape_path = output_dir / "scrape_results.json"
    scrape_path.write_text(
        json.dumps(scrape_results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Scrape results written to %s", scrape_path)
    logger.info("Run complete")


if __name__ == "__main__":
    main()