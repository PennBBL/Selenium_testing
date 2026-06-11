import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions

BROWSER_BINARIES = {
    'chrome': '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
}


def build_chrome_driver():
    opts = ChromeOptions()
    opts.add_argument('--start-maximized')
    binary = BROWSER_BINARIES.get('chrome')
    if binary and os.path.exists(binary):
        opts.binary_location = binary
    return webdriver.Chrome(options=opts)
