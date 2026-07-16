import random
import time

from selenium.webdriver.common.by import By

from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue, click_continue_until, find_continue


ENGLISH_TARGETS = {
    "NIGHT", "TOWER", "RING", "FLAG", "UMBRELLA",
    "CHEESE", "CHERRY", "LAP", "NURSE", "HOBBY",
    "BRICK", "BOX", "STATION", "BLOOM", "VOLUME",
    "JOKE", "POCKET", "FORK", "HONEY", "PACKAGE",
}


class CPWPlugin:
    exact_code = "k-cpw-3.01-ff"

    exact_codes = {
        "k-cpw-3.01-ff",
        "zn_CN-k-cpw-3.01-ff",
        "zh_CN-k-cpw-3.01-ff",
    }

    TEST_TRIALS = 40

    # Response index mapping:
    # 0 = Definitely Yes
    # 1 = Probably Yes
    # 2 = Probably No
    # 3 = Definitely No
    DEFINITELY_YES_INDEX = 0
    DEFINITELY_NO_INDEX = 3

    def _get_exact_code(self, ctx):
        for attr in ("exact_code", "test_code", "code"):
            value = getattr(ctx, attr, None)
            if value:
                return value

        settings = getattr(ctx, "settings", None)
        if isinstance(settings, dict):
            return settings.get("test") or settings.get("exact_code")

        return self.exact_code

    def _is_english(self, ctx):
        return self._get_exact_code(ctx) == self.exact_code

    def _click_continue(self, ctx, label, timeout=30, delay=1):
        click_continue(ctx, label=f"CPW {label}", timeout=timeout, delay=delay)

    def _stimulus_present(self, ctx):
        stimuli = [
            el for el in ctx.driver.find_elements(By.CSS_SELECTOR, "h1.stimulus--cpw")
            if el.is_displayed()
        ]
        return len(stimuli) > 0

    def _presentation_or_test_started(self, ctx):
        # Language-agnostic: presentation/test phase has a CPW stimulus.
        return self._stimulus_present(ctx)

    def _wait_for_presentation_end(self, ctx, timeout=140):
        """
        CPW presentation is timed. After it ends, a continue button appears.
        This avoids relying on English or translated instruction text.
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            if find_continue(ctx.driver):
                ctx.logger.info("CPW presentation ended; continue button visible")
                return True

            time.sleep(1)

        return False

    def _get_response_buttons(self, ctx):
        selector = (
            ".memory--task .memory-buttons--test .memory-button, "
            ".memory--task .inline.memory-buttons--test .memory-button, "
            ".inline.memory-buttons--test .memory-button, "
            ".memory-buttons--test .memory-button"
        )

        return [
            el for el in ctx.driver.find_elements(By.CSS_SELECTOR, selector)
            if el.is_displayed() and el.is_enabled()
        ]

    def _wait_for_response_buttons(self, ctx, timeout=15):
        deadline = time.time() + timeout

        while time.time() < deadline:
            buttons = self._get_response_buttons(ctx)

            if len(buttons) >= 4:
                return buttons[:4]

            time.sleep(0.2)

        raise RuntimeError("CPW expected 4 test response buttons, but they were not found")

    def _get_correct_english_response_index(self, stimulus_text):
        word = (stimulus_text or "").strip().upper()
        is_target = word in ENGLISH_TARGETS
        return self.DEFINITELY_YES_INDEX if is_target else self.DEFINITELY_NO_INDEX

    def _get_response_index(self, ctx, stimulus_text):
        if self._is_english(ctx):
            return self._get_correct_english_response_index(stimulus_text)

        return random.randrange(4)

    def _click_response_index(self, ctx, response_index):
        buttons = self._wait_for_response_buttons(ctx, timeout=15)

        if response_index < 0 or response_index >= len(buttons):
            raise RuntimeError(
                f"CPW invalid response index {response_index}; found {len(buttons)} buttons"
            )

        target = buttons[response_index]

        ctx.logger.info(
            "CPW clicking response index=%s text=%r",
            response_index,
            (target.text or "").strip(),
        )

        ctx.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            target,
        )

        time.sleep(random.uniform(0.3, 1.0))

        try:
            target.click()
        except Exception:
            ctx.driver.execute_script("arguments[0].click();", target)

    def _instructions_to_presentation(self, ctx):
        # Runner has already clicked landing-page Continue.
        click_continue_until(
            ctx,
            stop_condition=lambda: self._presentation_or_test_started(ctx),
            max_clicks=7,
            label="CPW instruction/presentation-start",
            delay=1.5,
            timeout=30,
        )

    def _presentation_to_test(self, ctx):
        ctx.logger.info("CPW waiting for presentation to finish")

        if not self._wait_for_presentation_end(ctx):
            raise RuntimeError("Timed out waiting for CPW presentation end")

        self._click_continue(ctx, "post-presentation instructions", timeout=30, delay=1)
        self._click_continue(ctx, "begin test", timeout=30, delay=2)

    def _main_test(self, ctx):
        trial_count = 0
        is_english = self._is_english(ctx)

        ctx.logger.info(
            "CPW main test response mode=%s",
            "english-correct" if is_english else "non-english-random",
        )

        while trial_count < self.TEST_TRIALS:
            try:
                stimulus_el = ctx.wait.present(
                    (By.CSS_SELECTOR, "h1.stimulus--cpw"),
                    timeout=10,
                )
            except Exception:
                ctx.logger.info("CPW no stimulus found; ending loop")
                break

            stimulus_text = (stimulus_el.text or "").strip()

            if not stimulus_text:
                time.sleep(0.2)
                continue

            trial_count += 1
            response_index = self._get_response_index(ctx, stimulus_text)

            ctx.logger.info(
                "CPW trial %02d/%02d: stimulus=%r response_index=%s",
                trial_count,
                self.TEST_TRIALS,
                stimulus_text,
                response_index,
            )

            self._click_response_index(ctx, response_index)
            time.sleep(0.3)

        ctx.logger.info(f"CPW completed {trial_count} test trials")

        if trial_count != self.TEST_TRIALS:
            raise RuntimeError(
                f"CPW expected {self.TEST_TRIALS} test trials, completed {trial_count}"
            )

    def run(self, ctx, strategy=None):
        errors = []

        try:
            exact_code = self._get_exact_code(ctx)
            mode = "english-correct" if self._is_english(ctx) else "non-english-random"

            ctx.logger.info(f"CPW starting exact_code={exact_code!r} mode={mode}")

            self._instructions_to_presentation(ctx)
            self._presentation_to_test(ctx)
            self._main_test(ctx)

            return TestRunResult(status="PASS", errors=errors)

        except Exception as exc:
            errors.append(str(exc))
            ctx.logger.exception("CPW failed")
            ctx.artifacts.capture_failure(ctx.driver, "cpw_failure", {"errors": errors})
            return TestRunResult(status="FAIL", errors=errors)