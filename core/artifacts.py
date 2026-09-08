from __future__ import annotations

import json
import time
from pathlib import Path


class ArtifactManager:
    """
    Saves screenshots, HTML, and optional metadata for failures.

    Compatible with both calling styles used in the project:

    1. capture_failure(test_code, reason)
    2. capture_failure(driver, label, metadata)
    """

    def __init__(self, driver, output_dir):
        self.driver = driver
        self.output_dir = Path(output_dir)
        self.artifact_dir = self.output_dir / "artifacts"
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def _safe_name(self, value):
        value = str(value or "artifact")
        safe = []
        for ch in value:
            if ch.isalnum() or ch in {"-", "_", "."}:
                safe.append(ch)
            else:
                safe.append("_")
        return "".join(safe).strip("_") or "artifact"

    def capture_failure(self, *args, **kwargs):
        """
        Flexible failure capture.

        Supported examples:
            ctx.artifacts.capture_failure("zn_CN-spcptnl-2.01-ff", "practice_timeout")

            ctx.artifacts.capture_failure(
                ctx.driver,
                "zn_spcptnl_failure",
                {"errors": errors},
            )
        """
        driver = self.driver
        label = "failure"
        reason = "failure"
        metadata = {}

        if args:
            first = args[0]

            # Old-style call: capture_failure(driver, label, metadata)
            if hasattr(first, "get_screenshot_as_file"):
                driver = first
                if len(args) >= 2:
                    label = args[1]
                    reason = args[1]
                if len(args) >= 3 and isinstance(args[2], dict):
                    metadata = args[2]

            # New-style call: capture_failure(test_code, reason, metadata)
            else:
                label = first
                if len(args) >= 2:
                    reason = args[1]
                if len(args) >= 3 and isinstance(args[2], dict):
                    metadata = args[2]

        if "label" in kwargs:
            label = kwargs["label"]
        if "reason" in kwargs:
            reason = kwargs["reason"]
        if "metadata" in kwargs and isinstance(kwargs["metadata"], dict):
            metadata = kwargs["metadata"]

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        base = f"{timestamp}_{self._safe_name(label)}_{self._safe_name(reason)}"

        screenshot_path = self.artifact_dir / f"{base}.png"
        html_path = self.artifact_dir / f"{base}.html"
        metadata_path = self.artifact_dir / f"{base}.json"

        result = {
            "label": str(label),
            "reason": str(reason),
            "screenshot": str(screenshot_path),
            "html": str(html_path),
            "metadata": str(metadata_path),
        }

        try:
            driver.get_screenshot_as_file(str(screenshot_path))
        except Exception as exc:
            result["screenshot_error"] = str(exc)

        try:
            html_path.write_text(driver.page_source or "", encoding="utf-8")
        except Exception as exc:
            result["html_error"] = str(exc)

        try:
            payload = {
                "label": str(label),
                "reason": str(reason),
                "timestamp": timestamp,
                "metadata": metadata,
                "result": result,
            }
            metadata_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            result["metadata_error"] = str(exc)

        return result

    def capture_screenshot(self, label="screenshot"):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = self.artifact_dir / f"{timestamp}_{self._safe_name(label)}.png"
        self.driver.get_screenshot_as_file(str(path))
        return path

    def capture_html(self, label="page"):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = self.artifact_dir / f"{timestamp}_{self._safe_name(label)}.html"
        path.write_text(self.driver.page_source or "", encoding="utf-8")
        return path