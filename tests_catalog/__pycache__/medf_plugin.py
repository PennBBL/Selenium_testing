import random
import re
import time

from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue


class MEDFPlugin:
    exact_code = "medf36-a-3.06-ff"

    STIMULUS_SELECTOR = "div.stimulus--medf img"
    RESPONSE_BUTTON_SELECTOR = "button.memory-button"
    CONTINUE_SELECTOR = "button.continue-button"

    PRACTICE_TRIALS = 3
    TEST_TRIALS = 36

    def _click_continue(self, ctx, label, timeout=15, delay=1.5):
        click_continue(ctx, label=f"MEDF {label}", timeout=timeout, delay=delay)

    def _click_continue_if_present(self, ctx, label, delay=1):
        buttons = ctx.driver.find_elements(By.CSS_SELECTOR, self.CONTINUE_SELECTOR)
        if buttons:
            ctx.logger.info(f"MEDF clicking optional continue: {label}")
            ctx.driver.execute_script("arguments[0].click();", buttons[0])
            time.sleep(delay)
            return True
        return False

    def _wait_for_stimuli_and_buttons(self, ctx, timeout=15):
        end = time.time() + timeout

        while time.time() < end:
            imgs = ctx.driver.find_elements(By.CSS_SELECTOR, self.STIMULUS_SELECTOR)
            buttons = ctx.driver.find_elements(By.CSS_SELECTOR, self.RESPONSE_BUTTON_SELECTOR)

            if len(imgs) >= 2 and len(buttons) >= 3:
                return imgs[:2], buttons

            time.sleep(0.25)

        raise TimeoutException("MEDF expected 2 stimulus images and 3 response buttons.")

    def _extract_filename(self, src):
        """
        Expected cases:
            /static/media/024_happy_11.abc123.png
            /static/media/024_happy_11.png

        Returns:
            024_happy_11
        """
        if not src:
            return None

        if src.startswith("data:") or "base64" in src.lower():
            return None

        name = src.split("/")[-1].split("?")[0]

        # Handles both:
        #   024_happy_11.png
        #   024_happy_11.abc123.png
        m = re.search(r"(\d{3}_(happy|angry|fear|sad)_\d{2})", name, re.IGNORECASE)
        if not m:
            return None

        return m.group(1).lower()

    def _extract_intensity(self, filename):
        """
        024_happy_11 -> 11
        117_angry_03 -> 3
        """
        if not filename:
            return None

        m = re.search(r"_(\d{2})$", filename)
        if not m:
            return None

        return int(m.group(1))

    def _choose_correct_response(self, left_src, right_src):
        left_name = self._extract_filename(left_src)
        right_name = self._extract_filename(right_src)

        left_intensity = self._extract_intensity(left_name)
        right_intensity = self._extract_intensity(right_name)

        if left_intensity is None or right_intensity is None:
            raise RuntimeError(
                f"Could not infer MEDF answer from image srcs. "
                f"left={left_src[:80]} right={right_src[:80]}"
            )

        if left_intensity > right_intensity:
            return 1, left_name, right_name

        if right_intensity > left_intensity:
            return 2, left_name, right_name

        return 3, left_name, right_name

    def _choose_response(self, left_src, right_src, strategy):
        correct_response, left_name, right_name = self._choose_correct_response(left_src, right_src)

        if strategy == "correct":
            return correct_response, left_name, right_name, "correct"

        if strategy == "random":
            return random.choice([1, 2, 3]), left_name, right_name, "random"

        if strategy == "left_bias":
            return 1, left_name, right_name, "left_bias"

        if strategy == "right_bias":
            return 2, left_name, right_name, "right_bias"

        if strategy == "equal_bias":
            return 3, left_name, right_name, "equal_bias"

        return correct_response, left_name, right_name, "correct"

    def _click_response(self, ctx, buttons, response_num):
        """
        App.js response mapping:
            1 = left face
            3 = equal
            2 = right face

        Button text:
            ↑ This Face
            Equal
            This Face ↑
        """
        for btn in buttons:
            text = btn.text.strip().upper()

            if response_num == 1 and "THIS FACE" in text and text.startswith("↑"):
                btn.click()
                return

            if response_num == 2 and "THIS FACE" in text and text.endswith("↑"):
                btn.click()
                return

            if response_num == 3 and "EQUAL" in text:
                btn.click()
                return

        # Fallback by visible order: left, equal, right.
        if len(buttons) >= 3:
            if response_num == 1:
                buttons[0].click()
                return
            if response_num == 3:
                buttons[1].click()
                return
            if response_num == 2:
                buttons[2].click()
                return

        raise RuntimeError(f"Could not click MEDF response {response_num}")

    def _wait_for_trial_change(self, ctx, old_pair, timeout=8):
        end = time.time() + timeout

        while time.time() < end:
            imgs = ctx.driver.find_elements(By.CSS_SELECTOR, self.STIMULUS_SELECTOR)

            if len(imgs) < 2:
                return

            new_pair = (
                imgs[0].get_attribute("src") or "",
                imgs[1].get_attribute("src") or "",
            )

            if new_pair != old_pair:
                return

            # Some screens may require Continue after feedback.
            self._click_continue_if_present(ctx, "post-response feedback", delay=0.5)
            time.sleep(0.25)

    def _instructions_to_practice(self, ctx):
        """
        Runner already clicked the p.test-name landing Continue.

        Timeline:
            welcome
            instructions 1
            instructions 2
            begin practice
        """
        self._click_continue(ctx, "welcome")
        self._click_continue(ctx, "instructions 1")
        self._click_continue(ctx, "instructions 2")
        self._click_continue(ctx, "begin practice")

    def _run_trials(self, ctx, strategy, count, label, errors):
        for trial_num in range(1, count + 1):
            imgs, buttons = self._wait_for_stimuli_and_buttons(ctx, timeout=20)

            left_src = imgs[0].get_attribute("src") or ""
            right_src = imgs[1].get_attribute("src") or ""
            old_pair = (left_src, right_src)

            response_num, left_name, right_name, source = self._choose_response(
                left_src,
                right_src,
                strategy,
            )

            ctx.logger.info(
                f"MEDF {label} trial {trial_num:02d}: "
                f"{left_name} vs {right_name} -> response {response_num} ({source})"
            )

            time.sleep(random.uniform(0.4, 1.0))
            self._click_response(ctx, buttons, response_num)
            self._wait_for_trial_change(ctx, old_pair, timeout=8)

    def _practice(self, ctx, errors):
        self._run_trials(
            ctx=ctx,
            strategy="correct",
            count=self.PRACTICE_TRIALS,
            label="practice",
            errors=errors,
        )

        self._click_continue(ctx, "post-practice instructions")
        self._click_continue(ctx, "begin test")

    def _main_test(self, ctx, strategy, errors):
        self._run_trials(
            ctx=ctx,
            strategy=strategy,
            count=self.TEST_TRIALS,
            label="test",
            errors=errors,
        )

    def run(self, ctx, strategy="correct"):
        errors = []

        try:
            self._instructions_to_practice(ctx)
            self._practice(ctx, errors)
            self._main_test(ctx, strategy, errors)

            return TestRunResult(
                status="PASS" if not errors else "FAIL",
                errors=errors,
            )

        except Exception as exc:
            errors.append(str(exc))

            try:
                ctx.artifacts.capture_failure(
                    ctx.driver,
                    "medf_failure",
                    {"errors": errors},
                )
            except Exception:
                pass

            return TestRunResult(status="FAIL", errors=errors)