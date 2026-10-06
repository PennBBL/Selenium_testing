from __future__ import annotations

import random
import time

from selenium.common.exceptions import (
    JavascriptException,
    NoSuchWindowException,
    StaleElementReferenceException,
    TimeoutException,
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
    Shared dynamic PVT 6.00 runner for:

        pvt-b-6.00-ff
            - instruction navigation uses the existing mixed SPACE/Continue flow
            - trial responses use SPACE

        pvt-b-btn-6.00-ff
            - all internal instruction pages use Click Here to Continue
            - trial responses click the .pvt-trial area

    The two versions share the same timing strategies, dynamic practice/main
    detection, false-start scenarios, no-input scenario, and abandonment
    scenarios.

    Important behavior:
    - Practice/scored trial counts are not hard-coded.
    - The red stimulus box may remain visible while empty between trials.
    - A trial onset is detected when numeric text appears inside .pvt-stimulus.
    - Practice ends when the BEGIN TEST screen appears.
    - Main test ends when CNB transitions away from the active PVT task.
    """

    exact_code = "pvt-b-6.00-ff"
    exact_codes = {
        "pvt-b-6.00-ff",
        "pvt-b-btn-6.00-ff",
    }

    VARIANTS = {
        "pvt-b-6.00-ff": {
            "response_mode": "space",
            "instruction_mode": "mixed",
        },
        "pvt-b-btn-6.00-ff": {
            "response_mode": "click",
            "instruction_mode": "continue",
        },
    }

    PRACTICE_RT_MS = 300

    STIMULUS_CONTAINER_SELECTOR = ".pvt-stimulus"
    TRIAL_CLICK_TARGET_SELECTOR = ".pvt-trial"
    FEEDBACK_SELECTOR = ".pvt-feedback"

    PHASE_EVENT_TIMEOUT_SECONDS = 35.0
    POLL_INTERVAL_SECONDS = 0.005
    END_CONTAINER_ABSENCE_SECONDS = 1.0

    # Safety caps only; these are not expected trial counts.
    MAX_PRACTICE_TRIALS = 50
    MAX_TEST_TRIALS = 200

    SUPPORTED_STRATEGIES = {
        "under_350",
        "first5_false_starts",
        "mid_355_500",
        "over_500",
        "random",
        "first5_then_stop",
        "practice_stop_after_7",
        "main_random_stop",
    }

    FALSE_START_DELAY_MS = 500
    NO_INPUT_CLEAR_SECONDS = 35.0

    PRACTICE_ABANDON_AFTER_RESPONSES = 7
    MAIN_RANDOM_STOP_MIN_RESPONSES = 3
    MAIN_RANDOM_STOP_MAX_RESPONSES = 10

    ABANDONMENT_TIMEOUT_SECONDS = 25 * 60
    ABANDONMENT_POLL_SECONDS = 0.5
    ABANDONMENT_PROGRESS_LOG_SECONDS = 60.0

    # ------------------------------------------------------------------
    # Variant helpers
    # ------------------------------------------------------------------

    def _active_test_code(self, ctx) -> str:
        code = str(
            getattr(ctx, "exact_code", None)
            or self.exact_code
        ).strip().lower()

        if code not in self.exact_codes:
            raise RuntimeError(
                f"Unsupported PVT 6 test code {code!r}. "
                f"Expected one of {sorted(self.exact_codes)}."
            )

        return code

    def _variant(self, ctx) -> dict:
        return self.VARIANTS[self._active_test_code(ctx)]

    def _response_mode(self, ctx) -> str:
        return str(self._variant(ctx)["response_mode"])

    def _instruction_mode(self, ctx) -> str:
        return str(self._variant(ctx)["instruction_mode"])

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    def _body_text(self, ctx) -> str:
        try:
            return ctx.driver.find_element(By.TAG_NAME, "body").text or ""
        except Exception:
            return ""

    def _wait_for_text(
        self,
        ctx,
        text: str,
        timeout: float = 20.0,
    ) -> None:
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
            ctx.driver.find_element(
                By.TAG_NAME,
                "body",
            ).send_keys(Keys.SPACE)

    def _click_trial(self, ctx, label: str) -> None:
        """
        Click the response target used by pvt-b-btn-6.00-ff.

        Confirmed active-trial HTML:
            <div class="pvt-trial" style="cursor: pointer; ...">

        Click the whole trial area rather than the changing numeric span.
        """
        ctx.logger.info("PVT clicking trial area: %s", label)

        trial = WebDriverWait(
            ctx.driver,
            5,
            poll_frequency=0.02,
        ).until(
            lambda d: self._visible_click_target(d)
        )

        try:
            trial.click()
        except Exception:
            ctx.driver.execute_script(
                "arguments[0].click();",
                trial,
            )

    def _visible_click_target(self, driver):
        elements = driver.find_elements(
            By.CSS_SELECTOR,
            self.TRIAL_CLICK_TARGET_SELECTOR,
        )

        for element in elements:
            try:
                if element.is_displayed() and element.is_enabled():
                    return element
            except Exception:
                continue

        return False

    def _send_trial_response(
        self,
        ctx,
        label: str,
    ) -> None:
        mode = self._response_mode(ctx)

        if mode == "space":
            self._press_space(ctx, label)
            return

        if mode == "click":
            self._click_trial(ctx, label)
            return

        raise RuntimeError(
            f"Unknown PVT response mode {mode!r}."
        )

    def _click_continue(
        self,
        ctx,
        label: str,
        timeout: float = 10.0,
    ) -> None:
        click_continue(
            ctx,
            label=label,
            timeout=timeout,
            delay=0.5,
        )

    def _click_continue_if_present(
        self,
        ctx,
        label: str,
        timeout: float = 6.0,
    ) -> bool:
        try:
            self._click_continue(
                ctx,
                label=f"PVT {label}",
                timeout=timeout,
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
        Read the current PVT state in one short JavaScript command.

        Numeric onset is based on text inside .pvt-stimulus itself rather than
        depending exclusively on the .four-digit-stimulus class.
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

        The empty red box is not a trial onset. A "counter" event is returned
        only when numeric text appears inside the stimulus container.
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
    # Participant-abandonment observation
    # ------------------------------------------------------------------

    def _wait_for_unattended_termination(
        self,
        ctx,
        *,
        scenario: str,
        phase: str,
        responses_before_stop: int,
        timeout: float | None = None,
    ) -> dict:
        """
        Simulate a participant who leaves and never returns.

        Once this method starts it sends NO keyboard or mouse input.
        """

        timeout = (
            float(timeout)
            if timeout is not None
            else float(self.ABANDONMENT_TIMEOUT_SECONDS)
        )

        started = time.perf_counter()
        next_progress_log = (
            started + self.ABANDONMENT_PROGRESS_LOG_SECONDS
        )
        last_state = {}

        ctx.logger.info(
            "PVT abandonment started: scenario=%s phase=%s "
            "responses_before_stop=%d timeout=%.0fs. "
            "No further keyboard or mouse input will be sent.",
            scenario,
            phase,
            responses_before_stop,
            timeout,
        )

        while (time.perf_counter() - started) < timeout:
            try:
                state = self._state_snapshot(ctx)
                last_state = state or {}

            except NoSuchWindowException:
                elapsed = time.perf_counter() - started

                ctx.logger.info(
                    "PVT unattended session ended after %.1fs: "
                    "browser window closed or navigated away.",
                    elapsed,
                )

                return {
                    "scenario": scenario,
                    "phase": phase,
                    "responses_before_stop": responses_before_stop,
                    "outcome": "self_terminated",
                    "reason": "browser_window_closed_or_navigated",
                    "unattended_wait_seconds": round(elapsed, 2),
                }

            except (
                JavascriptException,
                StaleElementReferenceException,
                WebDriverException,
            ):
                time.sleep(self.ABANDONMENT_POLL_SECONDS)
                continue

            if last_state.get("postTest"):
                elapsed = time.perf_counter() - started

                reason = (
                    "battery_complete"
                    if last_state.get("batteryComplete")
                    else "post_test_transition"
                )

                ctx.logger.info(
                    "PVT unattended session self-terminated after %.1fs: %s",
                    elapsed,
                    reason,
                )

                return {
                    "scenario": scenario,
                    "phase": phase,
                    "responses_before_stop": responses_before_stop,
                    "outcome": "self_terminated",
                    "reason": reason,
                    "unattended_wait_seconds": round(elapsed, 2),
                    "final_url": last_state.get("url"),
                }

            now = time.perf_counter()

            if now >= next_progress_log:
                elapsed = now - started

                ctx.logger.info(
                    "PVT abandonment still waiting after %.1f minutes: "
                    "scenario=%s phase=%s begin_test=%s "
                    "box_visible=%s numeric_value=%r url=%s",
                    elapsed / 60.0,
                    scenario,
                    phase,
                    bool(last_state.get("beginTest")),
                    bool(last_state.get("boxVisible")),
                    last_state.get("numericValue"),
                    last_state.get("url"),
                )

                next_progress_log = (
                    now + self.ABANDONMENT_PROGRESS_LOG_SECONDS
                )

            time.sleep(self.ABANDONMENT_POLL_SECONDS)

        elapsed = time.perf_counter() - started

        raise TimeoutException(
            "PVT abandonment scenario did not self-terminate within "
            f"{timeout / 60.0:.1f} minutes. "
            f"scenario={scenario!r}; phase={phase!r}; "
            f"responses_before_stop={responses_before_stop}; "
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
                f"PVT expected counter event for {trial_label}, "
                f"got {event!r}"
            )

        response_mode = self._response_mode(ctx)

        ctx.logger.info(
            "PVT counter detected for %s: value=%s "
            "box_text=%r wait_elapsed_ms=%.1f response_mode=%s",
            trial_label,
            event.get("value"),
            event.get("box_text", ""),
            float(event.get("waitElapsedMs") or 0.0),
            response_mode,
        )

        local_detection_time = time.perf_counter()

        self._wait_response_delay(delay_ms)

        before_send = time.perf_counter()

        self._send_trial_response(
            ctx,
            f"{trial_label} target={delay_ms}ms",
        )

        after_send = time.perf_counter()

        local_wait_ms = (
            before_send - local_detection_time
        ) * 1000.0

        send_duration_ms = (
            after_send - before_send
        ) * 1000.0

        time.sleep(0.05)
        feedback = self._read_feedback(ctx)

        ctx.logger.info(
            "PVT response %s: requested=%dms "
            "local_wait=%.1fms webdriver_send=%.1fms "
            "response_mode=%s feedback=%r",
            trial_label,
            delay_ms,
            local_wait_ms,
            send_duration_ms,
            response_mode,
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
            "response_mode": response_mode,
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

    def _enter_practice_space_variant(self, ctx) -> None:
        """
        Existing pvt-b-6.00-ff flow.

        run_battery has already clicked the outer landing-page Continue.

            general instructions -> SPACE
            practice instructions -> SPACE
            BEGIN PRACTICE -> Continue button
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

        self._click_continue(
            ctx,
            label="PVT 6.00 BEGIN PRACTICE",
            timeout=10,
        )

    def _enter_practice_click_variant(self, ctx) -> None:
        """
        pvt-b-btn-6.00-ff flow.

        The user confirmed all internal instructional pages use a
        "Click here to continue" button. Do not send SPACE on this variant.
        """

        self._wait_for_text(
            ctx,
            "watch the red rectangle",
            timeout=20,
        )

        self._click_continue(
            ctx,
            label="PVT BTN instructions1 -> instructions2",
            timeout=10,
        )

        self._wait_for_text(
            ctx,
            "We will first do a practice trial",
            timeout=20,
        )

        self._click_continue(
            ctx,
            label="PVT BTN instructions2 -> begin practice",
            timeout=10,
        )

        self._wait_for_text(
            ctx,
            "BEGIN PRACTICE",
            timeout=20,
        )

        self._click_continue(
            ctx,
            label="PVT BTN BEGIN PRACTICE",
            timeout=10,
        )

    def _enter_practice(self, ctx) -> None:
        mode = self._instruction_mode(ctx)

        if mode == "mixed":
            self._enter_practice_space_variant(ctx)

        elif mode == "continue":
            self._enter_practice_click_variant(ctx)

        else:
            raise RuntimeError(
                f"Unknown PVT instruction mode {mode!r}."
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

    def _run_practice_stop_after_7(
        self,
        ctx,
    ) -> tuple[list[dict], dict]:
        observations = []
        trial_index = 0
        target_responses = self.PRACTICE_ABANDON_AFTER_RESPONSES

        while trial_index < target_responses:
            event = self._wait_for_phase_event(
                ctx,
                phase="practice",
                allow_task_end=False,
            )

            if event.get("type") == "begin_test":
                raise RuntimeError(
                    "PVT practice ended before the abandonment scenario "
                    f"could reach {target_responses} responses; "
                    f"observed {trial_index}."
                )

            if event.get("type") != "counter":
                raise RuntimeError(
                    f"Unexpected PVT practice event: {event!r}"
                )

            trial_index += 1

            observation = self._respond_to_counter_event(
                ctx,
                event=event,
                delay_ms=self.PRACTICE_RT_MS,
                trial_label=f"practice_{trial_index}",
            )

            observation["action"] = "respond_before_abandonment"
            observation["strategy"] = "practice_stop_after_7"
            observations.append(observation)

        ctx.logger.info(
            "PVT practice abandonment point reached after %d responses.",
            trial_index,
        )

        abandonment = self._wait_for_unattended_termination(
            ctx,
            scenario="practice_stop_after_7",
            phase="practice",
            responses_before_stop=trial_index,
        )

        return observations, abandonment

    def _enter_main_test(self, ctx) -> None:
        """
        Both PVT 6 variants reach a BEGIN TEST instruction page.

        - regular pvt-b-6.00-ff: Continue button
        - pvt-b-btn-6.00-ff: Continue button

        Therefore no trial response helper is used here.
        """

        self._wait_for_text(
            ctx,
            "BEGIN TEST",
            timeout=10,
        )

        ctx.logger.info(
            "PVT BEGIN TEST screen detected for %s.",
            self._active_test_code(ctx),
        )

        self._click_continue(
            ctx,
            label="PVT 6.00 BEGIN TEST",
            timeout=10,
        )

        self._wait_for_stimulus_container(
            ctx,
            "main test start",
            timeout=15,
        )

    # ------------------------------------------------------------------
    # Dynamic main test / eight validation strategies
    # ------------------------------------------------------------------

    def _validate_strategy(self, strategy: str) -> str:
        strategy = (
            strategy or "under_350"
        ).strip().lower()

        if strategy not in self.SUPPORTED_STRATEGIES:
            raise ValueError(
                f"Unsupported PVT strategy {strategy!r}. "
                f"Supported strategies: "
                f"{sorted(self.SUPPORTED_STRATEGIES)}"
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
            return 300

        if strategy == "first5_then_stop":
            return 300

        raise ValueError(
            f"No response-delay rule for PVT strategy "
            f"{strategy!r}."
        )

    def _wait_for_feedback_cycle_after_false_start(
        self,
        ctx,
        *,
        trial_label: str,
        timeout: float = 4.0,
    ) -> str:
        started = time.perf_counter()
        seen_feedback = ""
        feedback_seen_at = None

        while (time.perf_counter() - started) < timeout:
            feedback = self._read_feedback(ctx)

            if feedback:
                if not seen_feedback:
                    seen_feedback = feedback
                    feedback_seen_at = time.perf_counter()

                if (
                    feedback_seen_at is not None
                    and time.perf_counter() - feedback_seen_at >= 0.15
                ):
                    pass

            elif seen_feedback:
                ctx.logger.info(
                    "PVT false-start feedback cycle completed for "
                    "%s: %r",
                    trial_label,
                    seen_feedback,
                )
                return seen_feedback

            time.sleep(0.02)

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
        Intentionally respond while the trial area is active but the numeric
        counter has not appeared.

        Regular variant sends SPACE.
        BTN variant clicks .pvt-trial.
        """

        response_mode = self._response_mode(ctx)

        ctx.logger.info(
            "PVT intentional false start for %s: waiting %dms "
            "while box is empty; response_mode=%s.",
            trial_label,
            self.FALSE_START_DELAY_MS,
            response_mode,
        )

        started = time.perf_counter()
        target_seconds = self.FALSE_START_DELAY_MS / 1000.0

        while (time.perf_counter() - started) < target_seconds:
            state = self._state_snapshot(ctx)

            numeric_value = state.get("numericValue")

            if numeric_value:
                ctx.logger.warning(
                    "PVT %s: number appeared before intentional "
                    "false-start response (value=%s); responding "
                    "normally instead.",
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

                observation["action"] = (
                    "fallback_normal_response"
                )
                return observation

            if not state.get("boxVisible"):
                raise RuntimeError(
                    "PVT stimulus box disappeared before intentional "
                    f"false start for {trial_label}."
                )

            time.sleep(0.01)

        self._send_trial_response(
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
            "PVT intentional false start completed for %s: "
            "response_mode=%s feedback=%r",
            trial_label,
            response_mode,
            feedback,
        )

        return {
            "trial": trial_label,
            "action": "false_start",
            "response_mode": response_mode,
            "requested_false_start_delay_ms": (
                self.FALSE_START_DELAY_MS
            ),
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
        Perform no participant response for this visible stimulus.

        This behavior is identical for keyboard and click variants.
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
                    "PVT no-input trial completed for %s after "
                    "%.1fms: feedback=%r",
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
                        (
                            time.perf_counter()
                            - started
                        ) * 1000.0,
                        2,
                    ),
                    "feedback": feedback,
                }

            time.sleep(0.02)

        raise RuntimeError(
            f"PVT no-input trial {trial_label} did not clear "
            f"within {self.NO_INPUT_CLEAR_SECONDS:.1f}s."
        )

    def _run_main_random_stop(
        self,
        ctx,
    ) -> tuple[list[dict], dict]:
        stop_after = random.randint(
            self.MAIN_RANDOM_STOP_MIN_RESPONSES,
            self.MAIN_RANDOM_STOP_MAX_RESPONSES,
        )

        ctx.logger.info(
            "PVT main_random_stop selected stop point: "
            "%d completed scored responses.",
            stop_after,
        )

        observations = []
        trial_index = 0

        while trial_index < stop_after:
            event = self._wait_for_phase_event(
                ctx,
                phase="main test",
                allow_task_end=True,
            )

            if event.get("type") == "task_end":
                raise RuntimeError(
                    "PVT main test ended before the random "
                    "abandonment point was reached. "
                    f"stop_after={stop_after}; "
                    f"observed={trial_index}; "
                    f"reason={event.get('reason')!r}"
                )

            if event.get("type") == "begin_test":
                raise RuntimeError(
                    "Unexpected BEGIN TEST screen while running "
                    "main_random_stop."
                )

            if event.get("type") != "counter":
                raise RuntimeError(
                    f"Unexpected PVT main-test event: {event!r}"
                )

            trial_index += 1
            trial_label = f"test_{trial_index}"

            observation = self._respond_to_counter_event(
                ctx,
                event=event,
                delay_ms=300,
                trial_label=trial_label,
            )

            observation["action"] = (
                "respond_before_abandonment"
            )
            observation["strategy"] = "main_random_stop"
            observations.append(observation)

        ctx.logger.info(
            "PVT main-test abandonment point reached after "
            "%d responses.",
            trial_index,
        )

        abandonment = self._wait_for_unattended_termination(
            ctx,
            scenario="main_random_stop",
            phase="main_test",
            responses_before_stop=trial_index,
        )

        abandonment["random_stop_after_responses"] = stop_after

        return observations, abandonment

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
                    "advancing via Continue and continuing."
                )

                self._click_continue(
                    ctx,
                    label="PVT unexpected BEGIN TEST during main test",
                    timeout=10,
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
                "PVT strategy=%s for %s: "
                "response_delay=%dms response_mode=%s",
                strategy,
                trial_label,
                delay_ms,
                self._response_mode(ctx),
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
            strategy = self._validate_strategy(strategy)
            test_code = self._active_test_code(ctx)
            variant = self._variant(ctx)

            ctx.logger.info(
                "PVT 6.00 starting test=%s strategy=%s "
                "response_mode=%s instruction_mode=%s",
                test_code,
                strategy,
                variant["response_mode"],
                variant["instruction_mode"],
            )

            self._enter_practice(ctx)

            if strategy == "practice_stop_after_7":
                (
                    practice_observations,
                    abandonment,
                ) = self._run_practice_stop_after_7(ctx)

                ctx.pvt_observations = {
                    "test_code": test_code,
                    "response_mode": variant["response_mode"],
                    "instruction_mode": variant["instruction_mode"],
                    "strategy": strategy,
                    "practice_count": len(practice_observations),
                    "test_count": 0,
                    "practice": practice_observations,
                    "test": [],
                    "abandonment": abandonment,
                }

                ctx.logger.info(
                    "PVT practice_stop_after_7 completed: %s",
                    abandonment,
                )

                return TestRunResult(
                    status="PASS",
                    errors=[],
                )

            practice_observations = self._run_practice(ctx)

            ctx.logger.info(
                "PVT 6.00 completed dynamic practice block: "
                "%d trials.",
                len(practice_observations),
            )

            self._enter_main_test(ctx)

            if strategy == "main_random_stop":
                (
                    test_observations,
                    abandonment,
                ) = self._run_main_random_stop(ctx)

                ctx.pvt_observations = {
                    "test_code": test_code,
                    "response_mode": variant["response_mode"],
                    "instruction_mode": variant["instruction_mode"],
                    "strategy": strategy,
                    "practice_count": len(practice_observations),
                    "test_count": len(test_observations),
                    "practice": practice_observations,
                    "test": test_observations,
                    "abandonment": abandonment,
                }

                ctx.logger.info(
                    "PVT main_random_stop completed: %s",
                    abandonment,
                )

                return TestRunResult(
                    status="PASS",
                    errors=[],
                )

            test_observations = self._run_main_test(
                ctx,
                strategy=strategy,
            )

            ctx.logger.info(
                "PVT 6.00 completed dynamic scored block: "
                "%d trials.",
                len(test_observations),
            )

            ctx.pvt_observations = {
                "test_code": test_code,
                "response_mode": variant["response_mode"],
                "instruction_mode": variant["instruction_mode"],
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
