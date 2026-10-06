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


SPLLT_TEST_CODES = {
    "spllt-a-1.00-ff",
    "spllt-b-1.00-ff",
    "spllt-c-1.00-ff",
    "spllt-d-1.00-ff",
}
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
            ).select_by_value("SELENIUM")
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


def _datasetid_from_form(form) -> str | None:
    """
    Return the dataset ID associated with one session-list form.
    """
    selectors = (
        "input[name='datasetid']",
        "input[name='dataset_id']",
        "input[id='datasetid']",
        "input[id='dataset_id']",
    )

    for selector in selectors:
        try:
            elements = form.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            elements = []

        for element in elements:
            try:
                value = (element.get_attribute("value") or "").strip()
            except Exception:
                value = ""

            if re.fullmatch(r"\d+", value):
                return value

    try:
        html = form.get_attribute("outerHTML") or ""
    except Exception:
        html = ""

    for pattern in (
        r'name=["\']datasetid["\'][^>]*value=["\'](\d+)["\']',
        r'value=["\'](\d+)["\'][^>]*name=["\']datasetid["\']',
        r'name=["\']dataset_id["\'][^>]*value=["\'](\d+)["\']',
        r'value=["\'](\d+)["\'][^>]*name=["\']dataset_id["\']',
        r'datasetid(?:=|%3D)(\d+)',
        r'dataset_id(?:=|%3D)(\d+)',
    ):
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def _find_view_button_for_datasetid(driver, datasetid: str):
    """
    Find the exact View button whose ancestor form belongs to datasetid.
    """
    expected = str(datasetid).strip()
    seen: list[str] = []

    buttons = driver.find_elements(
        By.XPATH,
        "//input[@name='ViewSession' and @value='View']",
    )

    for button in buttons:
        try:
            form = button.find_element(By.XPATH, "./ancestor::form[1]")
        except Exception:
            continue

        observed = _datasetid_from_form(form)

        if observed:
            seen.append(observed)

        if observed == expected:
            return button

    raise RuntimeError(
        f"Could not find ViewSession button for datasetid={expected}. "
        f"Dataset IDs attached to visible View forms: {seen}"
    )


def _validate_datasetid(driver, datasetid: str, timeout: float = 20.0) -> None:
    """
    Confirm that the currently open CNB page belongs to the requested dataset.
    """
    expected = str(datasetid).strip()

    def matching_dataset(d):
        for element in d.find_elements(
            By.CSS_SELECTOR,
            "input[name='datasetid'], input[name='dataset_id']",
        ):
            try:
                observed = (element.get_attribute("value") or "").strip()
            except Exception:
                continue

            if observed == expected:
                return True

        try:
            body_text = d.find_element(By.TAG_NAME, "body").text or ""
        except Exception:
            body_text = ""

        return (
            expected in body_text
            and "Dataset ID:" in body_text
        )

    WebDriverWait(driver, timeout).until(matching_dataset)


def _target_scores_present(driver) -> bool:
    """
    Return True only when actual SPLLT target score rows are present.
    """
    target_names = {name.upper() for name in SPLLT_SCORE_COLUMNS}

    for row in driver.find_elements(By.CSS_SELECTOR, "tr.row1, tr.row2"):
        cells = row.find_elements(By.TAG_NAME, "td")

        if len(cells) < 2:
            continue

        score_name = _normalize_score_name(cells[0].text).upper()

        if score_name in target_names:
            return True

    return False


def _close_extra_windows(driver, keep_handle: str) -> None:
    """
    Close result popups left by prior session views and return to keep_handle.
    """
    for handle in list(driver.window_handles):
        if handle == keep_handle:
            continue

        try:
            driver.switch_to.window(handle)
            driver.close()
        except Exception:
            pass

    driver.switch_to.window(keep_handle)


def open_scores_for_datasetid(
    driver,
    subid: str,
    datasetid: str,
    test_code: str,
    logger=None,
) -> None:
    """
    Open one exact SPLLT dataset by following CNB's normal UI:

        Display Test Sessions
        -> search subid
        -> List Session(s)
        -> exact dataset's View button
        -> Display Test Scores
        -> select SPLLT
        -> List Scores

    This avoids direct hand-built POSTs to results.pl.
    """
    datasetid = str(datasetid).strip()
    subid = str(subid or "").strip()
    test_code = str(test_code or "").strip().lower()

    if test_code not in SPLLT_TEST_CODES:
        raise ValueError(
            f"Unsupported SPLLT test code {test_code!r}; "
            f"expected one of {sorted(SPLLT_TEST_CODES)}"
        )

    if not datasetid:
        raise ValueError("datasetid is required")

    if not subid:
        raise ValueError("subid is required")

    base_handle = driver.window_handles[0]
    _close_extra_windows(driver, base_handle)

    if logger:
        logger.info(
            "SPLLT scraper opening session list for subid=%s datasetid=%s",
            subid,
            datasetid,
        )

    driver.get(RESULTS_URL)
    WebDriverWait(driver, 20).until(_document_ready)

    try:
        field = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.NAME, "multi_subid"))
        )
    except Exception:
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
        ).select_by_value("SELENIUM")
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

    view_button = _find_view_button_for_datasetid(
        driver,
        datasetid,
    )

    if logger:
        logger.info(
            "SPLLT scraper found exact ViewSession button for datasetid=%s",
            datasetid,
        )

    old_handles = set(driver.window_handles)
    old_url = driver.current_url

    _safe_click(driver, view_button)

    try:
        WebDriverWait(driver, 12).until(
            lambda d: (
                len(d.window_handles) > len(old_handles)
                or d.current_url != old_url
                or len(
                    d.find_elements(
                        By.XPATH,
                        "//a[contains(@onclick, 'display_scores')]",
                    )
                ) > 0
            )
        )
    except Exception:
        pass

    new_handles = set(driver.window_handles)

    if len(new_handles) > len(old_handles):
        new_handle = list(new_handles - old_handles)[0]
        driver.switch_to.window(new_handle)

        if logger:
            logger.info(
                "SPLLT scraper switched to ViewSession popup for datasetid=%s",
                datasetid,
            )

    WebDriverWait(driver, 20).until(_document_ready)
    _validate_datasetid(driver, datasetid, timeout=20)

    if logger:
        logger.info(
            "SPLLT scraper validated session datasetid=%s",
            datasetid,
        )

    if _target_scores_present(driver):
        if logger:
            logger.info(
                "SPLLT target scores already visible for datasetid=%s",
                datasetid,
            )
        return

    score_links = driver.find_elements(
        By.XPATH,
        "//a[contains(@onclick, 'display_scores')]",
    )

    score_link = next(
        (
            element
            for element in score_links
            if element.is_displayed()
        ),
        None,
    )

    if score_link is None:
        raise RuntimeError(
            f"Display Test Scores link not found for datasetid={datasetid}. "
            f"Current URL: {driver.current_url}"
        )

    _safe_click(driver, score_link)

    WebDriverWait(driver, 20).until(_document_ready)
    _validate_datasetid(driver, datasetid, timeout=20)

    if logger:
        logger.info(
            "SPLLT scraper opened Display Test Scores for datasetid=%s",
            datasetid,
        )

    if not _target_scores_present(driver):
        try:
            test_select = Select(driver.find_element(By.NAME, "test"))
            test_select.select_by_value(test_code)
        except Exception as exc:
            raise RuntimeError(
                f"Could not select {test_code} on score page for "
                f"datasetid={datasetid}: {exc}"
            ) from exc

        list_scores_btn = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.NAME, "ListScores"))
        )
        _safe_click(driver, list_scores_btn)

        WebDriverWait(driver, 20).until(_document_ready)
        _validate_datasetid(driver, datasetid, timeout=20)

    WebDriverWait(driver, 20).until(_target_scores_present)

    if logger:
        logger.info(
            "SPLLT target score rows loaded for datasetid=%s",
            datasetid,
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
    test_name: str,
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
        "test_name": test_name,
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
        if str(record.get("test_name") or "").strip().lower()
        in SPLLT_TEST_CODES
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
            test_name = str(record.get("test_name") or "").strip().lower()
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
                    test_name=test_name,
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
                    "test_name": test_name,
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
                open_scores_for_datasetid(
                    driver,
                    subid=ctx.subid,
                    datasetid=datasetid,
                    test_code=test_name,
                    logger=ctx.logger,
                )
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
                    test_name=test_name,
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
                    "test_name": test_name,
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
                    test_name=test_name,
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
                    "test_name": test_name,
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