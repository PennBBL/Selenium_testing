import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv
import os

load_dotenv()
adminid = os.getenv('adminid')
pwd     = os.getenv('pwd')


def selenium_login(driver, webpage, browser="chrome"):
    """
    Log in to the CNB webpage.

    For Safari, the session cookie is silently dropped by ITP during the
    post-login redirect.  The fix is to:
      1. Submit credentials normally.
      2. Wait until the redirect has fully settled (URL changes away from
         the login page, or "New Assessment" appears).
      3. Immediately re-inject every cookie Safari may have dropped, using
         the WebDriver cookie API which bypasses ITP.
      4. Reload the destination page so the re-injected cookies are sent.

    All other browsers go through the original three-step path unchanged.
    """

    # ── Step 1: open the login page ──────────────────────────────
    driver.get(webpage)
    wait = WebDriverWait(driver, 10)

    # ── Step 2: enter username ───────────────────────────────────
    username_element = wait.until(
        EC.presence_of_element_located((By.NAME, "adminid"))
    )
    username_element.send_keys(adminid)

    # ── Step 3: enter password ───────────────────────────────────
    pwd_element = wait.until(
        EC.presence_of_element_located((By.NAME, "pwd"))
    )
    pwd_element.send_keys(pwd)

    # ── Step 4: click login button ───────────────────────────────
    login_btn_element = wait.until(
        EC.element_to_be_clickable((By.NAME, "Login"))
    )
    login_origin = driver.current_url
    login_btn_element.click()

    if browser != "safari":
        # Non-Safari: original behaviour — click and return immediately.
        return

    # ── Safari-only: survive ITP ─────────────────────────────────
    # Wait for the redirect away from the login page (up to 15 s).
    try:
        WebDriverWait(driver, 15).until(
            lambda d: d.current_url != login_origin
        )
    except Exception:
        pass   # if URL didn't change, carry on anyway

    # Give the server a moment to fully set all cookies before we read them.
    time.sleep(1)

    # Snapshot every cookie that was set during login + redirect.
    cookies_after_login = driver.get_cookies()

    if not cookies_after_login:
        # Safari gave us nothing — try a brief extra wait and retry once.
        time.sleep(2)
        cookies_after_login = driver.get_cookies()

    # Navigate back to the login origin so add_cookie() targets the right
    # domain (Safari rejects cookies added on a different origin).
    landed_url = driver.current_url
    driver.get(webpage)
    time.sleep(1)

    for cookie in cookies_after_login:
        # Safari rejects cookies that contain keys it doesn't recognise.
        safe = {k: v for k, v in cookie.items()
                if k in ("name", "value", "domain", "path",
                         "secure", "httpOnly", "expiry")}
        try:
            driver.add_cookie(safe)
        except Exception:
            pass

    # Return to where the server sent us after login — now with the
    # re-injected cookies the session should be alive.
    driver.get(landed_url)
    time.sleep(1)
