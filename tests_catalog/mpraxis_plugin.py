import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue


class MPraxisPlugin:
    exact_code = "mpraxis-2.06-ff"

    exact_codes = {
        "mpraxis-2.06-ff",
        "zn_CN-mpraxis-2.06-ff",
    }

    # App.js praxis coordinates are in a 600 x 400 logical coordinate system.
    # The visible canvas may render as 800 x 600, or another size depending on
    # browser window/headless/display. Always scale from logical -> displayed.
    LOGICAL_CANVAS_WIDTH = 600
    LOGICAL_CANVAS_HEIGHT = 400

    PRACTICE_TRIALS = [
        {"quest": 1, "x": 188, "y": 3, "w": 407, "h": 368},
        {"quest": 2, "x": 5.5, "y": 44.8, "w": 350, "h": 333},
        {"quest": 3, "x": 275.4, "y": 0.55, "w": 323, "h": 306},
        {"quest": 4, "x": 5, "y": 4, "w": 302, "h": 288},
        {"quest": 5, "x": 299, "y": 88, "w": 293, "h": 265},
        {"quest": 6, "x": 4.6, "y": 97.6, "w": 261, "h": 244},
        {"quest": 7, "x": 332.1, "y": 11.8, "w": 255, "h": 224},
        {"quest": 8, "x": 5.2, "y": 45.1, "w": 232, "h": 194},
        {"quest": 9, "x": 365.6, "y": 194.7, "w": 226, "h": 181},
        {"quest": 10, "x": 380.1, "y": 3.2, "w": 214.1, "h": 166},
        {"quest": 11, "x": 4.8, "y": 5.8, "w": 198, "h": 147},
        {"quest": 12, "x": 415.8, "y": 222.85, "w": 176.9, "h": 124},
        {"quest": 13, "x": 113.3, "y": 138.3, "w": 157, "h": 102},
        {"quest": 14, "x": 470.9, "y": 0.8, "w": 126.9, "h": 80},
        {"quest": 15, "x": 44.4, "y": 250.3, "w": 115, "h": 59},
        {"quest": 16, "x": 263.9, "y": 17.9, "w": 94, "h": 40},
        {"quest": 17, "x": 366.4, "y": 286.4, "w": 76, "h": 36},
        {"quest": 18, "x": 223.8, "y": 11.9, "w": 57.1, "h": 30},
        {"quest": 19, "x": 558.4, "y": 25.4, "w": 39, "h": 25},
        {"quest": 20, "x": 123.45, "y": 143.45, "w": 21.1, "h": 21.1},
    ]

    TEST_TRIALS = [
        {"quest": 21, "x": 187.8, "y": 3.05, "w": 407.1, "h": 367.9},
        {"quest": 22, "x": 5.5, "y": 44.8, "w": 350, "h": 333},
        {"quest": 23, "x": 275.4, "y": 0.55, "w": 323, "h": 306},
        {"quest": 24, "x": 5.05, "y": 4, "w": 302, "h": 288},
        {"quest": 25, "x": 299, "y": 88, "w": 293, "h": 265},
        {"quest": 26, "x": 4.6, "y": 97.6, "w": 261, "h": 244},
        {"quest": 27, "x": 339.1, "y": 15.2, "w": 255, "h": 224},
        {"quest": 28, "x": 5.2, "y": 45.1, "w": 232, "h": 194},
        {"quest": 29, "x": 365.6, "y": 194.7, "w": 226, "h": 181},
        {"quest": 30, "x": 380.1, "y": 3.2, "w": 214.1, "h": 166},
        {"quest": 31, "x": 4.8, "y": 5.8, "w": 198, "h": 147},
        {"quest": 32, "x": 415.8, "y": 222.85, "w": 176.9, "h": 124},
        {"quest": 33, "x": 113.3, "y": 138.3, "w": 157, "h": 102},
        {"quest": 34, "x": 470.9, "y": 0.8, "w": 126.9, "h": 80},
        {"quest": 35, "x": 44.4, "y": 250.3, "w": 115, "h": 59},
        {"quest": 36, "x": 263.9, "y": 17.9, "w": 94, "h": 40},
        {"quest": 37, "x": 366.4, "y": 286.4, "w": 76, "h": 36},
        {"quest": 38, "x": 223.8, "y": 11.9, "w": 57.1, "h": 30},
        {"quest": 39, "x": 533.4, "y": 25.4, "w": 39, "h": 25},
        {"quest": 40, "x": 123.45, "y": 143.45, "w": 21.1, "h": 21.1},
    ]

    def _click_continue_if_present(self, ctx, label, timeout=4):
        try:
            click_continue(ctx, label=f"MPraxis {label}", timeout=timeout, delay=0.5)
            return True
        except Exception:
            return False

    def _canvas_present(self, ctx):
        canvases = [
            canvas
            for canvas in ctx.driver.find_elements(By.CSS_SELECTOR, ".canvas_container canvas, canvas")
            if canvas.is_displayed()
        ]
        return len(canvases) > 0

    def _click_continue_required(self, ctx, label, timeout=20):
        if self._canvas_present(ctx):
            ctx.logger.info(f"MPraxis {label}: canvas already present; skipping continue")
            return

        click_continue(ctx, label=f"MPraxis {label}", timeout=timeout, delay=1)

    def _wait_for_canvas(self, ctx, timeout=15):
        return WebDriverWait(ctx.driver, timeout).until(
            lambda d: next(
                (
                    canvas
                    for canvas in d.find_elements(By.CSS_SELECTOR, ".canvas_container canvas, canvas")
                    if canvas.is_displayed()
                ),
                None,
            )
        )

    def _trial_logical_center(self, trial):
        center_x = trial["x"] + trial["w"] / 2
        center_y = trial["y"] + trial["h"] / 2
        return center_x, center_y

    def _click_canvas_point(self, ctx, trial):
        canvas = self._wait_for_canvas(ctx, timeout=15)
        logical_x, logical_y = self._trial_logical_center(trial)

        result = ctx.driver.execute_script(
            """
            const canvas = arguments[0];
            const logicalX = arguments[1];
            const logicalY = arguments[2];
            const logicalWidth = arguments[3];
            const logicalHeight = arguments[4];

            const rect = canvas.getBoundingClientRect();

            const displayX = logicalX * (rect.width / logicalWidth);
            const displayY = logicalY * (rect.height / logicalHeight);

            const clientX = rect.left + displayX;
            const clientY = rect.top + displayY;

            const eventInit = {
                bubbles: true,
                cancelable: true,
                view: window,
                clientX: clientX,
                clientY: clientY,
                screenX: window.screenX + clientX,
                screenY: window.screenY + clientY,
                button: 0
            };

            const targets = [canvas, canvas.parentElement].filter(Boolean);

            for (const target of targets) {
                target.dispatchEvent(new MouseEvent("mousemove", {
                    ...eventInit,
                    buttons: 0
                }));

                target.dispatchEvent(new MouseEvent("mousedown", {
                    ...eventInit,
                    buttons: 1
                }));

                target.dispatchEvent(new MouseEvent("mouseup", {
                    ...eventInit,
                    buttons: 0
                }));

                target.dispatchEvent(new MouseEvent("click", {
                    ...eventInit,
                    buttons: 0
                }));
            }

            return {
                rectLeft: rect.left,
                rectTop: rect.top,
                rectWidth: rect.width,
                rectHeight: rect.height,
                logicalX: logicalX,
                logicalY: logicalY,
                displayX: displayX,
                displayY: displayY,
                clientX: clientX,
                clientY: clientY,
                devicePixelRatio: window.devicePixelRatio,
                innerWidth: window.innerWidth,
                innerHeight: window.innerHeight
            };
            """,
            canvas,
            logical_x,
            logical_y,
            self.LOGICAL_CANVAS_WIDTH,
            self.LOGICAL_CANVAS_HEIGHT,
        )

        ctx.logger.info(
            "MPraxis quest %s: logical=(%.1f, %.1f) display=(%.1f, %.1f) "
            "canvas=(%.0fx%.0f) dpr=%.2f window=(%sx%s)",
            trial["quest"],
            result["logicalX"],
            result["logicalY"],
            result["displayX"],
            result["displayY"],
            result["rectWidth"],
            result["rectHeight"],
            result["devicePixelRatio"],
            result["innerWidth"],
            result["innerHeight"],
        )

    def _instructions_to_practice(self, ctx):
        # Landing Continue is already clicked by run_battery.
        self._click_continue_required(ctx, "instruction page", timeout=20)
        self._click_continue_required(ctx, "begin practice", timeout=20)

    def _practice(self, ctx):
        completed = 0

        for trial in self.PRACTICE_TRIALS:
            self._click_canvas_point(ctx, trial)
            completed += 1
            time.sleep(0.35)

        ctx.logger.info(f"MPraxis completed {completed} practice trials")

        if completed != len(self.PRACTICE_TRIALS):
            raise RuntimeError(
                f"MPraxis expected {len(self.PRACTICE_TRIALS)} practice trials, completed {completed}"
            )

        # After practice, the task shows one instruction page, then BEGIN TEST.
        self._click_continue_required(ctx, "post-practice instructions", timeout=20)
        self._click_continue_required(ctx, "begin test", timeout=20)

    def _test(self, ctx):
        completed = 0

        for trial in self.TEST_TRIALS:
            self._click_canvas_point(ctx, trial)
            completed += 1
            time.sleep(0.25)

        ctx.logger.info(f"MPraxis completed {completed} test trials")

        if completed != len(self.TEST_TRIALS):
            raise RuntimeError(
                f"MPraxis expected {len(self.TEST_TRIALS)} test trials, completed {completed}"
            )

    def run(self, ctx, strategy="coordinate"):
        errors = []

        try:
            ctx.logger.info("MPraxis starting")

            self._instructions_to_practice(ctx)
            self._practice(ctx)
            self._test(ctx)

            return TestRunResult(status="PASS", errors=errors)

        except Exception as exc:
            errors.append(str(exc))
            ctx.logger.exception("MPraxis failed")
            ctx.artifacts.capture_failure(ctx.driver, "mpraxis_failure", {"errors": errors})
            return TestRunResult(status="FAIL", errors=errors)