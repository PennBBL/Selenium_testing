from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class BatteryChoicePage:
    COMPLETED_HEADER = (By.XPATH, "//*[contains(normalize-space(.), 'So far the following tests have been completed')]")
    NEXT_TEST_TEXT = (By.XPATH, "//p[contains(normalize-space(.), 'Next test:')]")
    CONTINUE_LINK = (By.XPATH, "//a[.//img[contains(@src, 'go.png')]]")
    QUIT_LINK = (By.XPATH, "//a[contains(@href, 'op=Quit') or .//img[contains(@src, 'stop.png')]]")
    COMPLETED_TEST_ROWS = (By.XPATH, "//h2[contains(., 'completed')]/following::table[1]//tr")

    def __init__(self, ctx):
        self.ctx = ctx

    def wait_until_present(self, timeout=45):
        return WebDriverWait(self.ctx.driver, timeout).until(
            EC.presence_of_element_located(self.COMPLETED_HEADER)
        )

    def is_present(self) -> bool:
        return bool(self.ctx.driver.find_elements(*self.COMPLETED_HEADER))

    def get_next_test_label(self) -> str | None:
        els = self.ctx.driver.find_elements(*self.NEXT_TEST_TEXT)
        if not els:
            return None
        text = els[0].text.strip()
        return text.split('Next test:', 1)[1].strip() if 'Next test:' in text else text

    def has_next_test(self) -> bool:
        return self.get_next_test_label() is not None and self.has_continue()

    def has_continue(self) -> bool:
        return bool(self.ctx.driver.find_elements(*self.CONTINUE_LINK))

    def has_quit(self) -> bool:
        return bool(self.ctx.driver.find_elements(*self.QUIT_LINK))

    def get_completed_tests(self) -> list[str]:
        rows = self.ctx.driver.find_elements(*self.COMPLETED_TEST_ROWS)
        return [r.text.strip() for r in rows if r.text.strip()]

    def click_continue(self):
        el = self.ctx.wait.clickable(self.CONTINUE_LINK, timeout=30)
        self.ctx.driver.execute_script('arguments[0].click();', el)
