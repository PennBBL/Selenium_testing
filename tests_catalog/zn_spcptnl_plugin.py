import base64
import io
import time
from pathlib import Path

from PIL import Image, ImageChops
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue


class ZN_SPCPTNLPlugin:
    exact_code = "zn_CN-spcptnl-2.01-ff"

    exact_codes = {
        "zn_CN-spcptnl-2.01-ff",
        "zh_CN-spcptnl-2.01-ff",
        "kr_KR-spcptnl-2.01-ff",
    }

    MAIN_NUMBER_TRIALS = 5
    MAIN_LETTER_TRIALS = 5

    ASSET_DIR = Path(__file__).resolve().parent / "assets" / "spcptnl"
    PRAC_NUM_TARGET = ASSET_DIR / "pracNum1.png"
    PRAC_LET_TARGET = ASSET_DIR / "pracLet1.png"

    # App.js target settings are width=100 height=150.
    TARGET_RENDER_SIZE = (100, 150)

    CONTINUE_SELECTORS = [
        "button.continue-button",
        "button.button.continue-button",
        "button.button.continue-button.center--horizontal",
    ]

    def __init__(self):
        self._num_template = self._load_template(self.PRAC_NUM_TARGET)
        self._let_template = self._load_template(self.PRAC_LET_TARGET)

    def _load_template(self, path):
        if not path.exists():
            raise FileNotFoundError(f"SPCPTNL template not found: {path}")

        return Image.open(path).convert("RGB").resize(self.TARGET_RENDER_SIZE)

    def _press_space(self, ctx, label="space"):
        """
        Robust Space press for headless Chrome.

        The earlier version only used body.send_keys(Keys.SPACE), which can fail
        if the app/canvas does not have focus in headless mode.
        """
        ctx.logger.info(f"SPCPTNL pressing space: {label}")

        try:
            ctx.driver.execute_script(
                """
                window.focus();
                if (document.body) {
                    document.body.focus();
                }
                """
            )
        except Exception:
            pass

        # Best path for Chrome/headless Chrome.
        try:
            key_event = {
                "key": " ",
                "code": "Space",
                "windowsVirtualKeyCode": 32,
                "nativeVirtualKeyCode": 32,
                "text": " ",
                "unmodifiedText": " ",
            }

            ctx.driver.execute_cdp_cmd(
                "Input.dispatchKeyEvent",
                {"type": "keyDown", **key_event},
            )
            time.sleep(0.03)
            ctx.driver.execute_cdp_cmd(
                "Input.dispatchKeyEvent",
                {"type": "keyUp", **key_event},
            )
            return
        except Exception:
            ctx.logger.warning("SPCPTNL CDP Space failed; trying ActionChains")

        try:
            ActionChains(ctx.driver).send_keys(Keys.SPACE).perform()
            return
        except Exception:
            ctx.logger.warning("SPCPTNL ActionChains Space failed; trying body.send_keys")

        body = ctx.driver.find_element(By.TAG_NAME, "body")
        body.click()
        body.send_keys(Keys.SPACE)

    def _click_continue_required(self, ctx, label, timeout=20):
        click_continue(ctx, label=f"SPCPTNL {label}", timeout=timeout, delay=0.5)

    def _continue_visible(self, ctx):
        for selector in self.CONTINUE_SELECTORS:
            try:
                buttons = ctx.driver.find_elements(By.CSS_SELECTOR, selector)
            except Exception:
                continue

            for button in buttons:
                try:
                    if button.is_displayed() and button.is_enabled():
                        return True
                except Exception:
                    continue

        return False

    def _click_continue_if_visible(self, ctx, label="continue"):
        for selector in self.CONTINUE_SELECTORS:
            try:
                buttons = ctx.driver.find_elements(By.CSS_SELECTOR, selector)
            except Exception:
                continue

            for button in buttons:
                try:
                    if button.is_displayed() and button.is_enabled():
                        ctx.logger.info(f"SPCPTNL clicking visible continue: {label}")
                        ctx.driver.execute_script("arguments[0].click();", button)
                        time.sleep(0.5)
                        return True
                except Exception:
                    continue

        return False

    def _canvas_visible(self, ctx):
        try:
            canvases = ctx.driver.find_elements(By.CSS_SELECTOR, ".canvas_container canvas, canvas")
        except Exception:
            return False

        for canvas in canvases:
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

        bg_color = image.getpixel((0, 0))
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

def _feedback_spacebar_visible(self, ctx):
    """
    Feedback pages explicitly show '按空格键继续'.

    Important: these pages may still contain the old canvas, so this check
    must run before canvas/template matching.
    """
    try:
        tables = ctx.driver.find_elements(By.CSS_SELECTOR, ".spacebar-response--table")
        for table in tables:
            if table.is_displayed():
                return True
    except Exception:
        pass

    try:
        body_text = ctx.driver.find_element(By.TAG_NAME, "body").text
        return (
            "按空格键继续" in body_text
            or "Press spacebar to continue" in body_text
        )
    except Exception:
        return False


def _wait_for_feedback_to_clear(self, ctx, timeout=5):
    deadline = time.time() + timeout

    while time.time() < deadline:
        if not self._feedback_spacebar_visible(ctx):
            return True
        time.sleep(0.1)

    return False


def _run_practice_with_template(self, ctx, template, label, timeout=180):
    """
    App.js-confirmed practice logic:

    - sampleSize: 3
    - terminate: 3 consecutive correct
    - only pracNum1/pracLet1 has correct: 32
    - non-target practice images should receive no response
    - feedback page uses '按空格键继续'
    """
    ctx.logger.info(f"SPCPTNL starting {label} practice with template matching")

    deadline = time.time() + timeout
    target_presses = 0
    feedback_clears = 0

    target_active = False
    last_matched_time = 0
    last_target_press = 0
    last_log = 0
    last_score = None
    last_matched = False

    target_press_cooldown = 1.4

    while time.time() < deadline:
        now = time.time()

        # 1. Practice complete.
        if self._continue_visible(ctx):
            ctx.logger.info(
                f"SPCPTNL {label} practice complete; "
                f"target_presses={target_presses}; "
                f"feedback_clears={feedback_clears}"
            )
            return

        # 2. Feedback page.
        # Must be checked before canvas, because feedback page can retain canvas.
        if self._feedback_spacebar_visible(ctx):
            ctx.logger.info(
                f"SPCPTNL {label} feedback page visible; pressing Space to continue"
            )
            self._press_space(ctx, f"{label} feedback continue")
            feedback_clears += 1
            self._wait_for_feedback_to_clear(ctx, timeout=5)

            target_active = False
            time.sleep(0.3)
            continue

        # 3. Practice stimulus canvas.
        if self._canvas_visible(ctx):
            matched, score = self._canvas_matches_template(
                ctx,
                template,
                threshold=18.0,
            )

            last_score = score
            last_matched = matched

            if now - last_log > 2 and score is not None:
                ctx.logger.info(
                    "SPCPTNL %s practice template score=%.2f matched=%s "
                    "target_active=%s target_presses=%s feedback_clears=%s",
                    label,
                    score,
                    matched,
                    target_active,
                    target_presses,
                    feedback_clears,
                )
                last_log = now

            if matched:
                last_matched_time = now

                if not target_active and now - last_target_press >= target_press_cooldown:
                    self._press_space(ctx, f"{label} target match score={score:.2f}")
                    target_presses += 1
                    last_target_press = now
                    target_active = True
                    time.sleep(0.35)

            else:
                # Do not press Space on non-target practice images.
                # Just wait for the next stimulus.
                if target_active and now - last_matched_time > 0.5:
                    target_active = False

        else:
            # No feedback, no continue, no canvas. Wait.
            time.sleep(0.1)

        time.sleep(0.06)

    raise RuntimeError(
        f"SPCPTNL {label} practice did not finish; "
        f"target_presses={target_presses}; "
        f"feedback_clears={feedback_clears}; "
        f"last_score={last_score}; "
        f"last_matched={last_matched}"
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
        Stimulus duration is about 1000 ms, blank about 700 ms.
        Press once roughly per stimulus.
        """
        ctx.logger.info(f"SPCPTNL starting main {label} timed block")

        for i in range(1, expected_trials + 1):
            self._press_space(ctx, f"{label} main trial {i}")
            time.sleep(1.65)

        ctx.logger.info(f"SPCPTNL completed main {label} timed block")

    def _wait_for_switch_to_letters(self):
        # App.js switch message duration is about 3000 ms.
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

            try:
                ctx.artifacts.capture_failure(
                    ctx.driver,
                    "zn_spcptnl_failure",
                    {"errors": errors},
                )
            except Exception:
                ctx.logger.exception("Could not capture SPCPTNL Chinese failure artifact")

            return TestRunResult(status="FAIL", errors=errors)


# Compatibility alias only.
# The English test should still use tests_catalog/spcptnl_plugin.py.
SPCPTNLPlugin = ZN_SPCPTNLPlugin
