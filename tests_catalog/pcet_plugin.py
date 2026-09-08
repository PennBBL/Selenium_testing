import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue


class PCETPlugin:
    exact_code = "k-pcet-3.00-ff"

    exact_codes = {
        "k-pcet-3.00-ff",
        "zn_CN-k-pcet-3.00-ff",
        "zh_CN-k-pcet-3.00-ff",
    }

    BLOCKS_TO_PASS = 3
    CORRECT_NEEDED_PER_BLOCK = 10

    CANVAS_SELECTOR = ".canvas_container canvas, .stimulus--plot canvas, canvas"

    # First 10 trials from each rule block.
    # Each block ends after 10 consecutive correct:
    # terminate: {correct: 10, consecutive: true}
    #
    # The response index is the position in the responses array.
    # The live canvas draws those responses left-to-right.
    BLOCK_TRIALS = [
        [
            {"correct": 1, "responses": [3, 1, 4, 2]},
            {"correct": 1, "responses": [1, 4, 3, 2]},
            {"correct": 1, "responses": [4, 23, 1, 4]},
            {"correct": 1, "responses": [4, 3, 2, 1]},
            {"correct": 12, "responses": [12, 3, 4, 4]},
            {"correct": 1, "responses": [4, 3, 2, 1]},
            {"correct": 1, "responses": [4, 1, 2, 3]},
            {"correct": 13, "responses": [2, 4, 4, 13]},
            {"correct": 13, "responses": [2, 4, 13, 4]},
            {"correct": 1, "responses": [4, 4, 1, 23]},
        ],
        [
            {"correct": 2, "responses": [3, 1, 4, 2]},
            {"correct": 2, "responses": [1, 4, 3, 2]},
            {"correct": 23, "responses": [4, 23, 2, 4]},
            {"correct": 2, "responses": [4, 3, 2, 1]},
            {"correct": 12, "responses": [12, 3, 4, 4]},
            {"correct": 2, "responses": [4, 3, 2, 1]},
            {"correct": 2, "responses": [4, 1, 2, 3]},
            {"correct": 2, "responses": [2, 4, 4, 13]},
            {"correct": 2, "responses": [2, 4, 13, 4]},
            {"correct": 23, "responses": [4, 4, 1, 23]},
        ],
        [
            {"correct": 3, "responses": [3, 1, 4, 2]},
            {"correct": 3, "responses": [1, 4, 3, 2]},
            {"correct": 23, "responses": [4, 23, 1, 4]},
            {"correct": 3, "responses": [4, 3, 2, 1]},
            {"correct": 3, "responses": [12, 3, 4, 4]},
            {"correct": 3, "responses": [4, 3, 2, 1]},
            {"correct": 3, "responses": [4, 1, 2, 3]},
            {"correct": 13, "responses": [2, 4, 4, 13]},
            {"correct": 13, "responses": [2, 4, 13, 4]},
            {"correct": 23, "responses": [4, 4, 1, 23]},
        ],
    ]

    def _visible(self, element):
        try:
            return element.is_displayed()
        except Exception:
            return False

    def _canvas_present(self, ctx):
        try:
            return any(
                self._visible(canvas)
                for canvas in ctx.driver.find_elements(By.CSS_SELECTOR, self.CANVAS_SELECTOR)
            )
        except Exception:
            return False

    def _wait_for_canvas(self, ctx, timeout=20):
        return WebDriverWait(ctx.driver, timeout).until(
            lambda driver: next(
                (
                    canvas
                    for canvas in driver.find_elements(By.CSS_SELECTOR, self.CANVAS_SELECTOR)
                    if canvas.is_displayed()
                ),
                None,
            )
        )

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
                    pass

        return False

    def _click_continue_required(self, ctx, label, timeout=20):
        if self._canvas_present(ctx):
            ctx.logger.info(f"PCET {label}: canvas already present; skipping continue")
            return

        click_continue(ctx, label=f"PCET {label}", timeout=timeout, delay=0.5)

    def _instructions_to_test(self, ctx):
        # run_battery already clicked the landing-page continue.
        self._click_continue_required(ctx, "instructions", timeout=20)
        self._click_continue_required(ctx, "begin test", timeout=20)
        self._wait_for_canvas(ctx, timeout=20)

    def _correct_response_index(self, trial):
        correct = trial["correct"]
        responses = trial["responses"]

        for index, response_value in enumerate(responses):
            if response_value == correct:
                return index

        raise RuntimeError(
            f"PCET could not find correct={correct} in responses={responses}"
        )

    def _canvas_signature(self, ctx):
        try:
            canvas = self._wait_for_canvas(ctx, timeout=2)
            return ctx.driver.execute_script(
                """
                const canvas = arguments[0];

                try {
                    return canvas.toDataURL("image/png").slice(-250);
                } catch (e) {
                    return null;
                }
                """,
                canvas,
            )
        except Exception:
            return None

    def _find_blue_object_target(self, ctx, canvas, response_index):
        """
        PCET draws the four response objects into one canvas.

        This JS reads canvas pixels, finds the four blue object groups,
        sorts them left-to-right, and returns a real blue pixel inside
        the requested object. This avoids clicking black holes inside
        hollow squares/stars.
        """
        return ctx.driver.execute_script(
            """
            const canvas = arguments[0];
            const responseIndex = arguments[1];

            const ctx2d = canvas.getContext("2d", { willReadFrequently: true });
            const width = canvas.width;
            const height = canvas.height;
            const image = ctx2d.getImageData(0, 0, width, height);
            const data = image.data;

            function isBlueAt(x, y) {
                const i = (y * width + x) * 4;
                const r = data[i];
                const g = data[i + 1];
                const b = data[i + 2];
                const a = data[i + 3];

                // PCET object color is bright blue. This ignores black background,
                // white instruction text, and gray border.
                return a > 80 && b > 120 && g > 80 && r < 100;
            }

            // Count blue pixels per x-column.
            const colCounts = new Array(width).fill(0);

            for (let y = 0; y < height; y += 2) {
                for (let x = 0; x < width; x += 2) {
                    if (isBlueAt(x, y)) {
                        colCounts[x]++;
                    }
                }
            }

            // Build horizontal groups of blue pixels.
            const rawGroups = [];
            let inGroup = false;
            let start = 0;
            let lastBlue = 0;

            const minColCount = 4;
            const maxGap = 45;

            for (let x = 0; x < width; x++) {
                if (colCounts[x] >= minColCount) {
                    if (!inGroup) {
                        inGroup = true;
                        start = x;
                    }
                    lastBlue = x;
                } else if (inGroup && x - lastBlue > maxGap) {
                    rawGroups.push({xMin: start, xMax: lastBlue});
                    inGroup = false;
                }
            }

            if (inGroup) {
                rawGroups.push({xMin: start, xMax: lastBlue});
            }

            // Remove tiny noise groups and sort left-to-right.
            let groups = rawGroups
                .filter(g => (g.xMax - g.xMin) > 50)
                .sort((a, b) => a.xMin - b.xMin);

            // Sometimes anti-aliased parts split one object into nearby groups.
            // Merge close groups until we get object-level groups.
            const merged = [];
            for (const g of groups) {
                if (!merged.length) {
                    merged.push({...g});
                    continue;
                }

                const prev = merged[merged.length - 1];
                const gap = g.xMin - prev.xMax;

                if (gap < 90) {
                    prev.xMax = g.xMax;
                } else {
                    merged.push({...g});
                }
            }

            groups = merged.filter(g => (g.xMax - g.xMin) > 50);

            if (groups.length < 4) {
                return {
                    ok: false,
                    error: `Expected at least 4 blue object groups, found ${groups.length}`,
                    rawGroups,
                    groups
                };
            }

            // If more than four groups are detected, keep the four widest.
            // Then sort those left-to-right.
            if (groups.length > 4) {
                groups = groups
                    .sort((a, b) => (b.xMax - b.xMin) - (a.xMax - a.xMin))
                    .slice(0, 4)
                    .sort((a, b) => a.xMin - b.xMin);
            }

            const group = groups[responseIndex];

            if (!group) {
                return {
                    ok: false,
                    error: `No group for responseIndex ${responseIndex}`,
                    groups
                };
            }

            let yMin = height;
            let yMax = 0;
            const xMin = group.xMin;
            const xMax = group.xMax;

            const bluePixels = [];

            for (let y = 0; y < height; y++) {
                for (let x = xMin; x <= xMax; x++) {
                    if (isBlueAt(x, y)) {
                        if (y < yMin) yMin = y;
                        if (y > yMax) yMax = y;
                        bluePixels.push([x, y]);
                    }
                }
            }

            if (!bluePixels.length) {
                return {
                    ok: false,
                    error: "No blue pixels found inside selected group",
                    group,
                    groups
                };
            }

            // Choose an actual blue pixel near the visual center of this object.
            // This avoids clicking the black hole in hollow shapes.
            const cx = (xMin + xMax) / 2;
            const cy = (yMin + yMax) / 2;

            let best = bluePixels[0];
            let bestDist = Infinity;

            for (const [x, y] of bluePixels) {
                const dx = x - cx;
                const dy = y - cy;
                const dist = dx * dx + dy * dy;

                if (dist < bestDist) {
                    bestDist = dist;
                    best = [x, y];
                }
            }

            const rect = canvas.getBoundingClientRect();

            const clientX = rect.left + (best[0] / width) * rect.width;
            const clientY = rect.top + (best[1] / height) * rect.height;

            return {
                ok: true,
                responseIndex,
                logicalX: best[0],
                logicalY: best[1],
                clientX,
                clientY,
                group: {xMin, xMax, yMin, yMax},
                groups,
                canvas: {
                    width,
                    height,
                    displayWidth: rect.width,
                    displayHeight: rect.height,
                    left: rect.left,
                    top: rect.top
                }
            };
            """,
            canvas,
            response_index,
        )

    def _dispatch_cdp_click(self, ctx, x, y):
        """
        Click at viewport/client coordinates.

        Chrome/Edge:
            Use CDP Input.dispatchMouseEvent.

        Firefox:
            CDP is unavailable, so fall back to Selenium W3C pointer actions.
            If that fails, fall back to dispatching DOM mouse/pointer events.
        """
        x = int(round(x))
        y = int(round(y))

        # Chrome / Edge path.
        try:
            ctx.driver.execute_cdp_cmd(
                "Input.dispatchMouseEvent",
                {
                    "type": "mouseMoved",
                    "x": x,
                    "y": y,
                    "button": "none",
                    "buttons": 0,
                },
            )

            ctx.driver.execute_cdp_cmd(
                "Input.dispatchMouseEvent",
                {
                    "type": "mousePressed",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "buttons": 1,
                    "clickCount": 1,
                },
            )

            ctx.driver.execute_cdp_cmd(
                "Input.dispatchMouseEvent",
                {
                    "type": "mouseReleased",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "buttons": 0,
                    "clickCount": 1,
                },
            )

            return

        except Exception as exc:
            ctx.logger.info(
                "PCET CDP click unavailable; trying W3C pointer click. "
                "client=(%s, %s), error=%s",
                x,
                y,
                exc,
            )

        # Firefox-safe W3C pointer action path.
        try:
            from selenium.webdriver.common.actions import interaction
            from selenium.webdriver.common.actions.action_builder import ActionBuilder
            from selenium.webdriver.common.actions.pointer_input import PointerInput

            mouse = PointerInput(interaction.POINTER_MOUSE, "mouse")
            actions = ActionBuilder(ctx.driver, mouse=mouse)

            actions.pointer_action.move_to_location(x, y)
            actions.pointer_action.pointer_down()
            actions.pointer_action.pause(0.05)
            actions.pointer_action.pointer_up()
            actions.perform()

            return

        except Exception as exc:
            ctx.logger.info(
                "PCET W3C pointer click failed; trying DOM event fallback. "
                "client=(%s, %s), error=%s",
                x,
                y,
                exc,
            )

        # Last-resort browser-agnostic DOM event fallback.
        ctx.driver.execute_script(
            """
            const x = arguments[0];
            const y = arguments[1];
            const el = document.elementFromPoint(x, y);

            if (!el) {
                throw new Error(`No element at point ${x}, ${y}`);
            }

            function fireMouse(type, buttons) {
                const ev = new MouseEvent(type, {
                    bubbles: true,
                    cancelable: true,
                    view: window,
                    clientX: x,
                    clientY: y,
                    screenX: x,
                    screenY: y,
                    button: 0,
                    buttons: buttons
                });
                el.dispatchEvent(ev);
            }

            function firePointer(type, buttons) {
                if (!window.PointerEvent) return;

                const ev = new PointerEvent(type, {
                    bubbles: true,
                    cancelable: true,
                    view: window,
                    clientX: x,
                    clientY: y,
                    screenX: x,
                    screenY: y,
                    button: 0,
                    buttons: buttons,
                    pointerId: 1,
                    pointerType: "mouse",
                    isPrimary: true
                });
                el.dispatchEvent(ev);
            }

            firePointer("pointermove", 0);
            fireMouse("mousemove", 0);

            firePointer("pointerdown", 1);
            fireMouse("mousedown", 1);

            firePointer("pointerup", 0);
            fireMouse("mouseup", 0);

            fireMouse("click", 0);
            """,
            x,
            y,
        )

    def _wait_for_blue_object_target(self, ctx, canvas, response_index, timeout=6):
        """
        Wait until the canvas is showing the four blue PCET objects,
        then return the target blue pixel for response_index.
        """
        deadline = time.time() + timeout
        last_target = None

        while time.time() < deadline:
            target = self._find_blue_object_target(ctx, canvas, response_index)
            last_target = target

            if target and target.get("ok"):
                return target

            time.sleep(0.1)

        raise RuntimeError(f"PCET could not locate blue object target after wait: {last_target}")

    def _click_response_index(self, ctx, response_index):
        canvas = self._wait_for_canvas(ctx, timeout=20)

        if response_index not in [0, 1, 2, 3]:
            raise RuntimeError(f"PCET invalid response index: {response_index}")

        ctx.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            canvas,
        )
        time.sleep(0.1)

        target = self._wait_for_blue_object_target(
            ctx,
            canvas,
            response_index,
            timeout=6,
        )

        ctx.logger.info(
            "PCET clicking response index %s at logical=(%.1f, %.1f), "
            "client=(%.1f, %.1f), group=%s, groups=%s",
            response_index,
            target["logicalX"],
            target["logicalY"],
            target["clientX"],
            target["clientY"],
            target["group"],
            target["groups"],
        )

        self._dispatch_cdp_click(
            ctx,
            target["clientX"],
            target["clientY"],
        )

    def _wait_after_click(self, ctx, previous_signature=None, timeout=4):
        """
        Wait through feedback/transition. PCET feedbackDuration is 650 ms,
        but the next canvas can appear slightly later.
        """
        time.sleep(0.9)

        deadline = time.time() + timeout

        while time.time() < deadline:
            if self._continue_visible(ctx):
                return "continue"

            try:
                canvas = self._wait_for_canvas(ctx, timeout=1)
                probe = self._find_blue_object_target(ctx, canvas, 0)
                if probe and probe.get("ok"):
                    return "next_trial"
            except Exception:
                pass

            time.sleep(0.1)

        return "timeout"

    def _click_trial_correct(self, ctx, trial):
        response_index = self._correct_response_index(trial)

        ctx.logger.info(
            "PCET correct=%s responses=%s -> response index=%s",
            trial["correct"],
            trial["responses"],
            response_index,
        )

        before = self._canvas_signature(ctx)
        self._click_response_index(ctx, response_index)
        return self._wait_after_click(ctx, previous_signature=before, timeout=4)

    def _run_block(self, ctx, block_index, strategy):
        trials = self.BLOCK_TRIALS[block_index]
        completed = 0

        ctx.logger.info(f"PCET starting block {block_index + 1}/{self.BLOCKS_TO_PASS}")

        for trial in trials:
            self._wait_for_canvas(ctx, timeout=20)

            if strategy == "random":
                response_index = random.choice([0, 1, 2, 3])
                ctx.logger.info(
                    "PCET block %s trial %s: random response index=%s",
                    block_index + 1,
                    completed + 1,
                    response_index,
                )

                before = self._canvas_signature(ctx)
                self._click_response_index(ctx, response_index)
                state = self._wait_after_click(ctx, previous_signature=before, timeout=4)

            else:
                ctx.logger.info(
                    "PCET block %s trial %s: clicking correct",
                    block_index + 1,
                    completed + 1,
                )

                state = self._click_trial_correct(ctx, trial)

            completed += 1

            ctx.logger.info(
                "PCET block %s trial %s advanced by %s",
                block_index + 1,
                completed,
                state,
            )

        ctx.logger.info(
            "PCET completed %d trials in block %d",
            completed,
            block_index + 1,
        )

        if strategy != "random" and completed != self.CORRECT_NEEDED_PER_BLOCK:
            raise RuntimeError(
                f"PCET block {block_index + 1} expected "
                f"{self.CORRECT_NEEDED_PER_BLOCK} trials, completed {completed}"
            )

    def _main_test(self, ctx, strategy):
        for block_index in range(self.BLOCKS_TO_PASS):
            self._run_block(ctx, block_index, strategy=strategy)

            # Between block 1->2 and 2->3 there is a short auto-advancing slideblock.
            if block_index < self.BLOCKS_TO_PASS - 1:
                ctx.logger.info("PCET waiting for next rule block canvas")
                time.sleep(1.2)
                self._wait_for_canvas(ctx, timeout=20)

        ctx.logger.info("PCET completed all rule blocks")

    def run(self, ctx, strategy="correct"):
        errors = []

        try:
            ctx.logger.info("PCET starting language-agnostic plugin")

            self._instructions_to_test(ctx)
            self._main_test(ctx, strategy=strategy)

            return TestRunResult(status="PASS", errors=errors)

        except Exception as exc:
            errors.append(str(exc))
            ctx.logger.exception("PCET failed")
            ctx.artifacts.capture_failure(
                ctx.driver,
                "pcet_failure",
                {"errors": errors},
            )
            return TestRunResult(status="FAIL", errors=errors)