from __future__ import annotations

import csv
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

try:
    from scraping.base_scraper import get_datasetid_for_subid
except Exception:
    get_datasetid_for_subid = None


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


SUMMARY_CSV_NAME = "completed_tests_summary.csv"
INDIVIDUAL_STATUS_DIR = "test_status"


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


def score_scraping_enabled() -> bool:
    """
    Score scraping is disabled by default for now.

    Future behavior can be restored without changing code by setting:
        SCRAPE_RESULTS=1
    """
    return bool(env_bool("SCRAPE_RESULTS", default=False))


def sanitize_folder_part(value) -> str:
    value = str(value or "").strip().replace(" ", "_")
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_") or "unknown"


def sanitize_file_part(value) -> str:
    return sanitize_folder_part(value)


def normalize_status(status) -> str:
    status = str(status or "UNKNOWN").strip().upper()
    if status in {"SKIP", "SKIPPED"}:
        return "SKIPPED"
    return status


def record_reason(record: dict) -> str:
    reason = str(record.get("reason") or "").strip()
    if reason:
        return reason

    errors = record.get("errors") or []
    if isinstance(errors, list) and errors:
        return "; ".join(str(error) for error in errors if str(error).strip())

    status = normalize_status(record.get("status"))
    if status == "PASS":
        return "Completed successfully."
    if status == "SKIPPED":
        return "Skipped."
    if status == "FAIL":
        return "Failed."
    return "No reason recorded."


def completed_summary_rows(
    completed_tests: list[dict],
    *,
    run_date: str,
    datasetid: str | None,
    subid: str,
    battery_code: str,
    browser: str,
    headless: bool,
    run_scope: str,
    selected_test_tokens: list[str],
) -> list[dict]:
    rows = []
    selected_text = ",".join(selected_test_tokens or [])

    for index, record in enumerate(completed_tests, start=1):
        errors = record.get("errors") or []
        if not isinstance(errors, list):
            errors = [str(errors)]

        rows.append({
            "run_date": run_date,
            "datasetid": datasetid or "",
            "subid": subid,
            "battery_code": battery_code,
            "browser": browser,
            "headless": str(bool(headless)),
            "run_scope": run_scope,
            "selected_test_tokens": selected_text,
            "order": index,
            "test_name": record.get("test_name", ""),
            "status": normalize_status(record.get("status")),
            "reason": record_reason(record),
            "errors": json.dumps(errors, ensure_ascii=False),
            "skipped": str(bool(record.get("skipped", False))),
            "skip_method": record.get("skip_method") or "",
            "skip_reason": record.get("skip_reason") or "",
            "scrape": str(bool(record.get("scrape", False))),
            "strategy": record.get("strategy") or "",
        })

    return rows


def write_summary_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "run_date",
        "datasetid",
        "subid",
        "battery_code",
        "browser",
        "headless",
        "run_scope",
        "selected_test_tokens",
        "order",
        "test_name",
        "status",
        "reason",
        "errors",
        "skipped",
        "skip_method",
        "skip_reason",
        "scrape",
        "strategy",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_individual_status_files(output_dir: Path, rows: list[dict]) -> None:
    status_dir = output_dir / INDIVIDUAL_STATUS_DIR
    status_dir.mkdir(parents=True, exist_ok=True)

    for row in rows:
        order = str(row.get("order") or "0").zfill(2)
        test_name = sanitize_file_part(row.get("test_name") or "unknown_test")
        path = status_dir / f"{order}_{test_name}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")


def write_run_outputs(
    output_dir: Path,
    completed_tests: list[dict],
    *,
    run_date: str,
    datasetid: str | None,
    subid: str,
    battery_code: str,
    browser: str,
    headless: bool,
    run_scope: str,
    selected_test_tokens: list[str],
    dataset_lookup_error: str | None = None,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "run_date": run_date,
        "datasetid": datasetid,
        "subid": subid,
        "battery_code": battery_code,
        "browser": browser,
        "headless": bool(headless),
        "run_scope": run_scope,
        "selected_test_tokens": selected_test_tokens,
        "score_scraping_enabled": score_scraping_enabled(),
        "dataset_lookup_error": dataset_lookup_error,
        "output_dir": str(output_dir),
    }

    rows = completed_summary_rows(
        completed_tests,
        run_date=run_date,
        datasetid=datasetid,
        subid=subid,
        battery_code=battery_code,
        browser=browser,
        headless=headless,
        run_scope=run_scope,
        selected_test_tokens=selected_test_tokens,
    )

    completed_path = output_dir / "completed_tests.json"
    completed_path.write_text(
        json.dumps(completed_tests, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    metadata_path = output_dir / "run_metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary_path = output_dir / SUMMARY_CSV_NAME
    write_summary_csv(summary_path, rows)

    write_individual_status_files(output_dir, rows)

    return {
        "metadata": metadata,
        "rows": rows,
        "completed_path": completed_path,
        "metadata_path": metadata_path,
        "summary_path": summary_path,
    }


def final_output_dir_for(output_root: Path, datasetid: str | None, run_date: str, subid: str) -> Path:
    dataset_part = sanitize_folder_part(datasetid or "datasetid_unknown")
    date_part = sanitize_folder_part(run_date)
    subid_part = sanitize_folder_part(subid)

    base = output_root / f"{dataset_part}_{date_part}_{subid_part}"

    if not base.exists():
        return base

    suffix = 2
    while True:
        candidate = output_root / f"{dataset_part}_{date_part}_{subid_part}_{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def rename_output_dir(current_output_dir: Path, final_output_dir: Path) -> Path:
    current_output_dir = Path(current_output_dir)
    final_output_dir = Path(final_output_dir)

    if current_output_dir.resolve() == final_output_dir.resolve():
        return current_output_dir

    final_output_dir.parent.mkdir(parents=True, exist_ok=True)
    current_output_dir.rename(final_output_dir)
    return final_output_dir


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


def lookup_datasetid(subid: str, logger) -> tuple[str | None, str | None]:
    if get_datasetid_for_subid is None:
        return None, "get_datasetid_for_subid is not available from scraping.base_scraper."

    try:
        datasetid = get_datasetid_for_subid(subid=subid)
        if datasetid:
            logger.info("Dataset ID found: %s", datasetid)
            return str(datasetid), None
        return None, "Dataset ID was not found on the results page."
    except Exception as exc:
        logger.exception("Dataset ID lookup failed: %s", exc)
        return None, str(exc)


def main():
    print("=" * 70)
    print("PENN CNB BATTERY RUNNER")
    print("Browser-selectable, selected-test capable, headless-capable")
    print("Score scraping disabled by default; status summary enabled")
    print("=" * 70)

    browser = choose_browser()
    subid = prompt_required("Enter Subject ID / subid: ")
    battery_code = prompt_required("Enter Battery Code: ")
    run_scope, selected_test_tokens = prompt_run_scope()

    headless = resolve_headless()
    run_date = datetime.now().strftime("%Y%m%d")

    print()
    print(f"Browser: {browser}")
    print(f"Headless: {headless}")
    print(f"Subid: {subid}")
    print(f"Battery Code: {battery_code}")
    print(f"Run scope: {run_scope}")
    if run_scope == "selected":
        print(f"Selected test(s): {', '.join(selected_test_tokens)}")
    print(f"Score scraping enabled: {score_scraping_enabled()}")
    print()

    temp_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = Path("output")
    output_dir = output_root / f"_tmp_{temp_run_id}_{sanitize_folder_part(subid)}"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_dir)
    logger.info("Starting PENN CNB Battery Runner")
    logger.info("Browser: %s", browser)
    logger.info("Headless: %s", headless)
    logger.info("Subid: %s", subid)
    logger.info("Battery code: %s", battery_code)
    logger.info("Run scope: %s", run_scope)
    logger.info("Selected test tokens: %s", selected_test_tokens)
    logger.info("Temporary output directory: %s", output_dir)
    logger.info("Score scraping enabled: %s", score_scraping_enabled())

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

        # Preliminary files, in case dataset lookup or rename fails.
        write_run_outputs(
            output_dir,
            completed_tests,
            run_date=run_date,
            datasetid=None,
            subid=subid,
            battery_code=battery_code,
            browser=browser,
            headless=headless,
            run_scope=run_scope,
            selected_test_tokens=selected_test_tokens,
        )

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
        raise RuntimeError("Session context was not created; cannot finalize results.")

    logger.info("Looking up dataset ID for output folder name...")
    datasetid, dataset_lookup_error = lookup_datasetid(subid, logger)

    final_dir = final_output_dir_for(output_root, datasetid, run_date, subid)
    output_dir = rename_output_dir(output_dir, final_dir)

    ctx.output_dir = output_dir
    logger.info("Final output directory: %s", output_dir)

    outputs = write_run_outputs(
        output_dir,
        completed_tests,
        run_date=run_date,
        datasetid=datasetid,
        subid=subid,
        battery_code=battery_code,
        browser=browser,
        headless=headless,
        run_scope=run_scope,
        selected_test_tokens=selected_test_tokens,
        dataset_lookup_error=dataset_lookup_error,
    )

    logger.info("Completed tests written to %s", outputs["completed_path"])
    logger.info("Run metadata written to %s", outputs["metadata_path"])
    logger.info("Summary CSV written to %s", outputs["summary_path"])

    if score_scraping_enabled():
        logger.info("Starting score scraping for completed tests because SCRAPE_RESULTS=1...")
        scrape_results = scrape_completed_tests(ctx, completed_tests)
    else:
        logger.info("Score scraping skipped because SCRAPE_RESULTS is not enabled.")
        scrape_results = [{
            "test_name": "__score_scraping__",
            "status": "SKIPPED",
            "scrape_status": "SKIPPED_BY_CONFIG",
            "reason": "Score scraping is currently disabled. Set SCRAPE_RESULTS=1 to enable it later.",
            "datasetid": datasetid,
        }]

    scrape_path = output_dir / "scrape_results.json"
    scrape_path.write_text(
        json.dumps(scrape_results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Scrape results written to %s", scrape_path)
    logger.info("All done.")


if __name__ == "__main__":
    main()
