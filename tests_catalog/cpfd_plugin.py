import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue


class CPFDPlugin:
    exact_code = "cpfd-2.05-ff"

    TEST_TRIALS = 40
    RESPONSE_VALUES = [1, 2, 3, 4]

    def _click_continue_if_present(self, ctx, label, timeout=4):
        try:
            click_continue(ctx, label=f"CPFD {label}", timeout=timeout, delay=0.5)
            return True
        except Exception:
            return False

    def _response_elements_present(self, ctx):
        selector = (
            ".memory--task .memory-buttons--test .memory-button, "
            ".memory--task .inline.memory-buttons--test .memory-button, "
            ".memory--task .button.memory-button"
        )

        elements = [
            el for el in ctx.driver.find_elements(By.CSS_SELECTOR, selector)
            if el.is_displayed() and el.is_enabled()
        ]

        return len(elements) >= 4

    def _click_continue_required(self, ctx, label, timeout=20):
        if self._response_elements_present(ctx):
            ctx.logger.info(f"CPFD {label}: response elements already present; skipping continue")
            return

        click_continue(ctx, label=f"CPFD {label}", timeout=timeout, delay=1)

    def _wait_for_response_buttons(self, ctx, timeout=15):
        selector = (
            ".memory--task .memory-buttons--test .memory-button, "
            ".memory--task .inline.memory-buttons--test .memory-button, "
            ".memory--task .button.memory-button"
        )

        elements = WebDriverWait(ctx.driver, timeout).until(
            lambda d: [
                el for el in d.find_elements(By.CSS_SELECTOR, selector)
                if el.is_displayed() and el.is_enabled()
            ]
        )

        if len(elements) < 4:
            raise RuntimeError(f"CPFD expected 4 test response elements, found {len(elements)}")

        return elements[:4]

    def _click_response(self, ctx, response_value):
        elements = self._wait_for_response_buttons(ctx, timeout=15)

        index_by_response = {
            1: 0,  # DEFINITELY YES
            2: 1,  # PROBABLY YES
            3: 2,  # PROBABLY NO
            4: 3,  # DEFINITELY NO
        }

        target = elements[index_by_response[response_value]]

        ctx.logger.info(
            "CPFD clicking response %s using element text=%r",
            response_value,
            (target.text or "").strip(),
        )

        ctx.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            target,
        )

        WebDriverWait(ctx.driver, 5).until(
            lambda d: target.is_displayed() and target.is_enabled()
        )

        try:
            target.click()
        except Exception:
            ctx.driver.execute_script("arguments[0].click();", target)

    def _instructions_to_test(self, ctx):
        # Landing Continue is already clicked by run_battery.
        self._click_continue_required(ctx, "instructions", timeout=20)
        self._click_continue_required(ctx, "begin test", timeout=20)

    def _main_test(self, ctx, strategy):
        trial_count = 0

        while trial_count < self.TEST_TRIALS:
            try:
                self._wait_for_response_buttons(ctx, timeout=15)
            except Exception:
                break

            trial_count += 1

            if strategy == "sequential":
                response = self.RESPONSE_VALUES[(trial_count - 1) % len(self.RESPONSE_VALUES)]
            else:
                response = random.choice(self.RESPONSE_VALUES)

            ctx.logger.info(
                f"CPFD test trial {trial_count}/{self.TEST_TRIALS}: clicking response {response}"
            )

            time.sleep(random.uniform(0.3, 0.9))
            self._click_response(ctx, response)
            time.sleep(0.3)

            self._click_continue_if_present(ctx, f"after test trial {trial_count}", timeout=1)

        ctx.logger.info(f"CPFD completed {trial_count} randomized test trials")

        if trial_count != self.TEST_TRIALS:
            raise RuntimeError(
                f"CPFD expected {self.TEST_TRIALS} test trials, completed {trial_count}"
            )

    def run(self, ctx, strategy="random"):
        errors = []

        try:
            ctx.logger.info("CPFD starting")

            self._instructions_to_test(ctx)
            self._main_test(ctx, strategy=strategy)

            return TestRunResult(status="PASS", errors=errors)

        except Exception as exc:
            errors.append(str(exc))
            ctx.logger.exception("CPFD failed")
            ctx.artifacts.capture_failure(ctx.driver, "cpfd_failure", {"errors": errors})
            return TestRunResult(status="FAIL", errors=errors)