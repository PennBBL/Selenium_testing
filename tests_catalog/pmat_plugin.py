import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from tests_catalog.common import TestRunResult
from core.continue_utils import click_continue


class PMATPlugin:
    exact_code = "pmat24-a-2.00-ff"

    exact_codes = {
        "pmat24-a-2.00-ff",
        "zn_CN-pmat24-a-2.00-ff",
        "zh_CN-pmat24-a-2.00-ff",
    }

    PRACTICE_RESPONSES = [2, 3, 2]

    TEST_RESPONSES_CORRECT = [
        3,  # pmat12
        5,  # pmat22
        4,  # pmat67
        2,  # pmat16
        1,  # pmat11
        5,  # pmat70
        3,  # pmat23
        1,  # pmat08
        1,  # pmat63
        2,  # pmat48
        5,  # pmat24
        1,  # pmat76
        4,  # pmat21
        2,  # pmat35
        1,  # pmat72
        5,  # pmat51
        2,  # pmat38
        5,  # pmat75
        1,  # pmat39
        1,  # pmat31
        4,  # pmat37
        2,  # pmat27
        5,  # pmat32
        5,  # pmat36
    ]

    TEST_TRIALS = 24
    RESPONSE_VALUES = [1, 2, 3, 4, 5]

    RESPONSE_SELECTOR = ".pmat--responses > .button"

    def _visible_enabled(self, element):
        try:
            return element.is_displayed() and element.is_enabled()
        except Exception:
            return False

    def _continue_visible(self, ctx):
        selectors = [
            "button.continue-button",
            "button.button.continue-button",
            "button.button.continue-button.center--horizontal",
        ]

        for selector in selectors:
            for button in ctx.driver.find_elements(By.CSS_SELECTOR, selector):
                if self._visible_enabled(button):
                    return True

        return False

    def _response_elements_visible(self, ctx):
        return len(self._get_response_elements(ctx, timeout=0)) >= 5

    def _get_response_elements(self, ctx, timeout=15):
        """
        PMAT practice:
            .responses .pmat--responses > .button

        PMAT main:
            .pmat--responses > .button

        Return exactly five direct response buttons, left-to-right.
        """

        def find_buttons(driver):
            containers = [
                el for el in driver.find_elements(By.CSS_SELECTOR, ".pmat--responses")
                if self._visible_enabled(el)
            ]

            if not containers:
                return False

            best_buttons = []

            for container in containers:
                buttons = [
                    el for el in container.find_elements(By.CSS_SELECTOR, ":scope > .button")
                    if self._visible_enabled(el)
                ]

                if len(buttons) > len(best_buttons):
                    best_buttons = buttons

            if len(best_buttons) < 5:
                return False

            best_buttons = sorted(
                best_buttons,
                key=lambda el: (
                    round(el.rect.get("y", 0) / 20),
                    el.rect.get("x", 0),
                ),
            )

            return best_buttons[:5]

        if timeout <= 0:
            result = find_buttons(ctx.driver)
            return result if result else []

        return WebDriverWait(ctx.driver, timeout).until(find_buttons)

    def _current_response_srcs(self, ctx):
        try:
            buttons = self._get_response_elements(ctx, timeout=0)
            srcs = []

            for button in buttons:
                imgs = button.find_elements(By.CSS_SELECTOR, "img")
                srcs.append(imgs[0].get_attribute("src") if imgs else "")

            return srcs if len(srcs) == 5 else []
        except Exception:
            return []

    def _click_response(self, ctx, response_value, label=""):
        if response_value not in self.RESPONSE_VALUES:
            raise ValueError(f"Invalid PMAT response value: {response_value}")

        buttons = self._get_response_elements(ctx, timeout=20)

        if len(buttons) != 5:
            raise RuntimeError(f"PMAT expected 5 response buttons, found {len(buttons)}")

        target = buttons[response_value - 1]

        debug = ctx.driver.execute_script(
            """
            const el = arguments[0];
            const r = el.getBoundingClientRect();
            const img = el.querySelector("img");
            return {
                tag: el.tagName,
                className: el.className,
                imgAlt: img ? img.alt : "",
                rect: {x: r.x, y: r.y, width: r.width, height: r.height}
            };
            """,
            target,
        )

        ctx.logger.info(
            "PMAT clicking response %s %s target=%s",
            response_value,
            label,
            debug,
        )

        ctx.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            target,
        )
        time.sleep(0.1)

        try:
            target.click()
        except Exception:
            ctx.driver.execute_script(
                """
                const el = arguments[0];
                const r = el.getBoundingClientRect();
                const x = r.left + r.width / 2;
                const y = r.top + r.height / 2;

                for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
                    const ev = new MouseEvent(type, {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        clientX: x,
                        clientY: y
                    });
                    el.dispatchEvent(ev);
                }
                """,
                target,
            )

    def _click_continue_if_present(self, ctx, label, timeout=3):
        try:
            click_continue(ctx, label=f"PMAT {label}", timeout=timeout, delay=0.3)
            return True
        except Exception:
            return False

    def _click_continue_required(self, ctx, label, timeout=20):
        if self._response_elements_visible(ctx):
            ctx.logger.info(
                "PMAT %s: response buttons already visible; skipping continue",
                label,
            )
            return

        click_continue(ctx, label=f"PMAT {label}", timeout=timeout, delay=0.5)

    def _wait_until_responses_change_or_continue(self, ctx, previous_srcs, timeout=8):
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self._continue_visible(ctx):
                return "continue"

            current_srcs = self._current_response_srcs(ctx)
            if current_srcs and current_srcs != previous_srcs:
                return "next_trial"

            time.sleep(0.1)

        return "timeout"

    def _instructions_to_practice(self, ctx):
        # run_battery already clicked the landing-page continue.
        self._click_continue_required(ctx, "instructions", timeout=20)
        self._click_continue_required(ctx, "begin practice", timeout=20)

    def _run_practice(self, ctx):
        for trial_index, response in enumerate(self.PRACTICE_RESPONSES, start=1):
            previous_srcs = self._current_response_srcs(ctx)

            ctx.logger.info(
                "PMAT practice trial %d/%d: clicking response %s",
                trial_index,
                len(self.PRACTICE_RESPONSES),
                response,
            )

            self._click_response(ctx, response, label=f"practice {trial_index}")
            time.sleep(0.3)

            state = self._wait_until_responses_change_or_continue(
                ctx,
                previous_srcs=previous_srcs,
                timeout=8,
            )

            ctx.logger.info("PMAT practice trial %d advanced by %s", trial_index, state)

            if trial_index < len(self.PRACTICE_RESPONSES):
                self._click_continue_if_present(
                    ctx,
                    f"after practice trial {trial_index}",
                    timeout=4,
                )

        self._click_continue_required(ctx, "post-practice instructions", timeout=20)
        self._click_continue_required(ctx, "begin test", timeout=20)

    def _main_test(self, ctx, strategy):
        trial_count = 0

        while trial_count < self.TEST_TRIALS:
            try:
                self._get_response_elements(ctx, timeout=20)
            except Exception:
                break

            if strategy == "random":
                response = random.choice(self.RESPONSE_VALUES)
            elif strategy == "sequential":
                response = self.RESPONSE_VALUES[trial_count % len(self.RESPONSE_VALUES)]
            else:
                response = self.TEST_RESPONSES_CORRECT[trial_count]

            trial_count += 1
            previous_srcs = self._current_response_srcs(ctx)

            ctx.logger.info(
                "PMAT main trial %d/%d: clicking response %s",
                trial_count,
                self.TEST_TRIALS,
                response,
            )

            time.sleep(random.uniform(0.25, 0.7))
            self._click_response(ctx, response, label=f"main {trial_count}")
            time.sleep(0.25)

            state = self._wait_until_responses_change_or_continue(
                ctx,
                previous_srcs=previous_srcs,
                timeout=8,
            )

            ctx.logger.info("PMAT main trial %d advanced by %s", trial_count, state)

            self._click_continue_if_present(
                ctx,
                f"after main trial {trial_count}",
                timeout=1,
            )

        ctx.logger.info("PMAT completed %d main trials", trial_count)

        if strategy != "random" and trial_count != self.TEST_TRIALS:
            raise RuntimeError(
                f"PMAT expected {self.TEST_TRIALS} main trials, completed {trial_count}"
            )

    def run(self, ctx, strategy="correct"):
        errors = []

        try:
            ctx.logger.info("PMAT starting language-agnostic Form A plugin")

            self._instructions_to_practice(ctx)
            self._run_practice(ctx)
            self._main_test(ctx, strategy=strategy)

            return TestRunResult(status="PASS", errors=errors)

        except Exception as exc:
            errors.append(str(exc))
            ctx.logger.exception("PMAT failed")
            ctx.artifacts.capture_failure(
                ctx.driver,
                "pmat_failure",
                {"errors": errors},
            )
            return TestRunResult(status="FAIL", errors=errors)