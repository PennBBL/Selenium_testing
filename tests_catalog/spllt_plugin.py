from __future__ import annotations

import inspect
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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
from scraping.spllt_scraper import get_datasetids_for_subid

try:
    from scraping.base_scraper import get_datasetid_for_subid
except Exception:
    get_datasetid_for_subid = None


class SPLLTPlugin:
    """
    Short Penn List Learning Test functional test suite.

    Design:
    - SPLLT is expected to be the only task in its battery.
    - One complete SPLLT administration runs one scenario.
    - The same scenario sequence is repeated in all 3 recall blocks.
    - Every SPLLT test run executes every configured scenario.
    - A fresh SPLLT battery is launched between scenarios.
    - Each scenario is exposed as its own completed-test record so the final
      completed_tests_summary.csv can show one row per scenario.
    - Each scenario record carries its own datasetid.
    """

    exact_code = "spllt-a-1.00-ff"
    exact_codes = {"spllt-a-1.00-ff"}

    RESPONSE_SELECTOR = ".pllt-response-button"
    RECALL_WAIT_SECONDS = 30
    BETWEEN_CLICKS_SECONDS = 0.15
    END_OF_ADMINISTRATION_WAIT_SECONDS = 3.0

    DATASET_LOOKUP_TIMEOUT_SECONDS = 40
    DATASET_LOOKUP_INTERVAL_SECONDS = 2

    # ------------------------------------------------------------------
    # Basic response-button helpers
    # ------------------------------------------------------------------

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

        for element in ctx.driver.find_elements(
            By.CSS_SELECTOR,
            self.RESPONSE_SELECTOR,
        ):
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

    # ------------------------------------------------------------------
    # Counter/layout observation
    # ------------------------------------------------------------------

    def _read_visible_counter(self, ctx) -> int | None:
        """
        Best-effort read of the visible response counter.

        The App.js defines a counter with max=25. The exact cnbjs DOM is not
        guaranteed, so failure to read the counter must not fail the scenario.
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
        """Capture response-button positions for quadrant/layout inspection."""
        layout = {}

        for label, button in self._button_map(ctx).items():
            try:
                rect = button.rect

                x = float(rect.get("x", 0))
                y = float(rect.get("y", 0))
                width = float(rect.get("width", 0))
                height = float(rect.get("height", 0))

                layout[label] = {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "center_x": x + width / 2,
                    "center_y": y + height / 2,
                }

            except Exception:
                continue

        return layout

    # ------------------------------------------------------------------
    # Recall-block execution
    # ------------------------------------------------------------------

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

        self._wait_for_recall_block(
            ctx,
            timeout=self.RECALL_WAIT_SECONDS,
        )

    def _run_recall_block(
        self,
        ctx,
        scenario_name: str,
        block_index: int,
    ) -> dict:
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

        moved_with_button = False

        # max_25 may auto-advance depending on cnbjs behavior.
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

    def _wait_for_administration_end(self, ctx) -> None:
        """
        Give the final recall block time to submit before looking up its
        dataset ID or launching the next SPLLT administration.
        """
        deadline = time.time() + self.END_OF_ADMINISTRATION_WAIT_SECONDS

        while time.time() < deadline:
            if not self._response_grid_visible(ctx):
                break
            time.sleep(0.2)

        time.sleep(1.0)

    # ------------------------------------------------------------------
    # Scenario JSON output
    # ------------------------------------------------------------------

    def _scenario_output_dir(self, ctx) -> Path:
        path = Path(ctx.output_dir) / "spllt_scenarios"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_scenario_result(
        self,
        ctx,
        scenario_name: str,
        payload: dict,
    ) -> Path:
        path = self._scenario_output_dir(ctx) / f"{scenario_name}.json"

        path.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        return path

    # ------------------------------------------------------------------
    # Dataset-ID helpers
    # ------------------------------------------------------------------

    def _datasetid_from_active_test_browser(self, ctx) -> str | None:
        """
        Best-effort attempt to get the dataset ID directly from the active
        assessment session before opening the separate results browser.

        This checks common URL parameters and hidden/form inputs. If the live
        assessment does not expose datasetid, the results-page lookup is used.
        """
        try:
            current_url = ctx.driver.current_url or ""
            query = parse_qs(urlparse(current_url).query)

            for key in (
                "datasetid",
                "dataset_id",
                "dataset",
            ):
                values = query.get(key) or []
                if values and str(values[0]).strip():
                    return str(values[0]).strip()

        except Exception:
            pass

        selectors = [
            "input[name='datasetid']",
            "input[name='dataset_id']",
            "input[id='datasetid']",
            "input[id='dataset_id']",
            "input[name*='dataset' i]",
            "input[id*='dataset' i]",
        ]

        for selector in selectors:
            try:
                elements = ctx.driver.find_elements(
                    By.CSS_SELECTOR,
                    selector,
                )
            except Exception:
                continue

            for element in elements:
                try:
                    value = (
                        element.get_attribute("value")
                        or element.get_attribute("data-value")
                        or ""
                    ).strip()

                    if value and re.fullmatch(r"\d+", value):
                        return value

                except Exception:
                    continue

        return None

    def _lookup_scenario_datasetid(
        self,
        ctx,
        seen_datasetids: set[str],
        active_datasetid: str | None = None,
    ) -> str | None:
        """
        Resolve the dataset ID for the administration that just completed.

        Priority:
        1. Dataset ID captured from the active test browser.
        2. Poll the results site until the latest dataset ID is not one that
           has already been assigned to an earlier scenario.
        """
        if active_datasetid:
            active_datasetid = str(active_datasetid).strip()

            if active_datasetid and active_datasetid not in seen_datasetids:
                ctx.logger.info(
                    "SPLLT dataset ID captured from active session: %s",
                    active_datasetid,
                )
                return active_datasetid

        if get_datasetid_for_subid is None:
            ctx.logger.warning(
                "SPLLT dataset lookup unavailable: "
                "get_datasetid_for_subid could not be imported."
            )
            return None

        deadline = time.time() + self.DATASET_LOOKUP_TIMEOUT_SECONDS
        last_datasetid = None

        while time.time() < deadline:
            try:
                datasetid = get_datasetid_for_subid(
                    subid=ctx.subid,
                )

                if datasetid:
                    datasetid = str(datasetid).strip()
                    last_datasetid = datasetid

                    if datasetid not in seen_datasetids:
                        ctx.logger.info(
                            "SPLLT scenario dataset ID found from results: %s",
                            datasetid,
                        )
                        return datasetid

                    ctx.logger.info(
                        "SPLLT results lookup still shows already-used "
                        "dataset ID %s; waiting for the new session.",
                        datasetid,
                    )

            except Exception as exc:
                ctx.logger.warning(
                    "SPLLT scenario dataset lookup attempt failed: %s",
                    exc,
                )

            time.sleep(self.DATASET_LOOKUP_INTERVAL_SECONDS)

        ctx.logger.warning(
            "SPLLT could not find a new dataset ID. Last dataset ID seen: %s",
            last_datasetid,
        )

        return None

    def _resolve_suite_datasetids(
        self,
        ctx,
        scenario_records: list[dict],
        summary: list[dict],
    ) -> None:
        """
        Resolve all SPLLT dataset IDs in one pass after the suite finishes.

        The generic single-dataset lookup always selected the same session for
        this repeated-subid workflow. Instead, query the complete session list,
        take the newest N dataset IDs, and map them to the administered SPLLT
        scenarios in execution order.
        """
        administered = [
            record
            for record in scenario_records
            if record.get("scrape", True)
        ]

        if not administered:
            return

        try:
            all_datasetids = get_datasetids_for_subid(ctx.subid)
        except Exception as exc:
            ctx.logger.exception(
                "SPLLT could not enumerate dataset IDs for subid %s: %s",
                ctx.subid,
                exc,
            )
            return

        ctx.logger.info(
            "SPLLT session lookup found dataset IDs for %s: %s",
            ctx.subid,
            all_datasetids,
        )

        needed = len(administered)

        if len(all_datasetids) < needed:
            ctx.logger.warning(
                "SPLLT expected at least %d dataset IDs for %d administered "
                "scenarios, but session lookup found only %d. Dataset IDs "
                "will remain blank rather than being guessed.",
                needed,
                needed,
                len(all_datasetids),
            )
            return

        selected = all_datasetids[-needed:]

        ctx.logger.info(
            "SPLLT mapping newest %d dataset IDs to scenario order: %s",
            needed,
            selected,
        )

        by_strategy = {}

        for record, datasetid in zip(administered, selected):
            datasetid = str(datasetid)
            record["datasetid"] = datasetid
            by_strategy[record.get("strategy")] = datasetid

        for item in summary:
            strategy = item.get("scenario")
            if strategy in by_strategy:
                item["datasetid"] = by_strategy[strategy]

                output = item.get("output")
                if output:
                    try:
                        path = Path(output)
                        payload = json.loads(path.read_text(encoding="utf-8"))
                        payload["datasetid"] = by_strategy[strategy]
                        path.write_text(
                            json.dumps(
                                payload,
                                indent=2,
                                ensure_ascii=False,
                            ),
                            encoding="utf-8",
                        )
                    except Exception as exc:
                        ctx.logger.warning(
                            "Could not update SPLLT scenario JSON for %s: %s",
                            strategy,
                            exc,
                        )

    # ------------------------------------------------------------------
    # Battery restart / artifacts
    # ------------------------------------------------------------------

    def _restart_for_next_scenario(
        self,
        ctx,
        next_scenario: str,
    ) -> None:
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
                "SPLLT suite relaunched battery but found "
                f"{exact_code!r}, expected one of "
                f"{sorted(self.exact_codes)}"
            )

        landing.click_continue()

    def _capture_failure(
        self,
        ctx,
        name: str,
        metadata: dict,
    ) -> None:
        """Support both artifact-manager signatures used by this project."""
        try:
            method = ctx.artifacts.capture_failure
            parameter_names = list(
                inspect.signature(method).parameters
            )

            # Older implementation:
            # capture_failure(driver, name, metadata)
            if parameter_names and parameter_names[0] in {
                "driver",
                "browser",
            }:
                method(
                    ctx.driver,
                    name,
                    metadata,
                )
                return

            # Newer implementation:
            # capture_failure(name, reason, metadata)
            reason = str(
                metadata.get("error")
                or "SPLLT scenario failure"
            )

            method(
                name,
                reason,
                metadata,
            )

        except Exception:
            ctx.logger.exception(
                "SPLLT failure artifact capture failed"
            )

    # ------------------------------------------------------------------
    # One complete SPLLT administration
    # ------------------------------------------------------------------

    def _run_one_scenario(
        self,
        ctx,
        scenario_name: str,
    ) -> dict:
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

    # ------------------------------------------------------------------
    # Full SPLLT suite
    # ------------------------------------------------------------------

    def run(self, ctx, strategy="suite"):
        """
        Run every SPLLT scenario.

        The registry strategy remains "suite" internally, but reporting uses
        one row per scenario. Dataset IDs are resolved in one batch after all
        scenario administrations finish.
        """
        suite_errors = []
        summary = []
        scenario_records = []

        ctx.logger.info(
            "SPLLT functional suite starting with %d scenarios",
            len(SPLLT_SCENARIO_ORDER),
        )

        for scenario_index, scenario_name in enumerate(
            SPLLT_SCENARIO_ORDER
        ):
            ctx.logger.info(
                "SPLLT scenario %d/%d: %s",
                scenario_index + 1,
                len(SPLLT_SCENARIO_ORDER),
                scenario_name,
            )

            scenario_error = None

            try:
                payload = self._run_one_scenario(
                    ctx,
                    scenario_name,
                )
                scenario_status = "PASS"

            except Exception as exc:
                scenario_error = str(exc)
                scenario_status = "FAIL"

                error = (
                    f"SPLLT scenario {scenario_name} failed: "
                    f"{scenario_error}"
                )

                suite_errors.append(error)
                ctx.logger.exception(error)

                self._capture_failure(
                    ctx,
                    f"spllt_{scenario_name}_failure",
                    {
                        "scenario": scenario_name,
                        "error": scenario_error,
                    },
                )

                payload = {
                    **expected_scenario_payload(scenario_name),
                    "selenium_status": "FAIL",
                    "data_validation": "PENDING",
                    "observed_interactions": [],
                    "error": scenario_error,
                }

                time.sleep(1.0)

            # Dataset IDs are intentionally resolved after the entire suite.
            # The generic one-session lookup cannot distinguish repeated SPLLT
            # administrations that share the same subid.
            payload["datasetid"] = None

            output_path = self._write_scenario_result(
                ctx,
                scenario_name,
                payload,
            )

            reason = (
                "Completed successfully."
                if scenario_status == "PASS"
                else f"Scenario failed: {scenario_error}"
            )

            record = {
                "test_name": self.exact_code,
                "status": scenario_status,
                "reason": reason,
                "errors": (
                    []
                    if scenario_status == "PASS"
                    else [scenario_error]
                ),
                "scrape": True,
                "strategy": scenario_name,
                "datasetid": None,
            }

            scenario_records.append(record)

            summary.append({
                "scenario": scenario_name,
                "status": scenario_status,
                "datasetid": None,
                "output": str(output_path),
            })

            if scenario_index < len(SPLLT_SCENARIO_ORDER) - 1:
                next_scenario = SPLLT_SCENARIO_ORDER[
                    scenario_index + 1
                ]

                try:
                    self._restart_for_next_scenario(
                        ctx,
                        next_scenario,
                    )

                except Exception as exc:
                    fatal_error = (
                        "SPLLT could not relaunch battery before "
                        f"scenario {next_scenario}: {exc}"
                    )

                    suite_errors.append(fatal_error)
                    ctx.logger.exception(fatal_error)

                    remaining = SPLLT_SCENARIO_ORDER[
                        scenario_index + 1:
                    ]

                    for missing_scenario in remaining:
                        missing_reason = (
                            "Not run because SPLLT battery relaunch failed "
                            f"before {next_scenario}."
                        )

                        scenario_records.append({
                            "test_name": self.exact_code,
                            "status": "FAIL",
                            "reason": missing_reason,
                            "errors": [fatal_error],
                            "scrape": False,
                            "strategy": missing_scenario,
                            "datasetid": None,
                        })

                        summary.append({
                            "scenario": missing_scenario,
                            "status": "FAIL",
                            "datasetid": None,
                            "output": None,
                            "reason": missing_reason,
                        })

                    break

        # Resolve all dataset IDs together from the subject's session list.
        self._resolve_suite_datasetids(
            ctx,
            scenario_records,
            summary,
        )

        ctx.spllt_scenario_records = scenario_records
        ctx.spllt_suite_errors = suite_errors

        summary_path = (
            self._scenario_output_dir(ctx)
            / "suite_summary.json"
        )

        summary_path.write_text(
            json.dumps(
                {
                    "test": self.exact_code,
                    "internal_strategy": strategy,
                    "scenario_order": SPLLT_SCENARIO_ORDER,
                    "results": summary,
                    "errors": suite_errors,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        return TestRunResult(
            status="PASS",
            errors=[],
        )

