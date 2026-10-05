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
    """
    Dynamic PVT runner for pvt-b-5.00-ff.

    Important behavior:
    - The red PVT box can remain visible while empty between trials.
    - A response is sent only when .four-digit-stimulus appears.
    - Practice trial count is discovered dynamically.
    - Main-test trial count is discovered dynamically.
    - Practice ends when the BEGIN TEST screen appears.
    - Main test ends when the PVT stimulus container disappears and stays gone,
      or when the CNB page transitions to an obvious post-test page.
    """

    exact_code = "pvt-b-5.00-ff"

    PRACTICE_RT_MS = 300

    STIMULUS_CONTAINER_SELECTOR = ".pvt-stimulus"
    COUNTER_SELECTOR = ".pvt-stimulus .four-digit-stimulus"
    FEEDBACK_SELECTOR = ".pvt-feedback"

    # Every PVT trial can run up to about 30 seconds, so give the state watcher
    # a little extra room before declaring that the task is stuck.
    PHASE_EVENT_TIMEOUT_SECONDS = 35

    # Safety caps only. These are NOT expected trial counts.
    MAX_PRACTICE_TRIALS = 50
    MAX_TEST_TRIALS = 200

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

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    def _body_text(self, ctx) -> str:
        try:
            return ctx.driver.find_element(By.TAG_NAME, "body").text or ""
        except Exception:
            return ""

    def _wait_for_text(self, ctx, text: str, timeout: float = 20.0) -> None:
        wanted = text.lower()

        WebDriverWait(
            ctx.driver,
            timeout,
            poll_frequency=0.1,
        ).until(
            lambda d: wanted in (
                d.find_element(By.TAG_NAME, "body").text or ""
            ).lower()
        )

    def _press_space(self, ctx, label: str) -> None:
        ctx.logger.info("PVT pressing SPACE: %s", label)

        try:
            ActionChains(ctx.driver).send_keys(Keys.SPACE).perform()
        except Exception:
            ctx.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.SPACE)

    def _click_continue_if_present(
        self,
        ctx,
        label: str,
        timeout: float = 6.0,
    ) -> bool:
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
        for element in driver.find_elements(
            By.CSS_SELECTOR,
            self.COUNTER_SELECTOR,
        ):
            try:
                text = (element.text or "").strip()

                if (
                    element.is_displayed()
                    and text
                    and text.isdigit()
                ):
                    return True
            except Exception:
                continue

        return False

    def _stimulus_container_visible(self, driver) -> bool:
        for element in driver.find_elements(
            By.CSS_SELECTOR,
            self.STIMULUS_CONTAINER_SELECTOR,
        ):
            try:
                if element.is_displayed():
                    return True
            except Exception:
                continue

        return False

    def _wait_for_stimulus_container(
        self,
        ctx,
        label: str,
        timeout: float = 15.0,
    ) -> None:
        ctx.logger.info(
            "PVT waiting for stimulus container: %s",
            label,
        )

        WebDriverWait(
            ctx.driver,
            timeout,
            poll_frequency=0.05,
        ).until(
            lambda d: self._stimulus_container_visible(d)
        )

    def _read_feedback(self, ctx) -> str:
        try:
            element = ctx.driver.find_element(
                By.CSS_SELECTOR,
                self.FEEDBACK_SELECTOR,
            )
            return (element.text or "").strip()
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Browser-side state watcher
    # ------------------------------------------------------------------

    def _wait_for_phase_event(
        self,
        ctx,
        *,
        phase: str,
        allow_task_end: bool,
        timeout: float | None = None,
    ) -> dict:
        """
        Wait inside the browser for the next meaningful PVT state.

        Possible event types:
            counter
            begin_test
            task_end
            timeout

        This is intentionally NOT based on "counter missing", because the
        counter is supposed to be missing during the random empty-box period.
        """

        timeout = timeout or self.PHASE_EVENT_TIMEOUT_SECONDS

        script = r"""
const callback = arguments[arguments.length - 1];

const counterSelector = arguments[0];
const containerSelector = arguments[1];
const allowTaskEnd = arguments[2];
const timeoutMs = arguments[3];

const started = performance.now();
let containerAbsentSince = null;

function visible(el) {
    if (!el) return false;

    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();

    return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        Number(style.opacity || 1) > 0 &&
        rect.width > 0 &&
        rect.height > 0
    );
}

function bodyTextUpper() {
    return ((document.body && document.body.innerText) || "").toUpperCase();
}

function looksLikePostTestPage() {
    return Boolean(
        document.querySelector("p.test-name") ||
        document.querySelector("a[href*='op=Quit']") ||
        document.querySelector("a img[src*='go.png']")
    );
}

function tick() {
    const now = performance.now();
    const bodyText = bodyTextUpper();

    // Practice is over when the explicit BEGIN TEST screen appears.
    if (bodyText.includes("BEGIN TEST")) {
        callback({
            type: "begin_test",
            waitElapsedMs: now - started
        });
        return;
    }

    // Counter onset is the actual response trigger.
    const counter = document.querySelector(counterSelector);

    if (visible(counter)) {
        const value = (counter.textContent || "").trim();

        if (/^\d+$/.test(value)) {
            callback({
                type: "counter",
                value: value,
                detectedAtPerformanceMs: now,
                waitElapsedMs: now - started
            });
            return;
        }
    }

    if (allowTaskEnd) {
        const container = document.querySelector(containerSelector);

        if (looksLikePostTestPage()) {
            callback({
                type: "task_end",
                reason: "post_test_page",
                waitElapsedMs: now - started
            });
            return;
        }

        if (visible(container)) {
            containerAbsentSince = null;
        } else {
            if (containerAbsentSince === null) {
                containerAbsentSince = now;
            }

            // Require the red-box container to stay gone for a full second.
            // This avoids mistaking a brief React re-render for test completion.
            if (now - containerAbsentSince >= 1000) {
                callback({
                    type: "task_end",
                    reason: "stimulus_container_gone",
                    waitElapsedMs: now - started
                });
                return;
            }
        }
    }

    if (now - started >= timeoutMs) {
        callback({
            type: "timeout",
            waitElapsedMs: now - started,
            bodyPreview: bodyText.slice(0, 500)
        });
        return;
    }

    requestAnimationFrame(tick);
}

tick();
"""

        ctx.logger.info(
            "PVT waiting for next %s event (timeout=%ss).",
            phase,
            timeout,
        )

        try:
            ctx.driver.set_script_timeout(timeout + 2.0)

            result = ctx.driver.execute_async_script(
                script,
                self.COUNTER_SELECTOR,
                self.STIMULUS_CONTAINER_SELECTOR,
                bool(allow_task_end),
                int(timeout * 1000),
            )
        except Exception as exc:
            raise RuntimeError(
                f"PVT state detection failed during {phase}: {exc}"
            ) from exc

        if not result:
            raise RuntimeError(
                f"PVT state detector returned no result during {phase}."
            )

        if result.get("type") == "timeout":
            feedback = self._read_feedback(ctx)

            raise TimeoutException(
                f"PVT timed out waiting for the next {phase} event "
                f"after {timeout:.1f}s. "
                f"feedback={feedback!r}; "
                f"body={result.get('bodyPreview', '')!r}"
            )

        return result

    # ------------------------------------------------------------------
    # Response timing
    # ------------------------------------------------------------------

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

    def _wait_for_counter_clear(
        self,
        ctx,
        trial_label: str,
        timeout: float = 5.0,
    ) -> None:
        try:
            WebDriverWait(
                ctx.driver,
                timeout,
                poll_frequency=0.02,
            ).until(
                lambda d: not self._counter_visible(d)
            )
        except Exception:
            ctx.logger.warning(
                "PVT counter did not clearly disappear after %s.",
                trial_label,
            )

    def _respond_to_counter_event(
        self,
        ctx,
        *,
        event: dict,
        delay_ms: int,
        trial_label: str,
    ) -> dict:
        if event.get("type") != "counter":
            raise RuntimeError(
                f"PVT expected counter event for {trial_label}, got {event!r}"
            )

        ctx.logger.info(
            "PVT counter detected for %s: value=%s "
            "wait_elapsed_ms=%.1f",
            trial_label,
            event.get("value"),
            float(event.get("waitElapsedMs") or 0.0),
        )

        local_detection_time = time.perf_counter()

        self._wait_response_delay(delay_ms)

        before_press = time.perf_counter()

        self._press_space(
            ctx,
            f"{trial_label} target={delay_ms}ms",
        )

        after_press = time.perf_counter()

        local_wait_ms = (
            before_press - local_detection_time
        ) * 1000.0

        send_duration_ms = (
            after_press - before_press
        ) * 1000.0

        time.sleep(0.05)
        feedback = self._read_feedback(ctx)

        ctx.logger.info(
            "PVT response %s: requested=%dms "
            "local_wait=%.1fms webdriver_send=%.1fms "
            "feedback=%r",
            trial_label,
            delay_ms,
            local_wait_ms,
            send_duration_ms,
            feedback,
        )

        self._wait_for_counter_clear(
            ctx,
            trial_label,
            timeout=5.0,
        )

        return {
            "trial": trial_label,
            "requested_delay_ms": delay_ms,
            "local_wait_ms": round(local_wait_ms, 2),
            "webdriver_send_ms": round(send_duration_ms, 2),
            "counter_value_at_detection": event.get("value"),
            "wait_elapsed_ms": round(
                float(event.get("waitElapsedMs") or 0.0),
                2,
            ),
            "feedback": feedback,
        }

    # ------------------------------------------------------------------
    # Instructions
    # ------------------------------------------------------------------

    def _enter_practice(self, ctx) -> None:
        # run_battery has already handled the outer CNB landing page,
        # or direct-loaded the PVT React app.
        self._click_continue_if_present(
            ctx,
            "internal welcome",
            timeout=10,
        )

        self._wait_for_text(
            ctx,
            "watch the red rectangle",
            timeout=20,
        )
        self._press_space(
            ctx,
            "instructions1 -> instructions2",
        )

        self._wait_for_text(
            ctx,
            "practice trial",
            timeout=20,
        )
        self._press_space(
            ctx,
            "instructions2 -> begin practice",
        )

        self._wait_for_text(
            ctx,
            "BEGIN PRACTICE",
            timeout=20,
        )
        self._press_space(
            ctx,
            "BEGIN PRACTICE",
        )

        self._wait_for_stimulus_container(
            ctx,
            "practice start",
            timeout=15,
        )

    # ------------------------------------------------------------------
    # Dynamic practice block
    # ------------------------------------------------------------------

    def _run_practice(self, ctx) -> list[dict]:
        observations = []
        trial_index = 0

        while True:
            if trial_index >= self.MAX_PRACTICE_TRIALS:
                raise RuntimeError(
                    "PVT exceeded practice safety cap of "
                    f"{self.MAX_PRACTICE_TRIALS} trials."
                )

            event = self._wait_for_phase_event(
                ctx,
                phase="practice",
                allow_task_end=False,
            )

            event_type = event.get("type")

            if event_type == "begin_test":
                ctx.logger.info(
                    "PVT practice complete after %d observed trials.",
                    trial_index,
                )
                return observations

            if event_type != "counter":
                raise RuntimeError(
                    f"Unexpected PVT practice event: {event!r}"
                )

            trial_index += 1

            observations.append(
                self._respond_to_counter_event(
                    ctx,
                    event=event,
                    delay_ms=self.PRACTICE_RT_MS,
                    trial_label=f"practice_{trial_index}",
                )
            )

    def _enter_main_test(self, ctx) -> None:
        # _run_practice() returns only after detecting BEGIN TEST.
        ctx.logger.info("PVT BEGIN TEST screen detected.")
        self._press_space(ctx, "BEGIN TEST")

        self._wait_for_stimulus_container(
            ctx,
            "main test start",
            timeout=15,
        )

    # ------------------------------------------------------------------
    # Dynamic main test
    # ------------------------------------------------------------------

    def _delay_for_trial(
        self,
        strategy: str,
        trial_index: int,
    ) -> int:
        strategy = (
            strategy or "perfect_300"
        ).strip().lower()

        if strategy == "mixed":
            return self.MIXED_DELAYS_MS[
                (trial_index - 1) % len(self.MIXED_DELAYS_MS)
            ]

        if strategy not in self.STRATEGY_DELAYS_MS:
            supported = sorted(
                list(self.STRATEGY_DELAYS_MS.keys())
                + ["mixed"]
            )

            raise ValueError(
                f"Unsupported PVT strategy {strategy!r}. "
                f"Supported strategies: {supported}"
            )

        return self.STRATEGY_DELAYS_MS[strategy]

    def _run_main_test(
        self,
        ctx,
        strategy: str,
    ) -> list[dict]:
        observations = []
        trial_index = 0

        while True:
            if trial_index >= self.MAX_TEST_TRIALS:
                raise RuntimeError(
                    "PVT exceeded main-test safety cap of "
                    f"{self.MAX_TEST_TRIALS} trials."
                )

            event = self._wait_for_phase_event(
                ctx,
                phase="main test",
                allow_task_end=True,
            )

            event_type = event.get("type")

            if event_type == "task_end":
                ctx.logger.info(
                    "PVT main test complete after %d observed trials. "
                    "End reason=%s",
                    trial_index,
                    event.get("reason"),
                )
                return observations

            if event_type == "begin_test":
                # Defensive only. BEGIN TEST should have been consumed already.
                ctx.logger.warning(
                    "PVT BEGIN TEST appeared again during main test; "
                    "pressing SPACE and continuing."
                )
                self._press_space(
                    ctx,
                    "unexpected BEGIN TEST during main test",
                )
                self._wait_for_stimulus_container(
                    ctx,
                    "main test restart",
                    timeout=15,
                )
                continue

            if event_type != "counter":
                raise RuntimeError(
                    f"Unexpected PVT main-test event: {event!r}"
                )

            trial_index += 1

            delay_ms = self._delay_for_trial(
                strategy,
                trial_index,
            )

            observations.append(
                self._respond_to_counter_event(
                    ctx,
                    event=event,
                    delay_ms=delay_ms,
                    trial_label=f"test_{trial_index}",
                )
            )

    # ------------------------------------------------------------------
    # Public plugin API
    # ------------------------------------------------------------------

    def run(
        self,
        ctx,
        strategy: str = "perfect_300",
    ) -> TestRunResult:
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
                "PVT completed dynamic practice block: %d trials.",
                len(practice_observations),
            )

            self._enter_main_test(ctx)

            test_observations = self._run_main_test(
                ctx,
                strategy=strategy,
            )

            ctx.logger.info(
                "PVT completed dynamic scored block: %d trials.",
                len(test_observations),
            )

            ctx.pvt_observations = {
                "strategy": strategy,
                "practice_count": len(practice_observations),
                "test_count": len(test_observations),
                "practice": practice_observations,
                "test": test_observations,
            }

        except Exception as exc:
            ctx.logger.exception(
                "PVT plugin failed with strategy=%s",
                strategy,
            )
            errors.append(str(exc))

        if errors:
            return TestRunResult(
                status="FAIL",
                errors=errors,
            )

        return TestRunResult(
            status="PASS",
            errors=[],
        )
