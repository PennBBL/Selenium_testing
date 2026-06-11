import time
from selenium.webdriver.common.by import By
from selenium.webdriver import ActionChains
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv
import os
from auth.login import selenium_login

load_dotenv()


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

    browser_type_element = driver.find_element(By.XPATH, "//form/div/div[4]/div/select")
    browser_type_element.send_keys("browser")
    time.sleep(1)

    register_element = driver.find_element(By.XPATH, "//form/div[2]/button")
    ActionChains(driver).click(register_element).perform()

    # Wait for the link to appear rather than a fixed sleep.
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//table/tbody/tr/td[7]/a"))
        )
    except Exception:
        time.sleep(3)   # fallback if wait fails

    link_element = driver.find_element(By.XPATH, "//table/tbody/tr/td[7]/a")
    link = link_element.get_attribute("href")
    print(link)
    return link


def generate_link(selenium_driver, webpage, battery, site, subid, browser="chrome"):
    """
    Generate and return a CNB assessment link.

    Replaces the original recursive implementation with an explicit loop so
    that Safari (or any other browser) cannot cause infinite recursion when
    the post-login page check keeps failing.

    Parameters
    ----------
    browser : passed through to selenium_login so it can apply the
              Safari ITP cookie-survival fix when needed.
    """
    MAX_LOGIN_ATTEMPTS = 3

    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        selenium_driver.get(webpage)
        time.sleep(3)

        if "New Assessment" in selenium_driver.page_source:
            return make_link(selenium_driver, webpage, battery, site, subid)

        print(f"Not logged in (attempt {attempt}/{MAX_LOGIN_ATTEMPTS}) — logging in...")
        selenium_login(selenium_driver, webpage, browser=browser)
        time.sleep(2)

        # After login, reload the target page and check once more before
        # looping — avoids an extra redundant get() on the next iteration.
        selenium_driver.get(webpage)
        time.sleep(3)

        if "New Assessment" in selenium_driver.page_source:
            return make_link(selenium_driver, webpage, battery, site, subid)

    raise RuntimeError(
        f"Could not reach the assessment page after {MAX_LOGIN_ATTEMPTS} "
        f"login attempts. Last URL: {selenium_driver.current_url}"
    )
