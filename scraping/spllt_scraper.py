from __future__ import annotations

import csv
import re
import time
from datetime import datetime
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

from core.driver_factory import build_chrome_driver
from scraping.base_scraper import (
    LOGIN_URL,
    RESULTS_URL,
    do_login,
    get_browser_info,
)


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

BASE_RESULTS_URL = RESULTS_URL.split("?", 1)[0]

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


# ---------------------------------------------------------------------
# Dataset-ID discovery for SPLLT suites
# ---------------------------------------------------------------------


def _extract_datasetids_from_session_list(driver) -> list[str]:
    """
    Extract every dataset ID visible in the session-list page.

    CNB session rows have changed markup over time, so this intentionally
    checks hidden inputs, ViewSession ancestor forms, and page HTML.
    """
    found: set[str] = set()

    # Most reliable case: hidden/form inputs containing datasetid.
    for element in driver.find_elements(
        By.CSS_SELECTOR,
        "input[name='datasetid'], input[name='dataset_id'], "
        "input[id='datasetid'], input[id='dataset_id']",
    ):
        try:
            value = (element.get_attribute("value") or "").strip()
            if re.fullmatch(r"\d+", value):
                found.add(value)
        except Exception:
            pass

    # Inspect each View button's form. This helps when the dataset field is
    # not globally easy to address but lives inside each session row/form.
    for button in driver.find_elements(
        By.XPATH,
        "//input[@name='ViewSession' and @value='View']",
    ):
        try:
            form = button.find_element(By.XPATH, "./ancestor::form[1]")
            html = form.get_attribute("outerHTML") or ""
        except Exception:
            html = ""

        for pattern in (
            r'name=["\']datasetid["\'][^>]*value=["\'](\d+)["\']',
            r'value=["\'](\d+)["\'][^>]*name=["\']datasetid["\']',
            r'datasetid(?:=|%3D)(\d+)',
        ):
            found.update(re.findall(pattern, html, flags=re.IGNORECASE))

    # Final fallback: scan the full page source for explicit datasetid
    # references. Avoid generic digit matching so unrelated numbers are not
    # interpreted as dataset IDs.
    source = driver.page_source or ""
    for pattern in (
        r'name=["\']datasetid["\'][^>]*value=["\'](\d+)["\']',
        r'value=["\'](\d+)["\'][^>]*name=["\']datasetid["\']',
        r'datasetid(?:=|%3D)(\d+)',
        r'datasetid\s*["\']?\s*[:=]\s*["\']?(\d+)',
    ):
        found.update(re.findall(pattern, source, flags=re.IGNORECASE))

    return sorted(found, key=lambda value: int(value))


def get_datasetids_for_subid(subid: str) -> list[str]:
    """
    Return all dataset IDs currently listed for one subject ID.

    This is used by the SPLLT suite because one Selenium suite run creates
    multiple independent battery administrations for the same subid.
    """
    driver = build_chrome_driver()

    try:
        do_login(driver, LOGIN_URL, RESULTS_URL)
        time.sleep(1)
        driver.get(RESULTS_URL)

        field = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.NAME, "multi_subid"))
        )
        field.clear()
        field.send_keys(subid)

        try:
            Select(
                driver.find_element(By.NAME, "multi_siteid")
            ).select_by_value("TEST")
        except Exception:
            pass

        list_sessions_btn = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//input[@value='   List Session(s)   ']")
            )
        )
        _safe_click(driver, list_sessions_btn)

        WebDriverWait(driver, 20).until(
            lambda d: len(
                d.find_elements(
                    By.XPATH,
                    "//input[@name='ViewSession' and @value='View']",
                )
            ) > 0
        )

        time.sleep(0.5)
        return _extract_datasetids_from_session_list(driver)

    finally:
        try:
            driver.quit()
        except Exception:
            pass


# ---------------------------------------------------------------------
# Open one exact dataset score page
# ---------------------------------------------------------------------


def _post_results_form(driver, datasetid: str) -> None:
    """
    Submit the same fields as the CNB "List Scores" form.

    The live score-page HTML shows that the form submits:
        op=display_scores
        datasetid=<exact dataset>
        test=spllt-a-1.00-ff
        ListScores=List Scores

    Posting only op + datasetid is not equivalent to clicking the real
    List Scores button, because the clicked submit button contributes its
    own name/value to the POST body.
    """
    driver.execute_script(
        """
        const action = arguments[0];
        const datasetid = arguments[1];
        const testCode = arguments[2];

        const form = document.createElement('form');
        form.method = 'POST';
        form.action = action;

        function addField(name, value) {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = name;
            input.value = value;
            form.appendChild(input);
        }

        addField('op', 'display_scores');
        addField('datasetid', datasetid);
        addField('test', testCode);
        addField('ListScores', 'List Scores');

        document.body.appendChild(form);
        form.submit();
        """,
        BASE_RESULTS_URL,
        str(datasetid),
        SPLLT_TEST_CODE,
    )

    # Allow the POST navigation to begin, then wait for the destination
    # document to finish loading.
    time.sleep(0.4)
    WebDriverWait(driver, 30).until(_document_ready)


def _validate_datasetid(driver, datasetid: str) -> None:
    expected = str(datasetid).strip()

    def matching_dataset(d):
        # Primary check: hidden datasetid field on the score page.
        for element in d.find_elements(
            By.CSS_SELECTOR,
            "input[name='datasetid']",
        ):
            observed = (element.get_attribute("value") or "").strip()
            if observed == expected:
                return True

        # Fallback: the Test Information table visibly prints Dataset ID.
        body_text = d.find_element(By.TAG_NAME, "body").text or ""
        return expected in body_text and "Dataset ID:" in body_text

    WebDriverWait(driver, 30).until(matching_dataset)


def _score_page_loaded(driver) -> bool:
    """
    Confirm that the SPLLT score section, not merely generic row markup,
    has loaded.

    The page has many tr.row1/tr.row2 elements before the score table, so
    generic row-count checks are not sufficient.
    """
    body_text = driver.find_element(By.TAG_NAME, "body").text or ""

    return (
        "Test Scores:" in body_text
        and SPLLT_TEST_CODE in body_text
    )


def open_scores_for_datasetid(driver, datasetid: str) -> None:
    """
    Open the score page for one exact SPLLT dataset.

    This submits the canonical List Scores POST in one step and avoids the
    previous two-stage POST-then-click sequence that was timing out.
    """
    datasetid = str(datasetid).strip()

    if not datasetid:
        raise ValueError("datasetid is required")

    _post_results_form(
        driver,
        datasetid=datasetid,
    )

    _validate_datasetid(driver, datasetid)

    WebDriverWait(driver, 30).until(_score_page_loaded)


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


# ---------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------


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

    Output:
        <ctx.output_dir>/spllt_results.csv
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
        # Authenticate exactly once. Do not call do_login again merely because
        # a direct results-page shape is unexpected.
        do_login(driver, LOGIN_URL, RESULTS_URL)
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
