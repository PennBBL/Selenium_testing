from selenium.webdriver.common.by import By


class TestLandingPage:
    TEST_NAME = (By.CSS_SELECTOR, 'p.test-name')
    CONTINUE_BUTTON = (By.CSS_SELECTOR, 'button.continue-button')

    def __init__(self, ctx):
        self.ctx = ctx

    def get_exact_test_code(self) -> str:
        el = self.ctx.wait.visible(self.TEST_NAME, timeout=30)
        return el.text.strip()

    def click_continue(self):
        el = self.ctx.wait.clickable(self.CONTINUE_BUTTON, timeout=30)
        self.ctx.driver.execute_script('arguments[0].click();', el)
