import hashlib
import random
import time

from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue


IMAGE_BUTTON_MAP = [
    ("1_MA_CW.png", 3), ("4_EA_BW.png", 3), ("3_FAZ_129.png", 3), ("4_FAZ_32.png", 3),
    ("5_FFX_130.png", 4), ("6_FFX_54.png", 4), ("7_FFZ_236.png", 4), ("8_FFZ_29.png", 4),
    ("9_FHX_127.png", 1), ("10_FHX_220.png", 1), ("11_FHZ_131.png", 1), ("12_FHZ_152.png", 1),
    ("13_FN_13.png", 5), ("14_FN_204.png", 5), ("15_FN_228.png", 5), ("16_FN_30.png", 5),
    ("17_FSX_20.png", 2), ("18_FSX_47.png", 2), ("19_FSZ_210.png", 2), ("20_FSZ_219.png", 2),
    ("21_MAX_201.png", 3), ("23_EA_CM.png", 3), ("23_MAZ_128.png", 3), ("24_MAZ_146.png", 3),
    ("25_MFX_137.png", 4), ("26_MFX_153.png", 4), ("27_MFZ_132.png", 4), ("27_EF_CM.png", 4),
    ("29_MH_CM.png", 1), ("30_MHX_140.png", 1), ("30_MH_BM.png", 1), ("32_EH_OM.png", 1),
    ("33_MN_111.png", 5), ("34_MN_123.png", 5), ("35_MN_21.png", 5), ("36_MN_223.png", 5),
    ("37_MSX_108.png", 2), ("38_MSX_147.png", 2), ("39_ES_CM.png", 2), ("40_MSZ_126.png", 2),
]

BUTTON_MAPPING = {
    1: "HAPPY",
    2: "SAD",
    3: "ANGRY",
    4: "FEAR",
    5: "NO FEELING",
}


# IMPORTANT:
# ER40 is randomized and your images are base64 data URLs.
# That means trial order cannot be used.
#
# This map must be filled once using the hashes logged by this plugin.
#
# Example:
# BASE64_HASH_BUTTON_MAP = {
#     "9f2c1a8b4e3d9910": 3,  # ANGRY
#     "3a0e77f1488cc9d2": 4,  # FEAR
# }
#
# Hash values are generated from the full img src.
BASE64_HASH_BUTTON_MAP = {
    # Fill these after calibration/logging.
}


class ER40Plugin:
    exact_code = "k-er40-d-4.60-ff"

    CONTINUE_SELECTOR = "button.continue-button"
    STIMULUS_SELECTOR = "div.stimulus--er40 img"
    RESPONSE_BUTTON_SELECTOR = "button.button.er40--response-button"

    def _click_continue(self, ctx, label):
        click_continue(ctx, label=f"ER40 {label}", timeout=15, delay=2)

    def _send_ctrl_period(self, ctx):
        ctx.logger.warning("ER40 sending Ctrl + . to skip current test.")
        ActionChains(ctx.driver).key_down(Keys.CONTROL).send_keys(".").key_up(Keys.CONTROL).perform()
        time.sleep(1)

    def _instructions(self, ctx, errors):
        """
        The battery runner already clicked the exact-code landing-page Continue.

        Current ER40 deployment:
            landing Continue
            -> instruction page 1
            -> instruction page 2
            -> instruction page 3
            -> practice face page
        """
        for i in range(3):
            self._click_continue(ctx, f"instruction page {i + 1}/3")

        try:
            ctx.wait.present((By.CSS_SELECTOR, self.STIMULUS_SELECTOR), timeout=10)
        except Exception as exc:
            raise RuntimeError(
                "ER40 practice page did not appear after 3 instruction pages"
            ) from exc

    def _practice(self, ctx, errors):
        ctx.wait.present((By.CSS_SELECTOR, self.STIMULUS_SELECTOR), timeout=15)

        buttons = ctx.driver.find_elements(By.CSS_SELECTOR, self.RESPONSE_BUTTON_SELECTOR)
        if len(buttons) != 5:
            raise RuntimeError(f"ER40 practice expected 5 buttons, found {len(buttons)}")

        for wrong in ["HAPPY", "SAD", "FEAR", "NO FEELING"]:
            buttons = ctx.driver.find_elements(By.CSS_SELECTOR, self.RESPONSE_BUTTON_SELECTOR)
            for btn in buttons:
                if btn.text.strip().upper() == wrong:
                    btn.click()
                    time.sleep(0.5)
                    break

        buttons = ctx.driver.find_elements(By.CSS_SELECTOR, self.RESPONSE_BUTTON_SELECTOR)
        for btn in buttons:
            if btn.text.strip().upper() == "ANGRY":
                btn.click()
                time.sleep(2)
                break
        else:
            raise RuntimeError("Could not click ANGRY during ER40 practice")

        self._click_continue(ctx, "after practice")
        self._click_continue(ctx, "pre-test instructions")

    def _extract_filename_if_available(self, src: str) -> str | None:
        if not src:
            return None

        src_lower = src.lower()

        if src_lower.startswith("data:"):
            return None

        if "base64" in src_lower:
            return None

        candidate = src.split("/")[-1].split("?")[0].strip()

        if candidate.lower().endswith(".png"):
            return candidate

        return None

    def _hash_src(self, src: str) -> str:
        return hashlib.sha256(src.encode("utf-8")).hexdigest()[:16]

    def _answer_from_filename(self, filename: str | None) -> int | None:
        if not filename:
            return None

        for image_name, answer_num in IMAGE_BUTTON_MAP:
            if filename == image_name or filename in image_name or image_name in filename:
                return answer_num

        return None

    def _answer_from_base64_hash(self, src: str) -> tuple[int | None, str]:
        image_hash = self._hash_src(src)
        return BASE64_HASH_BUTTON_MAP.get(image_hash), image_hash

    def _choose_answer(self, ctx, src: str, strategy: str, stimulus_count: int) -> tuple[str, str]:
        """
        Returns:
            (button_text, source_used)

        For correct mode:
            - filename map if image filename is available
            - base64 hash map if image is embedded as data URL
            - no trial-order fallback, because ER40 order is randomized
        """
        filename = self._extract_filename_if_available(src)
        answer_num = self._answer_from_filename(filename)

        if answer_num is not None:
            source_used = f"filename:{filename}"
        else:
            answer_num, image_hash = self._answer_from_base64_hash(src)
            source_used = f"hash:{image_hash}"

        if strategy == "correct":
            if answer_num is None:
                ctx.logger.error(
                    f"ER40 unmapped base64 image on trial {stimulus_count}. "
                    f"Hash={image_hash}. Add this hash to BASE64_HASH_BUTTON_MAP."
                )
                raise RuntimeError(
                    f"ER40 correct strategy cannot continue: unmapped base64 image hash {image_hash}"
                )

            return BUTTON_MAPPING[answer_num], source_used

        if strategy == "random":
            return random.choice(list(BUTTON_MAPPING.values())), "random"

        if strategy == "sequential":
            return BUTTON_MAPPING[((stimulus_count - 1) % 5) + 1], "sequential"

        if strategy == "positive_bias":
            return "HAPPY", "positive_bias"

        if strategy == "learning":
            accuracy_rate = min(0.9, stimulus_count * 0.05)
            if random.random() < accuracy_rate and answer_num is not None:
                return BUTTON_MAPPING[answer_num], f"learning_{source_used}"
            return random.choice(list(BUTTON_MAPPING.values())), "learning_random"

        if answer_num is None:
            raise RuntimeError(
                f"ER40 strategy {strategy} cannot continue: unmapped base64 image hash {image_hash}"
            )

        return BUTTON_MAPPING[answer_num], source_used

    def _has_real_test_stimulus(self, ctx) -> bool:
        imgs = ctx.driver.find_elements(By.CSS_SELECTOR, self.STIMULUS_SELECTOR)
        buttons = ctx.driver.find_elements(By.CSS_SELECTOR, self.RESPONSE_BUTTON_SELECTOR)
        return bool(imgs) and len(buttons) == 5

    def _maybe_click_start_main_test(self, ctx):
        """
        Some ER40 versions show one more Continue before the first real stimulus.
        Others already show the first real stimulus after pre-test instructions.
        """
        if self._has_real_test_stimulus(ctx):
            ctx.logger.info("ER40 main-test stimulus already visible; not clicking extra Continue.")
            return

        buttons = ctx.driver.find_elements(By.CSS_SELECTOR, self.CONTINUE_SELECTOR)
        if buttons:
            ctx.logger.info("ER40 clicking start-main-test Continue.")
            buttons[0].click()
            time.sleep(2)
        else:
            ctx.logger.info("ER40 no start-main-test Continue found; proceeding.")

    def _main_test(self, ctx, strategy, errors):
        self._maybe_click_start_main_test(ctx)

        stimulus_count = 0

        while stimulus_count < len(IMAGE_BUTTON_MAP):
            time.sleep(1)

            imgs = ctx.driver.find_elements(By.CSS_SELECTOR, self.STIMULUS_SELECTOR)
            if not imgs:
                ctx.logger.info("ER40 no stimulus image found; assuming test complete.")
                break

            buttons = ctx.driver.find_elements(By.CSS_SELECTOR, self.RESPONSE_BUTTON_SELECTOR)
            if len(buttons) != 5:
                errors.append(
                    f"Stimulus {stimulus_count + 1}: expected 5 buttons, found {len(buttons)}"
                )
                break

            stimulus_count += 1

            src = imgs[0].get_attribute("src") or ""
            target_button, source_used = self._choose_answer(ctx, src, strategy, stimulus_count)

            ctx.logger.info(
                f"ER40 trial {stimulus_count}: {source_used} -> {target_button}"
            )

            time.sleep(random.uniform(0.5, 1.5))

            clicked = False
            for btn in buttons:
                if btn.text.strip().upper() == target_button:
                    btn.click()
                    clicked = True
                    break

            if not clicked:
                errors.append(
                    f"Stimulus {stimulus_count}: could not click {target_button}"
                )
                break

        if stimulus_count != len(IMAGE_BUTTON_MAP):
            errors.append(
                f"ER40 expected {len(IMAGE_BUTTON_MAP)} trials, completed {stimulus_count}"
            )

    def run(self, ctx, strategy="correct"):
        errors = []

        try:
            self._instructions(ctx, errors)
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
                    "er40_failure",
                    {"errors": errors},
                )
            except Exception:
                pass

            try:
                self._send_ctrl_period(ctx)
            except Exception as skip_exc:
                errors.append(f"Could not skip ER40 after failure: {skip_exc}")

            return TestRunResult(status="FAIL", errors=errors)