import time

from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from auth.login import selenium_login


def make_link(driver, webpage, battery, site, subid):
    """Fill the assessment form and return the generated link href."""

    battery_element = driver.find_element(By.ID, "batteryFormControlSelect")
    battery_element.send_keys(battery)
    time.sleep(1)

    site_element = driver.find_element(By.ID, "siteFormControlSelect")
    site_element.send_keys(site)
    time.sleep(1)

    subid_element = driver.find_element(By.ID, "subFormControlInput")
    subid_element.send_keys(subid)
    time.sleep(1)

    browser_type_element = driver.find_element(
        By.XPATH,
        "//form/div/div[4]/div/select",
    )
    browser_type_element.send_keys("browser")
    time.sleep(1)

    register_element = driver.find_element(By.XPATH, "//form/div[2]/button")
    ActionChains(driver).click(register_element).perform()

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//table/tbody/tr/td[7]/a")
            )
        )
    except Exception:
        time.sleep(3)

    link_element = driver.find_element(
        By.XPATH,
        "//table/tbody/tr/td[7]/a",
    )
    link = link_element.get_attribute("href")
    print(link)
    return link


def generate_link(
    selenium_driver,
    webpage,
    battery,
    site,
    subid,
    browser="chrome",
):
    """
    Generate and return a CNB assessment link.

    Environment loading is intentionally handled by runner.py through
    core.environment. This module should not independently load .env or
    .env.dev because that can override the environment selected for the run.
    """
    max_login_attempts = 3

    for attempt in range(1, max_login_attempts + 1):
        selenium_driver.get(webpage)
        time.sleep(3)

        if "New Assessment" in selenium_driver.page_source:
            return make_link(
                selenium_driver,
                webpage,
                battery,
                site,
                subid,
            )

        print(
            f"Not logged in (attempt {attempt}/{max_login_attempts}) "
            "— logging in..."
        )
        selenium_login(
            selenium_driver,
            webpage,
            browser=browser,
        )
        time.sleep(2)

        selenium_driver.get(webpage)
        time.sleep(3)

        if "New Assessment" in selenium_driver.page_source:
            return make_link(
                selenium_driver,
                webpage,
                battery,
                site,
                subid,
            )

    raise RuntimeError(
        f"Could not reach the assessment page after "
        f"{max_login_attempts} login attempts. "
        f"Last URL: {selenium_driver.current_url}"
    )
