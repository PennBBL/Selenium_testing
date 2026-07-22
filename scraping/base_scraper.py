import csv
import time
from datetime import datetime
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

from auth.login import selenium_login as _base_selenium_login
from core.driver_factory import build_chrome_driver


RESULTS_URL = "https://penncnp-dev.pmacs.upenn.edu/results.pl?op=view_sessions&adminid=mruganks"
LOGIN_URL = "https://penncnp-dev.pmacs.upenn.edu/assessments.pl"


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


def append_csv(config, row):
    output_csv = Path(config.csv_file)

    fieldnames = [
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

    file_exists = output_csv.exists()

    with output_csv.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)

    print(f"Wrote row to {output_csv}")


def write_failure_row(
    config,
    subid,
    strategy,
    os_name,
    os_version,
    browser_name,
    browser_version,
    test_result="FAIL",
):
    row = {
        col: ""
        for col in [
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
    }

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

    append_csv(config, row)


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

    field = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.NAME, "multi_subid"))
    )
    field.clear()
    field.send_keys(subid)

    try:
        Select(driver.find_element(By.NAME, "multi_siteid")).select_by_value("TEST")
    except Exception:
        pass

    driver.find_element(By.XPATH, "//input[@value='   List Session(s)   ']").click()
    time.sleep(3)

    view_btn = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//input[@name='ViewSession' and @value='View']")
        )
    )

    old_handles = set(driver.window_handles)
    driver.execute_script("arguments[0].click();", view_btn)

    WebDriverWait(driver, 10).until(
        lambda d: len(d.window_handles) >= len(old_handles)
    )

    new_handles = set(driver.window_handles)

    if len(new_handles) > len(old_handles):
        driver.switch_to.window(list(new_handles - old_handles)[0])

    WebDriverWait(driver, 15).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

    link = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(@onclick, 'display_scores')]")
        )
    )
    driver.execute_script("arguments[0].click();", link)

    WebDriverWait(driver, 15).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

    WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.NAME, "ListScores"))
    ).click()

    time.sleep(2)


def collect_scores_from_open_page(driver, config):
    """
    Scrape the already-open score page for one test config.

    This does not navigate, log in, search, or open a new browser.
    """
    scores = {}

    rows = driver.find_elements(By.CSS_SELECTOR, "tr.row1, tr.row2")

    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")

        if len(cells) >= 2:
            score_name = cells[0].text.strip().split("(")[0].strip()
            score_val = cells[1].text.strip()

            if score_name in config.target_scores:
                scores[score_name] = score_val

    return scores


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
):
    csv_row = {
        col: ""
        for col in [
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
    }

    csv_row.update({
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

    csv_row.update(scores)
    append_csv(config, csv_row)


def scrape_scores(
    driver,
    subid,
    strategy,
    config,
    os_name,
    os_version,
    browser_name,
    browser_version,
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
    )

    return scores


def _is_fail_result(test_result):
    """
    Supports both old style:
        test_result == "FAIL"

    and current dict style:
        {"status": "FAIL"}
    """
    if isinstance(test_result, str):
        return test_result.upper() == "FAIL"

    if isinstance(test_result, dict):
        return str(test_result.get("status", "")).upper() == "FAIL"

    return False


def run_configured_scraper(
    subid,
    strategy,
    test_result,
    config,
    browser="chrome",
    headless=False,
):
    """
    Original one-test scraper behavior.
    Kept for individual test use and fallback use.
    """
    driver = build_chrome_driver()
    os_name, os_version, browser_name, browser_version = get_browser_info(driver)

    if _is_fail_result(test_result):
        driver.quit()
        write_failure_row(
            config,
            subid,
            strategy,
            os_name,
            os_version,
            browser_name,
            browser_version,
            "FAIL",
        )
        return True

    try:
        do_login(driver, LOGIN_URL, RESULTS_URL)

        scores = scrape_scores(
            driver,
            subid,
            strategy,
            config,
            os_name,
            os_version,
            browser_name,
            browser_version,
        )

        if scores:
            return True

        write_failure_row(
            config,
            subid,
            strategy,
            os_name,
            os_version,
            browser_name,
            browser_version,
            "PASS (test) / FAIL (scraper)",
        )
        return False

    finally:
        driver.quit()


def run_configured_battery_scraper(
    subid,
    strategy,
    test_results,
    configs,
    browser="chrome",
    headless=False,
):
    """
    Battery-level scraper.

    Opens Chrome once, logs in once, opens the score page once,
    then scrapes all known administered tests from that same page.
    """
    driver = build_chrome_driver()
    os_name, os_version, browser_name, browser_version = get_browser_info(driver)

    scraped = []

    try:
        do_login(driver, LOGIN_URL, RESULTS_URL)
        open_scores_page(driver, subid)

        for record in test_results:
            test_name = record["test_name"]
            config = configs.get(test_name)

            if not config:
                scraped.append({
                    "test_name": test_name,
                    "status": status,
                    "scrape_status": "NO_RESULTS_CONFIG",
                    "scores": {},
                })
                continue
            status = str(record.get("status", "UNKNOWN")).upper()

            if status == "FAIL":
                write_failure_row(
                    config,
                    subid,
                    strategy,
                    os_name,
                    os_version,
                    browser_name,
                    browser_version,
                    "FAIL",
                )

                scraped.append({
                    "test_name": test_name,
                    "status": "FAIL",
                    "scrape_status": "FAIL_ROW_WRITTEN",
                    "scores": {},
                })
                continue

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
                )

                scraped.append({
                    "test_name": test_name,
                    "status": "PASS",
                    "scrape_status": "PASS",
                    "scores": scores,
                    "csv_file": config.csv_file,
                })

            else:
                write_failure_row(
                    config,
                    subid,
                    strategy,
                    os_name,
                    os_version,
                    browser_name,
                    browser_version,
                    "PASS (test) / FAIL (scraper)",
                )

                scraped.append({
                    "test_name": test_name,
                    "status": status,
                    "scrape_status": "NO_SCORES_FOUND",
                    "scores": {},
                    "csv_file": config.csv_file,
                })

        return scraped

    finally:
        driver.quit()