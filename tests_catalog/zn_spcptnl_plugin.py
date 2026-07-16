import base64
import io
import time
from pathlib import Path

from PIL import Image, ImageChops
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue


class ZN_SPCPTNLPlugin:
    exact_code = "zn_CN-spcptnl-2.01-ff"

    exact_codes = {
        "zn_CN-spcptnl-2.01-ff",
        "zh_CN-spcptnl-2.01-ff",
    }

    MAIN_NUMBER_TRIALS = 5
    MAIN_LETTER_TRIALS = 5

    ASSET_DIR = Path(__file__).resolve().parent / "assets" / "spcptnl"
    PRAC_NUM_TARGET = ASSET_DIR / "pracNum1.png"
    PRAC_LET_TARGET = ASSET_DIR / "pracLet1.png"

    # App.js target settings are width=100 height=150.
    TARGET_RENDER_SIZE = (100, 150)

    def __init__(self):
        self._num_template = self._load_template(self.PRAC_NUM_TARGET)
        self._let_template = self._load_template(self.PRAC_LET_TARGET)

    def _load_template(self, path):
        if not path.exists():
            raise FileNotFoundError(f"SPCPTNL template not found: {path}")

        return Image.open(path).convert("RGB").resize(self.TARGET_RENDER_SIZE)

    def _press_space(self, ctx, label="space"):
        ctx.logger.info(f"SPCPTNL pressing space: {label}")
        body = ctx.driver.find_element(By.TAG_NAME, "body")
        body.send_keys(Keys.SPACE)

    def _click_continue_required(self, ctx, label, timeout=20):
        click_continue(ctx, label=f"SPCPTNL {label}", timeout=timeout, delay=0.5)

    def _continue_visible(self, ctx):
        selectors = [
            "button.continue-button",
            "button.button.continue-button",
            "button.button.continue-button.center--horizontal",
        ]

        for selector in selectors:
            for button in ctx.driver.find_elements(By.CSS_SELECTOR, selector):
                try:
                    if button.is_displayed() and button.is_enabled():
                        return True
                except Exception:
                    continue

        return False

    def _canvas_visible(self, ctx):
        for canvas in ctx.driver.find_elements(By.CSS_SELECTOR, ".canvas_container canvas, canvas"):
            try:
                if canvas.is_displayed():
                    return True
            except Exception:
                continue

        return False

    def _get_canvas_png(self, ctx):
        """
        Return current visible canvas as a PIL Image.
        Uses toDataURL so this is fast and avoids full-page screenshots.
        """
        data_url = ctx.driver.execute_script(
            """
            const canvas = Array.from(document.querySelectorAll("canvas"))
                .find(c => {
                    const r = c.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                });

            if (!canvas) return null;

            return canvas.toDataURL("image/png");
            """
        )

        if not data_url:
            return None

        encoded = data_url.split(",", 1)[1]
        raw = base64.b64decode(encoded)
        return Image.open(io.BytesIO(raw)).convert("RGB")

    def _crop_stimulus_region(self, canvas_image):
        """
        Find the non-background region in the canvas, crop it, and resize to the
        template size.

        This is better than assuming the stimulus is exactly centered.
        """
        image = canvas_image.convert("RGB")
        width, height = image.size

        # Use the top-left pixel as the dark/background color.
        bg_color = image.getpixel((0, 0))

        # Build a mask of pixels that differ from background enough to be stimulus.
        # The canvas background is dark; the line stimuli are lighter.
        pixels = image.load()

        min_x = width
        min_y = height
        max_x = 0
        max_y = 0
        found = False

        threshold = 25

        for y in range(0, height, 2):
            for x in range(0, width, 2):
                r, g, b = pixels[x, y]
                br, bg, bb = bg_color

                diff = abs(r - br) + abs(g - bg) + abs(b - bb)

                if diff > threshold:
                    found = True
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)

        if not found:
            return image.resize(self.TARGET_RENDER_SIZE)

        # Add padding so we do not cut off antialiasing.
        pad = 20
        left = max(0, min_x - pad)
        top = max(0, min_y - pad)
        right = min(width, max_x + pad)
        bottom = min(height, max_y + pad)

        crop = image.crop((left, top, right, bottom))

        return crop.resize(self.TARGET_RENDER_SIZE)

    def _image_difference_score(self, img_a, img_b):
        """
        Lower is better. 0 means exact match.
        Normalized average per-channel difference, roughly 0-255.
        """
        diff = ImageChops.difference(img_a.convert("RGB"), img_b.convert("RGB"))
        hist = diff.histogram()

        total = 0
        count = 0

        for value, pixels in enumerate(hist):
            channel_value = value % 256
            total += channel_value * pixels
            count += pixels

        return total / max(count, 1)

    def _canvas_matches_template(self, ctx, template, threshold=18.0):
        canvas_image = self._get_canvas_png(ctx)

        if canvas_image is None:
            return False, None

        stimulus = self._crop_stimulus_region(canvas_image)
        score = self._image_difference_score(stimulus, template)

        return score <= threshold, score

    def _wait_through_countdown(self, seconds=5.5):
        time.sleep(seconds)

    def _run_practice_with_template(self, ctx, template, label, timeout=180):
        """
        Poll the canvas quickly. Press space only when the current canvas
        resembles the target template. Practice ends when a continue button
        appears.
        """
        ctx.logger.info(f"SPCPTNL starting {label} practice with template matching")

        deadline = time.time() + timeout
        target_currently_visible = False
        target_presses = 0
        last_feedback_space = 0
        last_log = 0

        while time.time() < deadline:
            if self._continue_visible(ctx):
                ctx.logger.info(
                    f"SPCPTNL {label} practice complete; target_presses={target_presses}"
                )
                return

            if self._canvas_visible(ctx):
                matched, score = self._canvas_matches_template(
                    ctx,
                    template,
                    threshold=18.0,
                )

                now = time.time()
                if now - last_log > 2 and score is not None:
                    ctx.logger.info(
                        "SPCPTNL %s practice template score=%.2f matched=%s",
                        label,
                        score,
                        matched,
                    )
                    last_log = now

                if matched and not target_currently_visible:
                    self._press_space(ctx, f"{label} target match score={score:.2f}")
                    target_presses += 1
                    target_currently_visible = True

                if not matched:
                    target_currently_visible = False

            else:
                # Feedback/interstitial screens may require space to continue.
                now = time.time()
                if now - last_feedback_space > 0.8:
                    self._press_space(ctx, f"{label} feedback/interstitial")
                    last_feedback_space = now

            time.sleep(0.04)

        raise RuntimeError(
            f"SPCPTNL {label} practice did not finish; target_presses={target_presses}"
        )

    def _start_number_practice(self, ctx):
        self._click_continue_required(ctx, "initial instructions", timeout=20)
        self._click_continue_required(ctx, "begin number practice", timeout=20)
        self._wait_through_countdown(seconds=5.5)

    def _start_letter_practice(self, ctx):
        self._click_continue_required(ctx, "letter instructions", timeout=20)
        self._click_continue_required(ctx, "begin letter practice", timeout=20)
        self._wait_through_countdown(seconds=5.5)

    def _start_main_test(self, ctx):
        self._click_continue_required(ctx, "post-letter-practice instructions 1", timeout=20)
        self._click_continue_required(ctx, "post-letter-practice instructions 2", timeout=20)
        self._click_continue_required(ctx, "begin test", timeout=20)
        self._wait_through_countdown(seconds=5.5)

    def _run_main_timed_block(self, ctx, label, expected_trials=5):
        """
        Main test has 5 sampled target stimuli per block.
        Stimulus duration 1000ms, blank 700ms.
        Press once roughly per stimulus.
        """
        ctx.logger.info(f"SPCPTNL starting main {label} timed block")

        for i in range(1, expected_trials + 1):
            self._press_space(ctx, f"{label} main trial {i}")
            time.sleep(1.65)

        ctx.logger.info(f"SPCPTNL completed main {label} timed block")

    def _wait_for_switch_to_letters(self):
        # App.js switch message duration is 3000 ms.
        time.sleep(3.2)

    def run(self, ctx, strategy="correct"):
        errors = []

        try:
            ctx.logger.info("SPCPTNL Chinese starting")

            self._start_number_practice(ctx)
            self._run_practice_with_template(
                ctx,
                template=self._num_template,
                label="number",
                timeout=180,
            )

            self._start_letter_practice(ctx)
            self._run_practice_with_template(
                ctx,
                template=self._let_template,
                label="letter",
                timeout=180,
            )

            self._start_main_test(ctx)

            self._run_main_timed_block(
                ctx,
                label="number",
                expected_trials=self.MAIN_NUMBER_TRIALS,
            )

            self._wait_for_switch_to_letters()

            self._run_main_timed_block(
                ctx,
                label="letter",
                expected_trials=self.MAIN_LETTER_TRIALS,
            )

            return TestRunResult(status="PASS", errors=errors)

        except Exception as exc:
            errors.append(str(exc))
            ctx.logger.exception("SPCPTNL Chinese failed")
            ctx.artifacts.capture_failure(
                ctx.driver,
                "zn_spcptnl_failure",
                {"errors": errors},
            )
            return TestRunResult(status="FAIL", errors=errors)