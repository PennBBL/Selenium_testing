import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue


class ADTPlugin:
    exact_code = "adt36-a-3.07-ff"

    # Form A practice:
    # response 1 = left face
    # response 3 = Same Age
    # response 2 = right face
    PRACTICE_RESPONSES = [2, 1, 3]
    TEST_TRIALS = 36

    def _click_continue_if_present(self, ctx, label, timeout=4):
        try:
            click_continue(ctx, label=f"ADT {label}", timeout=timeout, delay=0.5)
            return True
        except Exception:
            return False

    def _adt_response_elements_present(self, ctx):
        selector = (
            ".comparison--responses .memory-button, "
            ".comparison--responses button, "
            ".comparison--responses .button"
        )

        elements = [
            el for el in ctx.driver.find_elements(By.CSS_SELECTOR, selector)
            if el.is_displayed() and el.is_enabled()
        ]

        return len(elements) >= 3

    def _click_continue_required(self, ctx, label, timeout=20):
        if self._adt_response_elements_present(ctx):
            ctx.logger.info(f"ADT {label}: response elements already present; skipping continue")
            return

        click_continue(ctx, label=f"ADT {label}", timeout=timeout, delay=1)

    def _wait_for_adt_buttons(self, ctx, timeout=15):
        selector = (
            ".comparison--responses .memory-button, "
            ".comparison--responses button, "
            ".comparison--responses .button"
        )

        elements = WebDriverWait(ctx.driver, timeout).until(
            lambda d: [
                el for el in d.find_elements(By.CSS_SELECTOR, selector)
                if el.is_displayed() and el.is_enabled()
            ]
        )

        if len(elements) < 3:
            raise RuntimeError(f"ADT expected 3 response elements, found {len(elements)}")

        return elements[:3]

    def _click_response(self, ctx, response_value):
        elements = self._wait_for_adt_buttons(ctx, timeout=15)

        # App.js visual order:
        # index 0 = response 1 = left face
        # index 1 = response 3 = Same Age
        # index 2 = response 2 = right face
        index_by_response = {
            1: 0,
            3: 1,
            2: 2,
        }

        target = elements[index_by_response[response_value]]

        ctx.logger.info(
            "ADT clicking response %s using element text=%r",
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

    def _instructions_to_practice(self, ctx):
        self._click_continue_required(ctx, "instruction page 1")
        self._click_continue_required(ctx, "instruction page 2")
        self._click_continue_required(ctx, "begin practice")

    def _practice(self, ctx):
        total_practice = len(self.PRACTICE_RESPONSES)

        for i, response in enumerate(self.PRACTICE_RESPONSES, start=1):
            ctx.logger.info(f"ADT Form A practice trial {i}: clicking response {response}")
            self._click_response(ctx, response)
            time.sleep(1)

            # Do not click optional Continue after final practice trial.
            # It can accidentally skip the post-practice instruction page.
            if i < total_practice:
                self._click_continue_if_present(ctx, f"after practice trial {i}", timeout=3)

        self._click_continue_required(ctx, "post-practice instructions", timeout=20)
        self._click_continue_required(ctx, "begin test", timeout=20)

    def _main_test(self, ctx, strategy):
        trial_count = 0

        while trial_count < self.TEST_TRIALS:
            try:
                self._wait_for_adt_buttons(ctx, timeout=10)
            except Exception:
                break

            trial_count += 1

            if strategy == "sequential":
                response = [1, 3, 2][(trial_count - 1) % 3]
            else:
                response = random.choice([1, 2, 3])

            ctx.logger.info(
                f"ADT Form A test trial {trial_count}/{self.TEST_TRIALS}: clicking response {response}"
            )

            time.sleep(random.uniform(0.4, 1.2))
            self._click_response(ctx, response)
            time.sleep(0.5)

            self._click_continue_if_present(ctx, f"after test trial {trial_count}", timeout=1)

        ctx.logger.info(f"ADT Form A completed {trial_count} randomized test trials")

        if trial_count != self.TEST_TRIALS:
            raise RuntimeError(
                f"ADT Form A expected {self.TEST_TRIALS} test trials, completed {trial_count}"
            )

    def run(self, ctx, strategy="random"):
        errors = []

        try:
            ctx.logger.info("ADT detected Form A")

            self._instructions_to_practice(ctx)
            self._practice(ctx)
            self._main_test(ctx, strategy=strategy)

            return TestRunResult(status="PASS", errors=errors)

        except Exception as exc:
            errors.append(str(exc))
            ctx.logger.exception("ADT Form A failed")
            ctx.artifacts.capture_failure(ctx.driver, "adt_failure", {"errors": errors})
            return TestRunResult(status="FAIL", errors=errors)