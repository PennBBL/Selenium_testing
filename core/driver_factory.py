from __future__ import annotations

import os
import shutil

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions


CHROME_BINARIES = [
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
]

EDGE_BINARIES = [
    "microsoft-edge",
    "microsoft-edge-stable",
    "msedge",
]

FIREFOX_BINARIES = [
    "firefox",
    "firefox-esr",
]


def _env_flag(name: str, default: bool | None = None) -> bool | None:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _find_binary(candidates: list[str]) -> str | None:
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path

    return None


def _should_headless(headless: bool | None) -> bool:
    """
    Headless behavior:
    - If caller passes True/False, use that.
    - Else if HEADLESS env exists, use it.
    - Else if no DISPLAY exists, use headless automatically.
    - Else visible mode.
    """
    if headless is not None:
        return bool(headless)

    env_headless = _env_flag("HEADLESS", default=None)
    if env_headless is not None:
        return bool(env_headless)

    return not bool(os.getenv("DISPLAY"))


def _window_size() -> str:
    return os.getenv("CHROME_WINDOW_SIZE") or os.getenv("BROWSER_WINDOW_SIZE") or "1200,900"


def _build_chrome_options(headless: bool) -> ChromeOptions:
    options = ChromeOptions()

    chrome_binary = _find_binary(CHROME_BINARIES)
    if chrome_binary:
        options.binary_location = chrome_binary

    if headless:
        options.add_argument("--headless=new")

    options.add_argument(f"--window-size={_window_size()}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")

    return options


def _build_edge_options(headless: bool) -> EdgeOptions:
    options = EdgeOptions()

    edge_binary = _find_binary(EDGE_BINARIES)
    if edge_binary:
        options.binary_location = edge_binary

    if headless:
        options.add_argument("--headless=new")

    options.add_argument(f"--window-size={_window_size()}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")

    return options


def _build_firefox_options(headless: bool) -> FirefoxOptions:
    options = FirefoxOptions()

    firefox_binary = _find_binary(FIREFOX_BINARIES)
    if firefox_binary:
        options.binary_location = firefox_binary

    if headless:
        options.add_argument("--headless")

    width, height = _window_size().split(",", 1)
    options.add_argument(f"--width={width.strip()}")
    options.add_argument(f"--height={height.strip()}")

    return options


def build_driver(browser: str = "chrome", headless: bool | None = None):
    browser = (browser or "chrome").strip().lower()
    resolved_headless = _should_headless(headless)

    if browser in {"chrome", "google-chrome", "chromium"}:
        return webdriver.Chrome(options=_build_chrome_options(resolved_headless))

    if browser in {"edge", "msedge", "microsoft-edge"}:
        return webdriver.Edge(options=_build_edge_options(resolved_headless))

    if browser in {"firefox", "mozilla", "ff"}:
        return webdriver.Firefox(options=_build_firefox_options(resolved_headless))

    raise ValueError(
        f"Unsupported browser: {browser}. "
        "Choose one of: chrome, firefox, edge."
    )


def build_chrome_driver(headless: bool | None = None):
    """
    Backward-compatible wrapper for older code.
    """
    return build_driver(browser="chrome", headless=headless)