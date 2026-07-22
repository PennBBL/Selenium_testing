import csv
import time
from datetime import datetime
from pathlib import Path

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

from auth.login import selenium_login as _base_selenium_login
from core.driver_factory import build_chrome_driver


RESULTS_URL = "https://penncnp-dev.pmacs.upenn.edu/results.pl?op=view_sessions&adminid=mruganks"
LOGIN_URL = "https://penncnp-dev.pmacs.upenn.edu/assessments.pl"


# ---------------------------------------------------------------------
# Login / browser info
# ---------------------------------------------------------------------

def do_login(driver, login_url: str, post_login_url: str | None = None):
    _base_selenium_login(driver, login_url)

    if post_login_url:
        time.sleep(2)
        driver.get(post_login_url)


def get_browser_info(driver):
    try:
        caps = driver.capabilities

        browser_name = (caps.get("browserName") or "unknown").lower()
        browser_version = caps.get("browserVersion") or caps.get("version", "unknown")
        platform_raw = (caps.get("platformName") or caps.get("platform", "unknown")).lower()

        try:
            ua = driver.execute_script("return navigator.userAgent;")
            os_name, os_version = _parse_os_from_ua(ua, platform_raw)
        except Exception:
            os_name, os_version = platform_raw, "unknown"

        return os_name, os_version, browser_name, browser_version

    except Exception:
        return "unknown", "unknown", "unknown", "unknown"


def _parse_os_from_ua(ua: str, fallback: str):
    import re

    lower = ua.lower()

    if "mac os x" in lower:
        m = re.search(r"mac os x ([\d_]+)", lower)
        return "macos", m.group(1).replace("_", ".") if m else "unknown"

    if "windows nt" in lower:
        m = re.search(r"windows nt ([\d.]+)", lower)
        return "windows", m.group(1) if m else "unknown"

    if "linux" in lower:
        return "linux", ""

    return fallback or "unknown", "unknown"


# ---------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------

def _output_csv_path(config, output_dir=None):
    """
    Return the full CSV path.

    If output_dir is provided, CSVs go inside that folder.
    If not provided, this preserves old behavior and writes to cwd.
    """
    if output_dir is None:
        output_dir = Path.cwd()
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    return output_dir / config.csv_file


def _base_fieldnames(config):
    return [
        "timestamp",
        "test_name",
        "subid",
        "strategy",
        "os_name",
        "os_version",
        "browser_name",
        "browser_version",
        "test_result",
    ] + list(config.target_scores)


def append_csv(config, row, output_dir=None):
    output_csv = _output_csv_path(config, output_dir)
    fieldnames = _base_fieldnames(config)

    file_exists = output_csv.exists()

    with output_csv.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)

    print(f"Wrote row to {output_csv}")


def _empty_row(config):
    return {col: "" for col in _base_fieldnames(config)}


def write_failure_row(
    config,
    subid,
    strategy,
    os_name,
    os_version,
    browser_name,
    browser_version,
    test_result="FAIL",
    output_dir=None,
):
    row = _empty_row(config)

    row.update({
        "timestamp": datetime.now().isoformat(),
        "test_name": config.test_name,
        "subid": subid,
        "strategy": strategy,
        "os_name": os_name,
        "os_version": os_version,
        "browser_name": browser_name,
        "browser_version": browser_version,
        "test_result": test_result,
    })

    append_csv(config, row, output_dir=output_dir)


def write_scores_row(
    config,
    subid,
    strategy,
    scores,
    os_name,
    os_version,
    browser_name,
    browser_version,
    test_result="PASS",
    output_dir=None,
):
    row = _empty_row(config)

    row.update({
        "timestamp": datetime.now().isoformat(),
        "test_name": config.test_name,
        "subid": subid,
        "strategy": strategy,
        "os_name": os_name,
        "os_version": os_version,
        "browser_name": browser_name,
        "browser_version": browser_version,
        "test_result": test_result,
    })

    row.update(scores)

    append_csv(config, row, output_dir=output_dir)


# ---------------------------------------------------------------------
# Results page navigation
# ---------------------------------------------------------------------

def _document_ready(driver):
    try:
        return driver.execute_script("return document.readyState") == "complete"
    except Exception:
        return False


def _has_display_scores_link(driver):
    try:
        links = driver.find_elements(By.XPATH, "//a[contains(@onclick, 'display_scores')]")
        return any(link.is_displayed() for link in links)
    except Exception:
        return False


def _safe_click(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    time.sleep(0.2)
    driver.execute_script("arguments[0].click();", element)


def open_scores_page(driver, subid):
    """
    Login/search/open the subject's score page once.

    After this function succeeds, the browser should already be on the page
    where all battery scores are listed.
    """
    driver.get(RESULTS_URL)
    time.sleep(2)

    if "op=view_sessions" not in driver.current_url:
        do_login(driver, LOGIN_URL, RESULTS_URL)
        time.sleep(2)
        driver.get(RESULTS_URL)

    field = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.NAME, "multi_subid"))
    )
    field.clear()
    field.send_keys(subid)

    try:
        Select(driver.find_element(By.NAME, "multi_siteid")).select_by_value("TEST")
    except Exception:
        pass

    list_sessions_btn = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//input[@value='   List Session(s)   ']")
        )
    )
    _safe_click(driver, list_sessions_btn)

    view_btn = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//input[@name='ViewSession' and @value='View']")
        )
    )

    old_handles = set(driver.window_handles)
    old_url = driver.current_url

    _safe_click(driver, view_btn)

    # Robust wait:
    # - Some environments open a new window.
    # - Some may reuse the current window.
    # - Do not use >= here; that returns immediately.
    try:
        WebDriverWait(driver, 12).until(
            lambda d: (
                len(d.window_handles) > len(old_handles)
                or d.current_url != old_url
                or _has_display_scores_link(d)
            )
        )
    except TimeoutException:
        # Continue; the next explicit waits will tell us what failed.
        pass

    new_handles = set(driver.window_handles)

    if len(new_handles) > len(old_handles):
        new_window = list(new_handles - old_handles)[0]
        driver.switch_to.window(new_window)

    WebDriverWait(driver, 20).until(_document_ready)

    score_link = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(@onclick, 'display_scores')]")
        )
    )
    _safe_click(driver, score_link)

    WebDriverWait(driver, 20).until(_document_ready)

    list_scores_btn = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.NAME, "ListScores"))
    )
    _safe_click(driver, list_scores_btn)

    WebDriverWait(driver, 20).until(_document_ready)

    # Wait until at least some score rows exist.
    WebDriverWait(driver, 20).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "tr.row1, tr.row2")) > 0
    )

    time.sleep(1)


# ---------------------------------------------------------------------
# Score collection
# ---------------------------------------------------------------------

def _normalize_score_name(score_name: str):
    return score_name.strip().split("(")[0].strip()


def collect_scores_from_open_page(driver, config):
    """
    Scrape the already-open score page for one test config.

    This does not navigate, log in, search, or open a new browser.
    """
    scores = {}

    target_lookup = {
        target.strip().upper(): target
        for target in config.target_scores
    }

    rows = driver.find_elements(By.CSS_SELECTOR, "tr.row1, tr.row2")

    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")

        if len(cells) < 2:
            continue

        raw_score_name = cells[0].text.strip()
        score_name = _normalize_score_name(raw_score_name)
        score_val = cells[1].text.strip()

        canonical_target = target_lookup.get(score_name.upper())

        if canonical_target:
            scores[canonical_target] = score_val

    return scores


# ---------------------------------------------------------------------
# Test result helpers
# ---------------------------------------------------------------------

def _is_fail_result(test_result):
    """
    Supports:
        "FAIL"
        {"status": "FAIL"}
        TestRunResult(status="FAIL")
    """
    if isinstance(test_result, str):
        return test_result.upper() == "FAIL"

    if isinstance(test_result, dict):
        return str(test_result.get("status", "")).upper() == "FAIL"

    if hasattr(test_result, "status"):
        return str(test_result.status).upper() == "FAIL"

    return False


def _record_status(record):
    if isinstance(record, dict):
        return str(record.get("status", "UNKNOWN")).upper()

    if hasattr(record, "status"):
        return str(record.status).upper()

    return "UNKNOWN"


def _record_test_name(record):
    if isinstance(record, dict):
        return record.get("test_name")

    if hasattr(record, "test_name"):
        return record.test_name

    return None


# ---------------------------------------------------------------------
# Single-test scraper
# ---------------------------------------------------------------------

def scrape_scores(
    driver,
    subid,
    strategy,
    config,
    os_name,
    os_version,
    browser_name,
    browser_version,
    output_dir=None,
):
    """
    Backward-compatible single-test scraping function.

    It opens the score page, then scrapes one config.
    """
    open_scores_page(driver, subid)

    scores = collect_scores_from_open_page(driver, config)

    if not scores:
        return None

    write_scores_row(
        config=config,
        subid=subid,
        strategy=strategy,
        scores=scores,
        os_name=os_name,
        os_version=os_version,
        browser_name=browser_name,
        browser_version=browser_version,
        test_result="PASS",
        output_dir=output_dir,
    )

    return scores


def run_configured_scraper(
    subid,
    strategy,
    test_result,
    config,
    browser="chrome",
    headless=False,
    output_dir=None,
):
    """
    Original one-test scraper behavior.
    Kept for individual test use and fallback use.

    CSV output:
        output_dir/config.csv_file
    """
    driver = build_chrome_driver()
    os_name, os_version, browser_name, browser_version = get_browser_info(driver)

    if _is_fail_result(test_result):
        driver.quit()

        write_failure_row(
            config=config,
            subid=subid,
            strategy=strategy,
            os_name=os_name,
            os_version=os_version,
            browser_name=browser_name,
            browser_version=browser_version,
            test_result="FAIL",
            output_dir=output_dir,
        )

        return True

    try:
        try:
            do_login(driver, LOGIN_URL, RESULTS_URL)

            scores = scrape_scores(
                driver=driver,
                subid=subid,
                strategy=strategy,
                config=config,
                os_name=os_name,
                os_version=os_version,
                browser_name=browser_name,
                browser_version=browser_version,
                output_dir=output_dir,
            )

            if scores:
                return True

            write_failure_row(
                config=config,
                subid=subid,
                strategy=strategy,
                os_name=os_name,
                os_version=os_version,
                browser_name=browser_name,
                browser_version=browser_version,
                test_result="PASS (test) / FAIL (scraper)",
                output_dir=output_dir,
            )

            return False

        except Exception as exc:
            write_failure_row(
                config=config,
                subid=subid,
                strategy=strategy,
                os_name=os_name,
                os_version=os_version,
                browser_name=browser_name,
                browser_version=browser_version,
                test_result=f"PASS (test) / FAIL (scraper exception: {type(exc).__name__})",
                output_dir=output_dir,
            )

            print(f"Scraper exception: {exc}")
            return False

    finally:
        driver.quit()


# ---------------------------------------------------------------------
# Battery scraper
# ---------------------------------------------------------------------

def _write_rows_when_score_page_open_fails(
    test_results,
    configs,
    subid,
    strategy,
    os_name,
    os_version,
    browser_name,
    browser_version,
    output_dir,
    exc,
):
    """
    If we cannot open the score page at all, still write CSV rows
    for every known config so you do not end up with no CSVs.
    """
    scraped = []

    for record in test_results:
        test_name = _record_test_name(record)
        status = _record_status(record)

        if not test_name:
            scraped.append({
                "test_name": None,
                "status": status,
                "scrape_status": "MISSING_TEST_NAME",
                "scores": {},
                "error": str(exc),
            })
            continue

        config = configs.get(test_name)

        if not config:
            scraped.append({
                "test_name": test_name,
                "status": status,
                "scrape_status": "NO_RESULTS_CONFIG",
                "scores": {},
                "error": str(exc),
            })
            continue

        if status == "FAIL":
            result_text = "FAIL"
            scrape_status = "FAIL_ROW_WRITTEN_AFTER_SCORE_PAGE_ERROR"
        else:
            result_text = f"{status} (test) / FAIL (scraper open_scores_page: {type(exc).__name__})"
            scrape_status = "SCORE_PAGE_OPEN_FAILED"

        write_failure_row(
            config=config,
            subid=subid,
            strategy=strategy,
            os_name=os_name,
            os_version=os_version,
            browser_name=browser_name,
            browser_version=browser_version,
            test_result=result_text,
            output_dir=output_dir,
        )

        scraped.append({
            "test_name": test_name,
            "status": status,
            "scrape_status": scrape_status,
            "scores": {},
            "csv_file": str(_output_csv_path(config, output_dir)),
            "error": str(exc),
        })

    return scraped


def run_configured_battery_scraper(
    subid,
    strategy,
    test_results,
    configs,
    browser="chrome",
    headless=False,
    output_dir=None,
):
    """
    Battery-level scraper.

    Opens Chrome once, logs in once, opens the score page once,
    then scrapes all known administered tests from that same page.

    CSV output:
        output_dir/config.csv_file
    """
    driver = build_chrome_driver()
    os_name, os_version, browser_name, browser_version = get_browser_info(driver)

    scraped = []

    try:
        do_login(driver, LOGIN_URL, RESULTS_URL)

        try:
            open_scores_page(driver, subid)
        except Exception as exc:
            print(f"Failed to open score page: {exc}")

            return _write_rows_when_score_page_open_fails(
                test_results=test_results,
                configs=configs,
                subid=subid,
                strategy=strategy,
                os_name=os_name,
                os_version=os_version,
                browser_name=browser_name,
                browser_version=browser_version,
                output_dir=output_dir,
                exc=exc,
            )

        for record in test_results:
            test_name = _record_test_name(record)
            status = _record_status(record)

            if not test_name:
                scraped.append({
                    "test_name": None,
                    "status": status,
                    "scrape_status": "MISSING_TEST_NAME",
                    "scores": {},
                })
                continue

            config = configs.get(test_name)

            if not config:
                scraped.append({
                    "test_name": test_name,
                    "status": status,
                    "scrape_status": "NO_RESULTS_CONFIG",
                    "scores": {},
                })
                continue

            if status == "FAIL":
                write_failure_row(
                    config=config,
                    subid=subid,
                    strategy=strategy,
                    os_name=os_name,
                    os_version=os_version,
                    browser_name=browser_name,
                    browser_version=browser_version,
                    test_result="FAIL",
                    output_dir=output_dir,
                )

                scraped.append({
                    "test_name": test_name,
                    "status": "FAIL",
                    "scrape_status": "FAIL_ROW_WRITTEN",
                    "scores": {},
                    "csv_file": str(_output_csv_path(config, output_dir)),
                })
                continue

            try:
                scores = collect_scores_from_open_page(driver, config)

                if scores:
                    write_scores_row(
                        config=config,
                        subid=subid,
                        strategy=strategy,
                        scores=scores,
                        os_name=os_name,
                        os_version=os_version,
                        browser_name=browser_name,
                        browser_version=browser_version,
                        test_result="PASS",
                        output_dir=output_dir,
                    )

                    scraped.append({
                        "test_name": test_name,
                        "status": status,
                        "scrape_status": "PASS",
                        "scores": scores,
                        "csv_file": str(_output_csv_path(config, output_dir)),
                    })

                else:
                    write_failure_row(
                        config=config,
                        subid=subid,
                        strategy=strategy,
                        os_name=os_name,
                        os_version=os_version,
                        browser_name=browser_name,
                        browser_version=browser_version,
                        test_result=f"{status} (test) / FAIL (scraper no scores)",
                        output_dir=output_dir,
                    )

                    scraped.append({
                        "test_name": test_name,
                        "status": status,
                        "scrape_status": "NO_SCORES_FOUND",
                        "scores": {},
                        "csv_file": str(_output_csv_path(config, output_dir)),
                    })

            except Exception as exc:
                write_failure_row(
                    config=config,
                    subid=subid,
                    strategy=strategy,
                    os_name=os_name,
                    os_version=os_version,
                    browser_name=browser_name,
                    browser_version=browser_version,
                    test_result=f"{status} (test) / FAIL (scraper exception: {type(exc).__name__})",
                    output_dir=output_dir,
                )

                scraped.append({
                    "test_name": test_name,
                    "status": status,
                    "scrape_status": "SCRAPER_EXCEPTION",
                    "scores": {},
                    "csv_file": str(_output_csv_path(config, output_dir)),
                    "error": str(exc),
                })

        return scraped

    finally:
        driver.quit()