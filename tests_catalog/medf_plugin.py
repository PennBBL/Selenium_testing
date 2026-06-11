import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue


class MEDFPlugin:
    exact_code = "medf36-a-3.06-ff"

    # App.js response mapping:
    # response 1 = left face, response 3 = Equal, response 2 = right face
    PRACTICE_RESPONSES = [
        2,  # angry practice: right face
        1,  # happy practice: left face
        3,  # sad practice: Equal
    ]

    def _click_continue_if_present(self, ctx, label, timeout=4):
        try:
            click_continue(ctx, label=f"MEDF {label}", timeout=timeout, delay=0.5)
            return True
        except Exception:
            return False
        
    def _medf_buttons_present(self, ctx):
        selector = "button.medf-memory-button, button.memory-button"
        buttons = [
            b for b in ctx.driver.find_elements(By.CSS_SELECTOR, selector)
            if b.is_displayed() and b.is_enabled()
        ]
        return len(buttons) >= 3

    def _click_continue_required(self, ctx, label, timeout=20):
        if self._medf_buttons_present(ctx):
            ctx.logger.info(f"MEDF {label}: response buttons already present; skipping continue")
            return

        click_continue(ctx, label=f"MEDF {label}", timeout=timeout, delay=1)

    def _wait_for_medf_buttons(self, ctx, timeout=15):
        selector = "button.medf-memory-button, button.memory-button"

        buttons = WebDriverWait(ctx.driver, timeout).until(
        lambda d: [
            b for b in d.find_elements(By.CSS_SELECTOR, selector)
            if b.is_displayed() and b.is_enabled()
        ]
    )

        if len(buttons) < 3:
            raise RuntimeError(f"MEDF expected 3 response buttons, found {len(buttons)}")

        return buttons[:3]

    def _click_response(self, ctx, response_value):
        buttons = self._wait_for_medf_buttons(ctx, timeout=15)

        # App.js order:
        # response 1 = left face
        # response 3 = Equal
        # response 2 = right face
        index_by_response = {
            1: 0,
            3: 1,
            2: 2,
        }

        button = buttons[index_by_response[response_value]]

        ctx.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            button,
        )

        WebDriverWait(ctx.driver, 5).until(lambda d: button.is_displayed() and button.is_enabled())

        try:
            button.click()
        except Exception:
            ctx.driver.execute_script("arguments[0].click();", button)

    def _instructions_to_practice(self, ctx):
        # Landing Continue is already clicked by run_battery.
        # MEDF then has two instruction Continue pages before BEGIN PRACTICE.
        self._click_continue_required(ctx, "instruction page 1")
        self._click_continue_required(ctx, "instruction page 2")

        # BEGIN PRACTICE
        self._click_continue_required(ctx, "begin practice")

    def _practice(self, ctx):
        total_practice = len(self.PRACTICE_RESPONSES)

        for i, response in enumerate(self.PRACTICE_RESPONSES, start=1):
            ctx.logger.info(f"MEDF practice trial {i}: clicking response {response}")
            self._click_response(ctx, response)
            time.sleep(1)

            # Only do this for practice trials 1 and 2.
            # After trial 3, the app may already advance to the post-practice instructions page.
            if i < total_practice:
                self._click_continue_if_present(ctx, f"after practice trial {i}", timeout=3)

        # Now we should be on the "Good job / test will begin now" page.
        self._click_continue_required(ctx, "post-practice instructions", timeout=20)

        # Now we should be on BEGIN TEST.
        self._click_continue_required(ctx, "begin test", timeout=20)

    def _main_test(self, ctx, strategy):
        trial_count = 0
        max_trials = 36

        while trial_count < max_trials:
            try:
                self._wait_for_medf_buttons(ctx, timeout=10)
            except Exception:
                # No more buttons usually means the test has ended.
                break

            trial_count += 1

            if strategy == "sequential":
                response = [1, 3, 2][(trial_count - 1) % 3]
            else:
                response = random.choice([1, 2, 3])

            ctx.logger.info(f"MEDF test trial {trial_count}: clicking response {response}")
            time.sleep(random.uniform(0.4, 1.2))
            self._click_response(ctx, response)
            time.sleep(0.5)

            # Usually test trials advance immediately, but this prevents hanging if a Continue appears.
            self._click_continue_if_present(ctx, f"after test trial {trial_count}", timeout=1)

        ctx.logger.info(f"MEDF completed {trial_count} randomized test trials")

    def run(self, ctx, strategy="random"):
        errors = []

        try:
            self._instructions_to_practice(ctx)
            self._practice(ctx)
            self._main_test(ctx, strategy="random")
            return TestRunResult(status="PASS", errors=errors)

        except Exception as exc:
            errors.append(str(exc))
            ctx.artifacts.capture_failure(ctx.driver, "medf_failure", {"errors": errors})
            return TestRunResult(status="FAIL", errors=errors)