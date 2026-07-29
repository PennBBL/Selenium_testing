import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions


BROWSER_BINARIES = {
    # macOS desktop path
    "chrome_mac": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",

    # common Linux paths
    "chrome_linux": "/usr/bin/google-chrome",
    "chromium_linux": "/usr/bin/chromium",
    "chromium_browser_linux": "/usr/bin/chromium-browser",
}


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _find_chrome_binary():
    """
    Use a hardcoded binary only if it exists.

    On macOS this can find Google Chrome.
    On Linux this can find google-chrome/chromium if installed.
    If nothing is found, Selenium Manager can still try to locate Chrome.
    """
    for binary in BROWSER_BINARIES.values():
        if binary and os.path.exists(binary):
            return binary

    return None


def build_chrome_driver(headless=None):
    """
    Build Chrome driver.

    Local desktop:
        python runner.py

    Server/headless:
        HEADLESS=1 python runner.py

    Optional custom window:
        HEADLESS=1 CHROME_WINDOW_SIZE=1600,1200 python runner.py
    """
    opts = ChromeOptions()

    if headless is None:
        headless = _env_flag("HEADLESS", default=False)

    window_size = os.environ.get("CHROME_WINDOW_SIZE", "1200,900")

    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument(f"--window-size={window_size}")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
    else:
        opts.add_argument("--start-maximized")

    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-popup-blocking")

    binary = _find_chrome_binary()

    if binary:
        opts.binary_location = binary

    return webdriver.Chrome(options=opts)