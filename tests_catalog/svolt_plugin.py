import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue


class SVOLTPlugin:
    """
    Visual Object Learning Test - Short Version.

    For zn_CN-k-svolt-3.01-ff.

    App.js flow:
      landing/welcome page        -> handled by run_battery landing.click_continue()
      first instructions          -> click Continue
      begin demonstration         -> click Continue
      study slideblock            -> 10 shapes x 5000 ms = about 50 seconds
      test instructions           -> click Continue
      begin test                  -> click Continue
      test trialblock             -> 20 trials, four button responses
    """

    exact_code = "zn_CN-k-svolt-3.01-ff"

    exact_codes = {
        "zn_CN-k-svolt-3.01-ff",
        "zh_CN-k-svolt-3.01-ff",
        "k-svolt-3.01-ff",
    }

    TEST_TRIALS = 20
    RESPONSE_VALUES = [1, 2, 3, 4]

    RESPONSE_SELECTOR = (
        ".memory-buttons--test .memory-button, "
        ".inline.memory-buttons--test .memory-button"
    )

    def _visible_enabled(self, element):
        try:
            return element.is_displayed() and element.is_enabled()
        except Exception:
            return False

    def _response_elements(self, ctx):
        try:
            return [
                el
                for el in ctx.driver.find_elements(By.CSS_SELECTOR, self.RESPONSE_SELECTOR)
                if self._visible_enabled(el)
            ]
        except Exception:
            return []

    def _response_elements_present(self, ctx):
        return len(self._response_elements(ctx)) >= 4

    def _click_continue_required(self, ctx, label, timeout=20):
        """
        Click a normal CNB continue button. Do not skip on generic .memory-button,
        because SVolt instruction pages contain non-click test examples using
        .memory-buttons--other .memory-button.
        """
        if self._response_elements_present(ctx):
            ctx.logger.info(
                "SVOLT %s: test response elements already present; skipping continue",
                label,
            )
            return

        click_continue(ctx, label=f"SVOLT {label}", timeout=timeout, delay=0.5)

    def _wait_for_response_buttons(self, ctx, timeout=20):
        elements = WebDriverWait(ctx.driver, timeout).until(
            lambda d: self._response_elements(ctx)
        )

        if len(elements) < 4:
            raise RuntimeError(f"SVOLT expected 4 response elements, found {len(elements)}")

        return elements[:4]

    def _click_response_index(self, ctx, index):
        elements = self._wait_for_response_buttons(ctx, timeout=20)

        if index not in {0, 1, 2, 3}:
            raise RuntimeError(f"SVOLT invalid response index: {index}")

        target = elements[index]

        ctx.logger.info(
            "SVOLT clicking response index=%s text=%r",
            index,
            (target.text or "").strip(),
        )

        ctx.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            target,
        )
        time.sleep(0.15)

        try:
            target.click()
        except Exception:
            ctx.driver.execute_script("arguments[0].click();", target)

    def _instructions_to_test(self, ctx):
        # run_battery already clicked landing/welcome Continue.
        self._click_continue_required(ctx, "first instructions", timeout=20)
        self._click_continue_required(ctx, "begin demonstration", timeout=20)

        # Study phase: 10 shapes x 5 seconds = about 50 seconds.
        # The next Continue appears only after the slideblock finishes.
        ctx.logger.info("SVOLT waiting for 10-shape study slideblock to finish")
        self._click_continue_required(ctx, "post-study test instructions", timeout=75)

        self._click_continue_required(ctx, "begin test", timeout=20)

    def _main_test(self, ctx, strategy):
        trial_count = 0

        while trial_count < self.TEST_TRIALS:
            try:
                self._wait_for_response_buttons(ctx, timeout=20)
            except Exception as exc:
                raise RuntimeError(
                    f"SVOLT response buttons disappeared before trial "
                    f"{trial_count + 1}/{self.TEST_TRIALS}: {exc}"
                )

            trial_count += 1

            if strategy == "sequential":
                response_index = (trial_count - 1) % 4
            else:
                response_index = random.choice([0, 1, 2, 3])

            ctx.logger.info(
                "SVOLT test trial %s/%s: clicking response index %s",
                trial_count,
                self.TEST_TRIALS,
                response_index,
            )

            time.sleep(random.uniform(0.25, 0.7))
            self._click_response_index(ctx, response_index)
            time.sleep(0.35)

        ctx.logger.info("SVOLT completed %s randomized test trials", trial_count)

        if trial_count != self.TEST_TRIALS:
            raise RuntimeError(
                f"SVOLT expected {self.TEST_TRIALS} test trials, completed {trial_count}"
            )

    def run(self, ctx, strategy="random"):
        errors = []

        try:
            ctx.logger.info("SVOLT starting")

            self._instructions_to_test(ctx)
            self._main_test(ctx, strategy=strategy)

            return TestRunResult(status="PASS", errors=errors)

        except Exception as exc:
            errors.append(str(exc))
            ctx.logger.exception("SVOLT failed")

            try:
                ctx.artifacts.capture_failure(ctx.driver, "svolt_failure", {"errors": errors})
            except Exception:
                ctx.logger.exception("Could not capture SVOLT failure artifact")

            return TestRunResult(status="FAIL", errors=errors)
