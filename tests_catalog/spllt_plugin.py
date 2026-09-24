from __future__ import annotations

import inspect
import json
import re
import time
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from core.continue_utils import click_continue
from pages.test_landing_page import TestLandingPage
from tests_catalog.common import TestRunResult
from tests_catalog.spllt_scenarios import (
    SPLLT_BLOCK_COUNT,
    SPLLT_CONTROL_NEXT,
    SPLLT_SCENARIO_ORDER,
    expected_scenario_payload,
    scenario_sequence,
)
from workflows.launch_battery import launch_battery


class SPLLTPlugin:
    """
    Short Penn List Learning Test functional test suite.

    Important behavior:
    - One SPLLT administration runs one scenario.
    - The exact same response sequence is used in all 3 recall blocks.
    - Every time SPLLT is tested, this plugin runs every configured scenario.
    - Between scenarios, the SPLLT-only battery is relaunched to create a fresh
      administration/session.
    - Scenario-level expected interactions are written to JSON for later
      comparison with CNB results/scoring output.
    """

    exact_code = "spllt-a-1.00-ff"
    exact_codes = {"spllt-a-1.00-ff"}

    RESPONSE_SELECTOR = ".pllt-response-button"
    RECALL_WAIT_SECONDS = 30
    BETWEEN_CLICKS_SECONDS = 0.15
    END_OF_ADMINISTRATION_WAIT_SECONDS = 3.0

    def _normalize_label(self, value: str) -> str:
        value = str(value or "")
        value = value.replace("*", " ")
        value = re.sub(r"\s+", " ", value)
        return value.strip().upper()

    def _element_label(self, element) -> str:
        text = (element.text or "").strip()
        if text:
            return self._normalize_label(text)

        value = (element.get_attribute("value") or "").strip()
        return self._normalize_label(value)

    def _visible_response_buttons(self, ctx):
        buttons = []

        for element in ctx.driver.find_elements(By.CSS_SELECTOR, self.RESPONSE_SELECTOR):
            try:
                if element.is_displayed() and element.is_enabled():
                    buttons.append(element)
            except Exception:
                continue

        return buttons

    def _button_map(self, ctx) -> dict[str, object]:
        mapping = {}

        for button in self._visible_response_buttons(ctx):
            label = self._element_label(button)
            if label:
                mapping[label] = button

        return mapping

    def _wait_for_recall_block(self, ctx, timeout=None):
        timeout = timeout or self.RECALL_WAIT_SECONDS

        def ready(_driver):
            mapping = self._button_map(ctx)
            return mapping if SPLLT_CONTROL_NEXT in mapping else False

        return WebDriverWait(ctx.driver, timeout).until(ready)

    def _find_button(self, ctx, label: str, timeout=8):
        wanted = self._normalize_label(label)

        def find(_driver):
            return self._button_map(ctx).get(wanted) or False

        return WebDriverWait(ctx.driver, timeout).until(find)

    def _click_button(self, ctx, label: str) -> None:
        button = self._find_button(ctx, label)
        normalized = self._normalize_label(label)

        ctx.logger.info("SPLLT clicking response: %s", normalized)

        try:
            button.click()
        except Exception:
            ctx.driver.execute_script("arguments[0].click();", button)

        time.sleep(self.BETWEEN_CLICKS_SECONDS)

    def _next_trial_visible(self, ctx) -> bool:
        return SPLLT_CONTROL_NEXT in self._button_map(ctx)

    def _response_grid_visible(self, ctx) -> bool:
        try:
            return bool(self._visible_response_buttons(ctx))
        except Exception:
            return False

    def _read_visible_counter(self, ctx) -> int | None:
        """
        Best-effort counter read. The App.js defines a max-25 counter, but the
        exact cnbjs DOM is not known yet. If a numeric value is exposed next to
        'Total Responses Made', capture it; otherwise return None without failing.
        """
        try:
            body_text = ctx.driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            return None

        patterns = [
            r"Total\s+Responses\s+Made\s*:?\s*(\d+)",
            r"(\d+)\s*Total\s+Responses\s+Made",
        ]

        for pattern in patterns:
            match = re.search(pattern, body_text, flags=re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except Exception:
                    pass

        return None

    def _capture_layout(self, ctx) -> dict[str, dict[str, float]]:
        """Capture button centers for later quadrant/layout inspection."""
        layout = {}

        for label, button in self._button_map(ctx).items():
            try:
                rect = button.rect
                layout[label] = {
                    "x": float(rect.get("x", 0)),
                    "y": float(rect.get("y", 0)),
                    "width": float(rect.get("width", 0)),
                    "height": float(rect.get("height", 0)),
                    "center_x": float(rect.get("x", 0)) + float(rect.get("width", 0)) / 2,
                    "center_y": float(rect.get("y", 0)) + float(rect.get("height", 0)) / 2,
                }
            except Exception:
                continue

        return layout

    def _click_continue_to_recall(self, ctx, block_index: int) -> None:
        click_continue(
            ctx,
            label=f"SPLLT instructions before recall block {block_index + 1}",
            timeout=20,
            delay=0.5,
        )

        ctx.logger.info(
            "SPLLT waiting for 16-word presentation before recall block %d",
            block_index + 1,
        )
        self._wait_for_recall_block(ctx, timeout=self.RECALL_WAIT_SECONDS)

    def _run_recall_block(self, ctx, scenario_name: str, block_index: int) -> dict:
        sequence = scenario_sequence(scenario_name)

        self._click_continue_to_recall(ctx, block_index)

        layout = self._capture_layout(ctx)
        initial_counter = self._read_visible_counter(ctx)
        click_log = []

        for click_index, response in enumerate(sequence, start=1):
            before_counter = self._read_visible_counter(ctx)
            self._click_button(ctx, response)
            after_counter = self._read_visible_counter(ctx)

            click_log.append({
                "click_index": click_index,
                "response": response,
                "counter_before": before_counter,
                "counter_after": after_counter,
            })

        # max_25 may auto-advance depending on cnbjs implementation. For every
        # other scenario, MOVE TO NEXT TRIAL should still be present.
        moved_with_button = False

        if self._next_trial_visible(ctx):
            self._click_button(ctx, SPLLT_CONTROL_NEXT)
            moved_with_button = True
        else:
            ctx.logger.info(
                "SPLLT block %d no longer shows MOVE TO NEXT TRIAL; "
                "assuming the block auto-advanced.",
                block_index + 1,
            )

        return {
            "block_index": block_index,
            "scenario": scenario_name,
            "sequence": sequence,
            "total_requested_responses": len(sequence),
            "initial_counter": initial_counter,
            "click_log": click_log,
            "layout": layout,
            "advanced_with_next_trial_button": moved_with_button,
        }

    def _scenario_output_dir(self, ctx) -> Path:
        path = Path(ctx.output_dir) / "spllt_scenarios"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_scenario_result(self, ctx, scenario_name: str, payload: dict) -> Path:
        path = self._scenario_output_dir(ctx) / f"{scenario_name}.json"
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def _wait_for_administration_end(self, ctx) -> None:
        """
        Give the final recall block time to submit before starting a new battery
        session. We also wait for the response grid to disappear when possible.
        """
        deadline = time.time() + self.END_OF_ADMINISTRATION_WAIT_SECONDS

        while time.time() < deadline:
            if not self._response_grid_visible(ctx):
                break
            time.sleep(0.2)

        # Small additional grace period for destructor/submission/navigation.
        time.sleep(1.0)

    def _restart_for_next_scenario(self, ctx, next_scenario: str) -> None:
        ctx.logger.info(
            "SPLLT relaunching battery for next scenario: %s",
            next_scenario,
        )

        launch_battery(ctx)

        landing = TestLandingPage(ctx)
        exact_code = landing.get_exact_test_code()
        ctx.exact_code = exact_code

        if exact_code not in self.exact_codes:
            raise RuntimeError(
                f"SPLLT suite relaunched battery but found {exact_code!r}, "
                f"expected one of {sorted(self.exact_codes)}"
            )

        landing.click_continue()

    def _capture_failure(self, ctx, name: str, metadata: dict) -> None:
        """Support both artifact-manager signatures used by this project."""
        try:
            method = ctx.artifacts.capture_failure
            parameter_names = list(inspect.signature(method).parameters)

            # Older implementation: capture_failure(driver, name, metadata)
            if parameter_names and parameter_names[0] in {"driver", "browser"}:
                method(ctx.driver, name, metadata)
                return

            # Newer implementation stores the driver on the manager and uses
            # capture_failure(name, reason, metadata).
            reason = str(metadata.get("error") or "SPLLT scenario failure")
            method(name, reason, metadata)

        except Exception:
            ctx.logger.exception("SPLLT failure artifact capture failed")

    def _run_one_scenario(self, ctx, scenario_name: str) -> dict:
        expected = expected_scenario_payload(scenario_name)
        blocks = []

        for block_index in range(SPLLT_BLOCK_COUNT):
            ctx.logger.info(
                "SPLLT scenario=%s recall block=%d/%d",
                scenario_name,
                block_index + 1,
                SPLLT_BLOCK_COUNT,
            )

            block_result = self._run_recall_block(
                ctx,
                scenario_name=scenario_name,
                block_index=block_index,
            )
            blocks.append(block_result)

        self._wait_for_administration_end(ctx)

        return {
            **expected,
            "selenium_status": "PASS",
            "data_validation": "PENDING",
            "observed_interactions": blocks,
            "error": None,
        }

    def run(self, ctx, strategy="suite"):
        errors = []
        summary = []

        ctx.logger.info(
            "SPLLT functional suite starting with %d scenarios",
            len(SPLLT_SCENARIO_ORDER),
        )

        for scenario_index, scenario_name in enumerate(SPLLT_SCENARIO_ORDER):
            ctx.logger.info(
                "SPLLT scenario %d/%d: %s",
                scenario_index + 1,
                len(SPLLT_SCENARIO_ORDER),
                scenario_name,
            )

            try:
                payload = self._run_one_scenario(ctx, scenario_name)
                scenario_status = "PASS"

            except Exception as exc:
                error = f"SPLLT scenario {scenario_name} failed: {exc}"
                errors.append(error)
                scenario_status = "FAIL"

                ctx.logger.exception(error)
                self._capture_failure(
                    ctx,
                    f"spllt_{scenario_name}_failure",
                    {
                        "scenario": scenario_name,
                        "error": str(exc),
                    },
                )

                payload = {
                    **expected_scenario_payload(scenario_name),
                    "selenium_status": "FAIL",
                    "data_validation": "PENDING",
                    "observed_interactions": [],
                    "error": str(exc),
                }

                # Do not trust the current task state after a scenario failure.
                # The next scenario starts from a fresh battery launch below.
                time.sleep(1.0)

            output_path = self._write_scenario_result(
                ctx,
                scenario_name,
                payload,
            )

            summary.append({
                "scenario": scenario_name,
                "status": scenario_status,
                "output": str(output_path),
            })

            # Every scenario is a separate SPLLT administration. Since the
            # SPLLT battery contains no subsequent tasks, relaunch immediately
            # for the next scenario.
            if scenario_index < len(SPLLT_SCENARIO_ORDER) - 1:
                next_scenario = SPLLT_SCENARIO_ORDER[scenario_index + 1]

                try:
                    self._restart_for_next_scenario(ctx, next_scenario)
                except Exception as exc:
                    error = (
                        f"SPLLT could not relaunch battery before scenario "
                        f"{next_scenario}: {exc}"
                    )
                    errors.append(error)
                    ctx.logger.exception(error)
                    break

        summary_path = self._scenario_output_dir(ctx) / "suite_summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "test": self.exact_code,
                    "strategy": strategy,
                    "scenario_order": SPLLT_SCENARIO_ORDER,
                    "results": summary,
                    "errors": errors,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        if errors:
            return TestRunResult(status="FAIL", errors=errors)

        return TestRunResult(status="PASS", errors=[])
