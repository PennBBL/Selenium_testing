from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class Waits:
    def __init__(self, driver, default_timeout: int = 15):
        self.driver = driver
        self.default_timeout = default_timeout

    def visible(self, locator, timeout=None):
        return WebDriverWait(self.driver, timeout or self.default_timeout).until(
            EC.visibility_of_element_located(locator)
        )

    def present(self, locator, timeout=None):
        return WebDriverWait(self.driver, timeout or self.default_timeout).until(
            EC.presence_of_element_located(locator)
        )

    def clickable(self, locator, timeout=None):
        return WebDriverWait(self.driver, timeout or self.default_timeout).until(
            EC.element_to_be_clickable(locator)
        )

    def ready(self, timeout=None):
        return WebDriverWait(self.driver, timeout or self.default_timeout).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
