from __future__ import annotations

import time

from selenium.common.exceptions import TimeoutException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from core.continue_utils import click_continue
from tests_catalog.common import TestRunResult


class PVTPlugin:
    exact_code = "pvt-b-5.00-ff"

    PRACTICE_TRIALS = 2
    TEST_TRIALS = 15
    PRACTICE_RT_MS = 300
    MAIN_TEST_TRANSITION_TIMEOUT_SECONDS = 45

    STIMULUS_CONTAINER_SELECTOR = ".pvt-stimulus"
    COUNTER_SELECTOR = ".pvt-stimulus .four-digit-stimulus"
    FEEDBACK_SELECTOR = ".pvt-feedback"

    FOREPERIODS_MS = [
        2000, 2150, 2300, 2450, 2600,
        2750, 2900, 3050, 3200, 3350,
        3500, 3650, 3800, 3950, 4100,
        4250, 4400, 4550, 4700, 4850,
        5000,
    ]

    STRATEGY_DELAYS_MS = {
        "perfect_300": 300,
        "fast_210": 210,
        "upper_340": 340,
        "slow_500": 500,
        "very_slow_1000": 1000,
    }

    MIXED_DELAYS_MS = [
        300, 500, 300, 1000, 300,
        500, 300, 340, 210, 500,
        300, 1000, 300, 340, 210,
    ]

    def _wait_for_text(self, ctx, text: str, timeout: float = 20.0) -> None:
        wanted = text.lower()
        WebDriverWait(ctx.driver, timeout, poll_frequency=0.1).until(
            lambda d: wanted in (d.find_element(By.TAG_NAME, "body").text or "").lower()
        )

    def _press_space(self, ctx, label: str) -> None:
        ctx.logger.info("PVT pressing SPACE: %s", label)
        try:
            ActionChains(ctx.driver).send_keys(Keys.SPACE).perform()
        except Exception:
            ctx.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.SPACE)

    def _click_continue_if_present(self, ctx, label: str, timeout: float = 6.0) -> bool:
        try:
            click_continue(
                ctx,
                label=f"PVT {label}",
                timeout=timeout,
                delay=0.5,
            )
            return True
        except Exception:
            return False

    def _counter_visible(self, driver) -> bool:
        for element in driver.find_elements(By.CSS_SELECTOR, self.COUNTER_SELECTOR):
            try:
                text = (element.text or "").strip()
                if element.is_displayed() and text and text.isdigit():
                    return True
            except Exception:
                continue
        return False

    def _wait_for_counter_onset(self, ctx, trial_label: str, timeout: float = 8.0) -> dict:
        ctx.logger.info("PVT waiting for counter onset: %s", trial_label)

        script = r"""
const callback = arguments[arguments.length - 1];
const selector = arguments[0];
const timeoutMs = arguments[1];
const started = performance.now();

function visible(el) {
    if (!el) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const text = (el.textContent || "").trim();

    return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        Number(style.opacity || 1) > 0 &&
        rect.width > 0 &&
        rect.height > 0 &&
        /^\d+$/.test(text)
    );
}

function tick() {
    const el = document.querySelector(selector);

    if (visible(el)) {
        callback({
            found: true,
            value: (el.textContent || "").trim(),
            detectedAtPerformanceMs: performance.now(),
            waitElapsedMs: performance.now() - started
        });
        return;
    }

    if (performance.now() - started >= timeoutMs) {
        callback({
            found: false,
            waitElapsedMs: performance.now() - started
        });
        return;
    }

    requestAnimationFrame(tick);
}

tick();
"""

        try:
            ctx.driver.set_script_timeout(timeout + 2.0)
            result = ctx.driver.execute_async_script(
                script,
                self.COUNTER_SELECTOR,
                int(timeout * 1000),
            )
        except Exception as exc:
            raise RuntimeError(
                f"PVT counter-onset detection failed for {trial_label}: {exc}"
            ) from exc

        if not result or not result.get("found"):
            raise TimeoutException(
                f"PVT counter did not appear within {timeout:.1f}s for {trial_label}"
            )

        ctx.logger.info(
            "PVT counter detected for %s: value=%s foreperiod_wait_observed_ms=%.1f",
            trial_label,
            result.get("value"),
            float(result.get("waitElapsedMs") or 0.0),
        )
        return result

    def _wait_for_counter_clear(self, ctx, trial_label: str, timeout: float = 5.0) -> None:
        try:
            WebDriverWait(ctx.driver, timeout, poll_frequency=0.02).until(
                lambda d: not self._counter_visible(d)
            )
        except Exception:
            ctx.logger.warning(
                "PVT counter did not clearly disappear after %s.",
                trial_label,
            )

    def _read_feedback(self, ctx) -> str:
        try:
            element = ctx.driver.find_element(By.CSS_SELECTOR, self.FEEDBACK_SELECTOR)
            return (element.text or "").strip()
        except Exception:
            return ""

    def _wait_response_delay(self, delay_ms: int) -> None:
        target = time.perf_counter() + (delay_ms / 1000.0)

        while True:
            remaining = target - time.perf_counter()

            if remaining <= 0:
                return

            if remaining > 0.025:
                time.sleep(remaining - 0.010)
            elif remaining > 0.004:
                time.sleep(0.001)

    def _respond_after_onset(self, ctx, delay_ms: int, trial_label: str) -> dict:
        onset = self._wait_for_counter_onset(ctx, trial_label, timeout=8.0)

        local_detection_time = time.perf_counter()
        self._wait_response_delay(delay_ms)

        before_press = time.perf_counter()
        self._press_space(ctx, f"{trial_label} target={delay_ms}ms")
        after_press = time.perf_counter()

        local_wait_ms = (before_press - local_detection_time) * 1000.0
        send_duration_ms = (after_press - before_press) * 1000.0

        time.sleep(0.05)
        feedback = self._read_feedback(ctx)

        ctx.logger.info(
            "PVT response %s: requested=%dms local_wait=%.1fms "
            "webdriver_send=%.1fms feedback=%r",
            trial_label,
            delay_ms,
            local_wait_ms,
            send_duration_ms,
            feedback,
        )

        self._wait_for_counter_clear(ctx, trial_label, timeout=5.0)

        return {
            "trial": trial_label,
            "requested_delay_ms": delay_ms,
            "local_wait_ms": round(local_wait_ms, 2),
            "webdriver_send_ms": round(send_duration_ms, 2),
            "counter_value_at_detection": onset.get("value"),
            "foreperiod_wait_observed_ms": round(
                float(onset.get("waitElapsedMs") or 0.0),
                2,
            ),
            "feedback": feedback,
        }

    def _enter_practice(self, ctx) -> None:
        # run_battery has already clicked the outer CNB landing-page Continue.
        self._click_continue_if_present(ctx, "internal welcome", timeout=10)

        self._wait_for_text(ctx, "watch the red rectangle", timeout=20)
        self._press_space(ctx, "instructions1 -> instructions2")

        self._wait_for_text(ctx, "practice trial", timeout=20)
        self._press_space(ctx, "instructions2 -> begin practice")

        self._wait_for_text(ctx, "BEGIN PRACTICE", timeout=20)
        self._press_space(ctx, "BEGIN PRACTICE")

    def _run_practice(self, ctx) -> list[dict]:
        observations = []

        for trial_index in range(1, self.PRACTICE_TRIALS + 1):
            observations.append(
                self._respond_after_onset(
                    ctx,
                    delay_ms=self.PRACTICE_RT_MS,
                    trial_label=f"practice_{trial_index}",
                )
            )

        return observations

    def _enter_main_test(self, ctx) -> None:
        """
        Wait for the practice block to hand off to the BEGIN TEST screen.

        The PVT block can remain in its post-practice state longer than a
        normal instruction transition, so do not use the old 20-second
        instruction timeout here. The App.js uses duration=30000 for the
        PVT block, so allow enough time for that block-level timing to settle.
        """
        timeout = self.MAIN_TEST_TRANSITION_TIMEOUT_SECONDS
        deadline = time.time() + timeout

        ctx.logger.info(
            "PVT waiting up to %ds for BEGIN TEST after practice.",
            timeout,
        )

        while time.time() < deadline:
            body_text = ""
            try:
                body_text = ctx.driver.find_element(By.TAG_NAME, "body").text or ""
            except Exception:
                pass

            if "BEGIN TEST" in body_text.upper():
                ctx.logger.info("PVT BEGIN TEST screen detected.")
                self._press_space(ctx, "BEGIN TEST")
                return

            # If a numeric PVT counter unexpectedly appears again while we
            # believe practice is finished, surface that explicitly rather
            # than silently treating it as the main test.
            if self._counter_visible(ctx.driver):
                counter = None
                try:
                    counter = ctx.driver.find_element(
                        By.CSS_SELECTOR, self.COUNTER_SELECTOR
                    ).text
                except Exception:
                    pass

                raise RuntimeError(
                    "PVT counter reappeared while waiting for BEGIN TEST "
                    f"after {self.PRACTICE_TRIALS} practice trials "
                    f"(counter={counter!r})."
                )

            time.sleep(0.1)

        feedback = self._read_feedback(ctx)
        body_preview = ""
        try:
            body_preview = (
                ctx.driver.find_element(By.TAG_NAME, "body").text or ""
            ).strip().replace("\n", " | ")[:500]
        except Exception:
            pass

        raise TimeoutException(
            "PVT did not reach BEGIN TEST within "
            f"{timeout}s after practice. "
            f"feedback={feedback!r}; body={body_preview!r}"
        )

    def _delays_for_strategy(self, strategy: str) -> list[int]:
        strategy = (strategy or "perfect_300").strip().lower()

        if strategy == "mixed":
            return list(self.MIXED_DELAYS_MS)

        if strategy not in self.STRATEGY_DELAYS_MS:
            supported = sorted(list(self.STRATEGY_DELAYS_MS.keys()) + ["mixed"])
            raise ValueError(
                f"Unsupported PVT strategy {strategy!r}. "
                f"Supported strategies: {supported}"
            )

        return [
            self.STRATEGY_DELAYS_MS[strategy]
            for _ in range(self.TEST_TRIALS)
        ]

    def _run_main_test(self, ctx, strategy: str) -> list[dict]:
        delays = self._delays_for_strategy(strategy)

        if len(delays) != self.TEST_TRIALS:
            raise RuntimeError(
                f"PVT strategy {strategy!r} produced {len(delays)} responses; "
                f"expected {self.TEST_TRIALS}."
            )

        observations = []

        for trial_index, delay_ms in enumerate(delays, start=1):
            observations.append(
                self._respond_after_onset(
                    ctx,
                    delay_ms=delay_ms,
                    trial_label=f"test_{trial_index}",
                )
            )

        return observations

    def run(self, ctx, strategy: str = "perfect_300") -> TestRunResult:
        errors = []

        try:
            ctx.logger.info(
                "PVT starting test=%s strategy=%s",
                self.exact_code,
                strategy,
            )

            self._enter_practice(ctx)
            practice_observations = self._run_practice(ctx)

            ctx.logger.info(
                "PVT completed %d/%d practice trials.",
                len(practice_observations),
                self.PRACTICE_TRIALS,
            )

            self._enter_main_test(ctx)
            test_observations = self._run_main_test(ctx, strategy=strategy)

            ctx.logger.info(
                "PVT completed %d/%d scored trials.",
                len(test_observations),
                self.TEST_TRIALS,
            )

            ctx.pvt_observations = {
                "strategy": strategy,
                "practice": practice_observations,
                "test": test_observations,
            }

            if len(practice_observations) != self.PRACTICE_TRIALS:
                errors.append("PVT practice trial count mismatch.")

            if len(test_observations) != self.TEST_TRIALS:
                errors.append("PVT scored trial count mismatch.")

        except Exception as exc:
            ctx.logger.exception(
                "PVT plugin failed with strategy=%s",
                strategy,
            )
            errors.append(str(exc))

        if errors:
            return TestRunResult(status="FAIL", errors=errors)

        return TestRunResult(status="PASS", errors=[])
