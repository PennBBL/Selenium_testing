from __future__ import annotations

import random
import re
import time

from selenium.common.exceptions import (
    JavascriptException,
    NoSuchWindowException,
    StaleElementReferenceException,
    WebDriverException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from core.continue_utils import click_continue
from tests_catalog.common import TestRunResult


class PVT6Plugin:
    """
    Dynamic PVT runner for pvt-b-6.00-ff.

    Key behavior:
    - Does not hard-code practice or scored trial counts.
    - The red box may remain visible while empty between trials.
    - A response is sent as soon as ANY numeric text appears inside .pvt-stimulus.
      This intentionally does not depend on .four-digit-stimulus.
    - Practice ends when the BEGIN TEST screen appears.
    - Main test ends when the red stimulus box disappears and stays gone, or when
      CNB transitions to an obvious post-test page.
    - Uses short synchronous JavaScript state snapshots instead of a long
      execute_async_script call. This is more robust when the page navigates at
      the end of the task, including in headless Chrome.
    """

    exact_code = "pvt-b-6.00-ff"

    PRACTICE_RT_MS = 300

    STIMULUS_CONTAINER_SELECTOR = ".pvt-stimulus"
    FEEDBACK_SELECTOR = ".pvt-feedback"

    PHASE_EVENT_TIMEOUT_SECONDS = 35.0
    POLL_INTERVAL_SECONDS = 0.005
    END_CONTAINER_ABSENCE_SECONDS = 1.0

    # Safety caps only; these are not expected trial counts.
    MAX_PRACTICE_TRIALS = 50
    MAX_TEST_TRIALS = 200

    # Six intentionally simple validation strategies.
    #
    # under_350:
    #     Respond at 300 ms on every scored trial.
    #
    # first5_false_starts:
    #     For the first 5 scored opportunities, press SPACE before the number
    #     appears. After that, respond normally at 300 ms.
    #
    # mid_355_500:
    #     Respond at 425 ms on every scored trial.
    #
    # over_500:
    #     Respond at 750 ms on every scored trial.
    #
    # random:
    #     Random response latency between 150 and 1000 ms on every trial.
    #
    # first5_then_stop:
    #     Respond normally to the first 5 scored trials, then provide no more
    #     input and allow the remaining PVT trials to time out naturally.
    SUPPORTED_STRATEGIES = {
        "under_350",
        "first5_false_starts",
        "mid_355_500",
        "over_500",
        "random",
        "first5_then_stop",
    }

    FALSE_START_DELAY_MS = 500
    NO_INPUT_CLEAR_SECONDS = 35.0

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
    # PVT page-state detection
    # ------------------------------------------------------------------

    def _state_snapshot(self, ctx) -> dict:
        """
        Read the current PVT state in one short JS command.

        Numeric onset is based on the text inside .pvt-stimulus itself, not on
        a digit-count-specific class such as .four-digit-stimulus.
        """

        script = r"""
const selector = arguments[0];

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

const bodyText = ((document.body && document.body.innerText) || "");
const bodyUpper = bodyText.toUpperCase();

const box = document.querySelector(selector);
const boxVisible = visible(box);

let boxText = "";
if (box) {
    boxText = (
        box.innerText ||
        box.textContent ||
        ""
    ).trim();
}

// Find the first numeric text currently rendered inside the PVT stimulus box.
// Examples this catches: "1", "27", "305", "1004".
const numericMatch = boxText.match(/\d+/);
const numericValue = numericMatch ? numericMatch[0] : null;

const batteryComplete = bodyUpper.includes(
    "YOU HAVE COMPLETED THE TEST BATTERY"
);

const postTest = Boolean(
    batteryComplete ||
    document.querySelector("p.test-name") ||
    document.querySelector("a[href*='op=Quit']") ||
    document.querySelector("a img[src*='go.png']")
);

return {
    beginTest: bodyUpper.includes("BEGIN TEST"),
    batteryComplete: batteryComplete,
    boxPresent: Boolean(box),
    boxVisible: boxVisible,
    boxText: boxText,
    numericValue: numericValue,
    postTest: postTest,
    url: window.location.href
};
"""

        return ctx.driver.execute_script(
            script,
            self.STIMULUS_CONTAINER_SELECTOR,
        )

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

        deadline = time.perf_counter() + timeout

        while time.perf_counter() < deadline:
            try:
                state = self._state_snapshot(ctx)

                if state.get("boxVisible"):
                    return
            except (
                JavascriptException,
                StaleElementReferenceException,
                WebDriverException,
            ):
                pass

            time.sleep(0.02)

        raise RuntimeError(
            f"PVT stimulus container did not appear for {label} "
            f"within {timeout:.1f}s."
        )

    def _wait_for_phase_event(
        self,
        ctx,
        *,
        phase: str,
        allow_task_end: bool,
        timeout: float | None = None,
    ) -> dict:
        """
        Wait for:
          - numeric counter onset,
          - BEGIN TEST,
          - or main-test completion.

        The key detail is that the EMPTY red box is not a trial onset.
        We only return "counter" when numeric text appears inside the box.
        """

        timeout = timeout or self.PHASE_EVENT_TIMEOUT_SECONDS
        started = time.perf_counter()
        container_absent_since = None
        last_state = {}

        ctx.logger.info(
            "PVT waiting for next %s event (timeout=%ss).",
            phase,
            timeout,
        )

        while (time.perf_counter() - started) < timeout:
            try:
                state = self._state_snapshot(ctx)
                last_state = state or {}
            except NoSuchWindowException:
                if allow_task_end:
                    return {
                        "type": "task_end",
                        "reason": "browser_window_closed_or_navigated",
                        "waitElapsedMs": (
                            time.perf_counter() - started
                        ) * 1000.0,
                    }
                raise
            except (
                JavascriptException,
                StaleElementReferenceException,
                WebDriverException,
            ) as exc:
                # A page transition can briefly invalidate the old document.
                # Give the new page a moment to become queryable.
                if allow_task_end:
                    time.sleep(0.05)
                    try:
                        state = self._state_snapshot(ctx)
                        last_state = state or {}
                    except Exception:
                        time.sleep(0.05)
                        continue
                else:
                    raise RuntimeError(
                        f"PVT state read failed during {phase}: {exc}"
                    ) from exc

            if last_state.get("beginTest"):
                return {
                    "type": "begin_test",
                    "waitElapsedMs": (
                        time.perf_counter() - started
                    ) * 1000.0,
                }

            numeric_value = last_state.get("numericValue")

            if numeric_value:
                return {
                    "type": "counter",
                    "value": str(numeric_value),
                    "box_text": last_state.get("boxText", ""),
                    "waitElapsedMs": (
                        time.perf_counter() - started
                    ) * 1000.0,
                }

            if allow_task_end:
                if last_state.get("postTest"):
                    return {
                        "type": "task_end",
                        "reason": "post_test_page",
                        "waitElapsedMs": (
                            time.perf_counter() - started
                        ) * 1000.0,
                    }

                if last_state.get("boxVisible"):
                    container_absent_since = None
                else:
                    now = time.perf_counter()

                    if container_absent_since is None:
                        container_absent_since = now

                    elif (
                        now - container_absent_since
                        >= self.END_CONTAINER_ABSENCE_SECONDS
                    ):
                        return {
                            "type": "task_end",
                            "reason": "stimulus_container_gone",
                            "waitElapsedMs": (
                                time.perf_counter() - started
                            ) * 1000.0,
                            "url": last_state.get("url"),
                        }

            time.sleep(self.POLL_INTERVAL_SECONDS)

        feedback = self._read_feedback(ctx)

        raise RuntimeError(
            f"PVT timed out waiting for the next {phase} event "
            f"after {timeout:.1f}s. "
            f"feedback={feedback!r}; "
            f"last_state={last_state!r}"
        )

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
        deadline = time.perf_counter() + timeout

        while time.perf_counter() < deadline:
            try:
                state = self._state_snapshot(ctx)

                if not state.get("numericValue"):
                    return
            except Exception:
                # Navigation at the end of the task also means the old counter
                # is no longer active.
                return

            time.sleep(0.01)

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
            "box_text=%r wait_elapsed_ms=%.1f",
            trial_label,
            event.get("value"),
            event.get("box_text", ""),
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
            "box_text_at_detection": event.get("box_text", ""),
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
        """
        Enter the PVT 6.00 practice block.

        run_battery has already clicked the outer CNB landing-page Continue.

        Confirmed PVT 6.00 flow:
            general instructions -> SPACE
            practice instructions -> SPACE
            BEGIN PRACTICE -> click Continue
        """

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
            "We will first do a practice trial",
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

        click_continue(
            ctx,
            label="PVT 6.00 BEGIN PRACTICE",
            timeout=10,
            delay=0.5,
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

            if event.get("type") == "begin_test":
                ctx.logger.info(
                    "PVT practice complete after %d observed trials.",
                    trial_index,
                )
                return observations

            if event.get("type") != "counter":
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
        """
        Start the scored PVT 6.00 block.

        Practice terminates when the BEGIN TEST screen appears. Unlike PVT
        5.00, PVT 6.00 advances from BEGIN TEST by clicking the Continue
        button.
        """

        self._wait_for_text(
            ctx,
            "BEGIN TEST",
            timeout=10,
        )

        ctx.logger.info("PVT 6.00 BEGIN TEST screen detected.")

        click_continue(
            ctx,
            label="PVT 6.00 BEGIN TEST",
            timeout=10,
            delay=0.5,
        )

        self._wait_for_stimulus_container(
            ctx,
            "main test start",
            timeout=15,
        )

    # ------------------------------------------------------------------
    # Dynamic main test / six validation strategies
    # ------------------------------------------------------------------

    def _validate_strategy(self, strategy: str) -> str:
        strategy = (
            strategy or "under_350"
        ).strip().lower()

        if strategy not in self.SUPPORTED_STRATEGIES:
            raise ValueError(
                f"Unsupported PVT strategy {strategy!r}. "
                f"Supported strategies: {sorted(self.SUPPORTED_STRATEGIES)}"
            )

        return strategy

    def _response_delay_for_trial(
        self,
        strategy: str,
        trial_index: int,
    ) -> int:
        if strategy == "under_350":
            return 300

        if strategy == "mid_355_500":
            return 425

        if strategy == "over_500":
            return 750

        if strategy == "random":
            return random.randint(150, 1000)

        if strategy == "first5_false_starts":
            # After the first five false-start trials, use normal responses.
            return 300

        if strategy == "first5_then_stop":
            # The first five are normal responses.
            return 300

        raise ValueError(
            f"No response-delay rule for PVT strategy {strategy!r}."
        )

    def _wait_for_feedback_cycle_after_false_start(
        self,
        ctx,
        *,
        trial_label: str,
        timeout: float = 4.0,
    ) -> str:
        """
        Give CNB time to register the false start and move into the next
        foreperiod. We prefer observing feedback, but do not require it.
        """

        started = time.perf_counter()
        seen_feedback = ""
        feedback_seen_at = None

        while (time.perf_counter() - started) < timeout:
            feedback = self._read_feedback(ctx)

            if feedback:
                if not seen_feedback:
                    seen_feedback = feedback
                    feedback_seen_at = time.perf_counter()

                # Once feedback has been visible briefly, wait for it to clear.
                if (
                    feedback_seen_at is not None
                    and time.perf_counter() - feedback_seen_at >= 0.15
                ):
                    pass

            elif seen_feedback:
                ctx.logger.info(
                    "PVT false-start feedback cycle completed for %s: %r",
                    trial_label,
                    seen_feedback,
                )
                return seen_feedback

            time.sleep(0.02)

        # If the page does not expose a visible feedback cycle, use a
        # conservative delay. The observed PVT foreperiod is much longer than
        # this, so this still keeps the next intentional press before onset.
        if not seen_feedback:
            time.sleep(0.75)

        return seen_feedback

    def _perform_false_start_trial(
        self,
        ctx,
        *,
        trial_label: str,
    ) -> dict:
        """
        Intentionally press SPACE while the red box is still empty.

        The 500 ms pre-press wait continuously verifies that the numeric
        stimulus has not appeared. If onset occurs unexpectedly early, the
        method falls back to a normal 300 ms response instead of corrupting
        the requested false-start scenario.
        """

        ctx.logger.info(
            "PVT intentional false start for %s: waiting %dms "
            "while box is empty.",
            trial_label,
            self.FALSE_START_DELAY_MS,
        )

        started = time.perf_counter()
        target_seconds = self.FALSE_START_DELAY_MS / 1000.0

        while (time.perf_counter() - started) < target_seconds:
            state = self._state_snapshot(ctx)

            numeric_value = state.get("numericValue")

            if numeric_value:
                ctx.logger.warning(
                    "PVT %s: number appeared before intentional false-start "
                    "press (value=%s); responding normally instead.",
                    trial_label,
                    numeric_value,
                )

                event = {
                    "type": "counter",
                    "value": str(numeric_value),
                    "box_text": state.get("boxText", ""),
                    "waitElapsedMs": (
                        time.perf_counter() - started
                    ) * 1000.0,
                }

                observation = self._respond_to_counter_event(
                    ctx,
                    event=event,
                    delay_ms=300,
                    trial_label=trial_label,
                )
                observation["action"] = "fallback_normal_response"
                return observation

            if not state.get("boxVisible"):
                raise RuntimeError(
                    f"PVT stimulus box disappeared before intentional "
                    f"false start for {trial_label}."
                )

            time.sleep(0.01)

        self._press_space(
            ctx,
            f"{trial_label} intentional false start",
        )

        time.sleep(0.05)
        immediate_feedback = self._read_feedback(ctx)

        feedback = self._wait_for_feedback_cycle_after_false_start(
            ctx,
            trial_label=trial_label,
            timeout=4.0,
        ) or immediate_feedback

        ctx.logger.info(
            "PVT intentional false start completed for %s: feedback=%r",
            trial_label,
            feedback,
        )

        return {
            "trial": trial_label,
            "action": "false_start",
            "requested_false_start_delay_ms": self.FALSE_START_DELAY_MS,
            "feedback": feedback,
        }

    def _perform_no_input_trial(
        self,
        ctx,
        *,
        event: dict,
        trial_label: str,
    ) -> dict:
        """
        Do not press anything for this visible stimulus.

        Wait for CNB to clear the counter on its own. This is used after the
        first five normal responses in first5_then_stop.
        """

        ctx.logger.info(
            "PVT no-input mode for %s: onset_value=%s; "
            "waiting for CNB to advance without a response.",
            trial_label,
            event.get("value"),
        )

        started = time.perf_counter()
        last_value = event.get("value")

        while (
            time.perf_counter() - started
        ) < self.NO_INPUT_CLEAR_SECONDS:
            try:
                state = self._state_snapshot(ctx)
            except Exception:
                state = {}

            numeric_value = state.get("numericValue")

            if numeric_value:
                last_value = numeric_value
            else:
                feedback = self._read_feedback(ctx)

                ctx.logger.info(
                    "PVT no-input trial completed for %s after %.1fms: "
                    "feedback=%r",
                    trial_label,
                    (time.perf_counter() - started) * 1000.0,
                    feedback,
                )

                return {
                    "trial": trial_label,
                    "action": "no_input",
                    "counter_value_at_detection": event.get("value"),
                    "last_counter_value": last_value,
                    "waited_without_input_ms": round(
                        (time.perf_counter() - started) * 1000.0,
                        2,
                    ),
                    "feedback": feedback,
                }

            time.sleep(0.02)

        raise RuntimeError(
            f"PVT no-input trial {trial_label} did not clear within "
            f"{self.NO_INPUT_CLEAR_SECONDS:.1f}s."
        )

    def _run_main_test(
        self,
        ctx,
        strategy: str,
    ) -> list[dict]:
        strategy = self._validate_strategy(strategy)

        observations = []
        trial_index = 0

        while True:
            if trial_index >= self.MAX_TEST_TRIALS:
                raise RuntimeError(
                    "PVT exceeded main-test safety cap of "
                    f"{self.MAX_TEST_TRIALS} trials."
                )

            next_trial_index = trial_index + 1
            trial_label = f"test_{next_trial_index}"

            # Strategy 2: first five scored opportunities are intentional
            # false starts, before any numeric counter appears.
            if (
                strategy == "first5_false_starts"
                and next_trial_index <= 5
            ):
                observation = self._perform_false_start_trial(
                    ctx,
                    trial_label=trial_label,
                )

                trial_index += 1
                observations.append(observation)
                continue

            event = self._wait_for_phase_event(
                ctx,
                phase="main test",
                allow_task_end=True,
            )

            if event.get("type") == "task_end":
                ctx.logger.info(
                    "PVT main test complete after %d observed trials. "
                    "End reason=%s",
                    trial_index,
                    event.get("reason"),
                )
                return observations

            if event.get("type") == "begin_test":
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

            if event.get("type") != "counter":
                raise RuntimeError(
                    f"Unexpected PVT main-test event: {event!r}"
                )

            trial_index += 1
            trial_label = f"test_{trial_index}"

            # Strategy 6: respond to trials 1-5, then never send another key.
            if (
                strategy == "first5_then_stop"
                and trial_index > 5
            ):
                observation = self._perform_no_input_trial(
                    ctx,
                    event=event,
                    trial_label=trial_label,
                )
                observations.append(observation)
                continue

            delay_ms = self._response_delay_for_trial(
                strategy,
                trial_index,
            )

            ctx.logger.info(
                "PVT strategy=%s for %s: response_delay=%dms",
                strategy,
                trial_label,
                delay_ms,
            )

            observation = self._respond_to_counter_event(
                ctx,
                event=event,
                delay_ms=delay_ms,
                trial_label=trial_label,
            )
            observation["action"] = "respond"
            observation["strategy"] = strategy

            observations.append(observation)

    # ------------------------------------------------------------------
    # Public plugin API
    # ------------------------------------------------------------------

    def run(
        self,
        ctx,
        strategy: str = "under_350",
    ) -> TestRunResult:
        errors = []

        try:
            ctx.logger.info(
                "PVT 6.00 starting test=%s strategy=%s",
                self.exact_code,
                strategy,
            )

            self._enter_practice(ctx)

            practice_observations = self._run_practice(ctx)

            ctx.logger.info(
                "PVT 6.00 completed dynamic practice block: %d trials.",
                len(practice_observations),
            )

            self._enter_main_test(ctx)

            test_observations = self._run_main_test(
                ctx,
                strategy=strategy,
            )

            ctx.logger.info(
                "PVT 6.00 completed dynamic scored block: %d trials.",
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
