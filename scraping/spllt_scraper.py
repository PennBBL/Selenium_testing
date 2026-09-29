from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from core.driver_factory import build_chrome_driver
from scraping.base_scraper import LOGIN_URL, do_login, get_browser_info


SPLLT_TEST_CODE = "spllt-a-1.00-ff"
SPLLT_CSV_NAME = "spllt_results.csv"

SPLLT_SCORE_COLUMNS = [
    "SPLLTCOR1",
    "SPLLTPER1",
    "SPLLTINT1",
    "SPLLTCOR2",
    "SPLLTPER2",
    "SPLLTINT2",
    "SPLLTCOR3",
    "SPLLTPER3",
    "SPLLTINT3",
    "SPLLT_CORR",
    "SPLLT_CORR_WREPEATS",
    "SPLLT_INT",
]

BASE_RESULTS_URL = "https://penncnp-dev.pmacs.upenn.edu/results.pl"


CSV_FIELDNAMES = [
    "timestamp",
    "datasetid",
    "test_name",
    "subid",
    "strategy",
    "test_result",
    "os_name",
    "os_version",
    "browser_name",
    "browser_version",
] + SPLLT_SCORE_COLUMNS


def _document_ready(driver) -> bool:
    try:
        return driver.execute_script("return document.readyState") == "complete"
    except Exception:
        return False


def _safe_click(driver, element) -> None:
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});",
        element,
    )
    time.sleep(0.2)

    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def _normalize_score_name(value: str) -> str:
    return str(value or "").strip().split("(")[0].strip()


def _dataset_scores_url(datasetid: str) -> str:
    return (
        f"{BASE_RESULTS_URL}?op=display_scores"
        f"&datasetid={datasetid}"
    )


def _validate_datasetid(driver, datasetid: str) -> None:
    expected = str(datasetid).strip()

    element = WebDriverWait(driver, 20).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "input[name='datasetid']")
    )

    observed = (element.get_attribute("value") or "").strip()

    if observed != expected:
        raise RuntimeError(
            "SPLLT results page dataset mismatch: "
            f"requested {expected}, page shows {observed!r}"
        )


def open_scores_for_datasetid(driver, datasetid: str) -> None:
    """
    Open the exact CNB score page for one dataset ID.

    SPLLT creates one dataset ID per scenario, so selecting a session only by
    subid is not sufficient. This function navigates directly to the requested
    dataset and validates that the returned page belongs to that dataset.
    """
    datasetid = str(datasetid).strip()

    if not datasetid:
        raise ValueError("datasetid is required")

    url = _dataset_scores_url(datasetid)
    driver.get(url)

    WebDriverWait(driver, 20).until(_document_ready)

    # If authentication redirected us away from the results page, log in and
    # then return to the exact dataset URL.
    if not driver.find_elements(By.CSS_SELECTOR, "input[name='datasetid']"):
        do_login(driver, LOGIN_URL)
        time.sleep(1)
        driver.get(url)
        WebDriverWait(driver, 20).until(_document_ready)

    _validate_datasetid(driver, datasetid)

    # display_scores normally exposes a ListScores submit button. If the page
    # is already showing score rows, no extra click is needed.
    list_scores_buttons = [
        element
        for element in driver.find_elements(By.NAME, "ListScores")
        if element.is_displayed() and element.is_enabled()
    ]

    if list_scores_buttons:
        _safe_click(driver, list_scores_buttons[0])
        WebDriverWait(driver, 20).until(_document_ready)
        _validate_datasetid(driver, datasetid)

    WebDriverWait(driver, 20).until(
        lambda d: len(
            d.find_elements(By.CSS_SELECTOR, "tr.row1, tr.row2")
        ) > 0
    )


def collect_spllt_scores(driver) -> dict[str, str]:
    """Collect only the SPLLT scores requested for functional validation."""
    target_lookup = {
        score.upper(): score
        for score in SPLLT_SCORE_COLUMNS
    }

    scores: dict[str, str] = {}

    for row in driver.find_elements(By.CSS_SELECTOR, "tr.row1, tr.row2"):
        cells = row.find_elements(By.TAG_NAME, "td")

        if len(cells) < 2:
            continue

        score_name = _normalize_score_name(cells[0].text)
        canonical = target_lookup.get(score_name.upper())

        if not canonical:
            continue

        scores[canonical] = cells[1].text.strip()

    return scores


def _empty_csv_row() -> dict:
    return {field: "" for field in CSV_FIELDNAMES}


def _append_csv_row(output_dir: Path, row: dict) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / SPLLT_CSV_NAME
    exists = path.exists()

    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CSV_FIELDNAMES,
            extrasaction="ignore",
        )

        if not exists:
            writer.writeheader()

        writer.writerow(row)

    return path


def _write_result_row(
    *,
    output_dir: Path,
    datasetid: str | None,
    subid: str,
    strategy: str,
    status: str,
    scores: dict[str, str],
    os_name: str,
    os_version: str,
    browser_name: str,
    browser_version: str,
) -> Path:
    row = _empty_csv_row()

    row.update({
        "timestamp": datetime.now().isoformat(),
        "datasetid": datasetid or "",
        "test_name": SPLLT_TEST_CODE,
        "subid": subid,
        "strategy": strategy,
        "test_result": status,
        "os_name": os_name,
        "os_version": os_version,
        "browser_name": browser_name,
        "browser_version": browser_version,
    })

    row.update(scores)

    return _append_csv_row(output_dir, row)


def scrape_spllt_records(ctx, completed_tests: list[dict]) -> list[dict]:
    """
    Scrape every SPLLT scenario by its exact dataset ID.

    Expected input records look like:
        {
            "test_name": "spllt-a-1.00-ff",
            "strategy": "coverage",
            "datasetid": "3841929",
            "status": "PASS",
            ...
        }

    Output:
        <ctx.output_dir>/spllt_results.csv

    There is one CSV row per SPLLT scenario/dataset ID.
    """
    records = [
        record
        for record in completed_tests
        if record.get("test_name") == SPLLT_TEST_CODE
    ]

    if not records:
        return []

    output_dir = Path(ctx.output_dir)
    scrape_results: list[dict] = []

    driver = build_chrome_driver()

    try:
        # Establish an authenticated results session once, then reuse the same
        # browser for all SPLLT dataset IDs.
        do_login(driver, LOGIN_URL)
        time.sleep(1)

        (
            os_name,
            os_version,
            browser_name,
            browser_version,
        ) = get_browser_info(driver)

        for record in records:
            datasetid = str(record.get("datasetid") or "").strip()
            strategy = str(record.get("strategy") or "").strip()
            test_status = str(record.get("status") or "UNKNOWN").upper()

            if not datasetid:
                message = (
                    f"SPLLT strategy {strategy!r} has no datasetid; "
                    "cannot scrape its scores."
                )
                ctx.logger.warning(message)

                csv_path = _write_result_row(
                    output_dir=output_dir,
                    datasetid=None,
                    subid=ctx.subid,
                    strategy=strategy,
                    status="FAIL - MISSING DATASETID",
                    scores={},
                    os_name=os_name,
                    os_version=os_version,
                    browser_name=browser_name,
                    browser_version=browser_version,
                )

                scrape_results.append({
                    "test_name": SPLLT_TEST_CODE,
                    "strategy": strategy,
                    "datasetid": None,
                    "status": test_status,
                    "scrape_status": "FAIL",
                    "reason": message,
                    "scores": {},
                    "csv_file": str(csv_path),
                })
                continue

            ctx.logger.info(
                "Scraping SPLLT strategy=%s datasetid=%s",
                strategy,
                datasetid,
            )

            try:
                open_scores_for_datasetid(driver, datasetid)
                scores = collect_spllt_scores(driver)

                missing_scores = [
                    score
                    for score in SPLLT_SCORE_COLUMNS
                    if score not in scores
                ]

                if not scores:
                    scrape_status = "FAIL"
                    csv_status = "FAIL - NO SPLLT SCORES FOUND"
                elif missing_scores:
                    scrape_status = "PARTIAL"
                    csv_status = "PARTIAL"
                else:
                    scrape_status = "PASS"
                    csv_status = test_status

                csv_path = _write_result_row(
                    output_dir=output_dir,
                    datasetid=datasetid,
                    subid=ctx.subid,
                    strategy=strategy,
                    status=csv_status,
                    scores=scores,
                    os_name=os_name,
                    os_version=os_version,
                    browser_name=browser_name,
                    browser_version=browser_version,
                )

                scrape_results.append({
                    "test_name": SPLLT_TEST_CODE,
                    "strategy": strategy,
                    "datasetid": datasetid,
                    "status": test_status,
                    "scrape_status": scrape_status,
                    "scores": scores,
                    "missing_scores": missing_scores,
                    "csv_file": str(csv_path),
                })

            except Exception as exc:
                ctx.logger.exception(
                    "SPLLT scrape failed for strategy=%s datasetid=%s: %s",
                    strategy,
                    datasetid,
                    exc,
                )

                csv_path = _write_result_row(
                    output_dir=output_dir,
                    datasetid=datasetid,
                    subid=ctx.subid,
                    strategy=strategy,
                    status=f"FAIL - SCRAPER {type(exc).__name__}",
                    scores={},
                    os_name=os_name,
                    os_version=os_version,
                    browser_name=browser_name,
                    browser_version=browser_version,
                )

                scrape_results.append({
                    "test_name": SPLLT_TEST_CODE,
                    "strategy": strategy,
                    "datasetid": datasetid,
                    "status": test_status,
                    "scrape_status": "FAIL",
                    "errors": [str(exc)],
                    "scores": {},
                    "csv_file": str(csv_path),
                })

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return scrape_results
