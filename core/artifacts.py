from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class Artifacts:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.screenshots_dir = output_dir / 'screenshots'
        self.html_dir = output_dir / 'html'
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.html_dir.mkdir(parents=True, exist_ok=True)

    def _safe_name(self, name: str) -> str:
        cleaned = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in name)
        return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{cleaned}"

    def capture_failure(self, driver, name: str, metadata: dict | None = None):
        base = self._safe_name(name)
        screenshot_path = self.screenshots_dir / f'{base}.png'
        html_path = self.html_dir / f'{base}.html'
        meta_path = self.output_dir / f'{base}_metadata.json'
        try:
            driver.save_screenshot(str(screenshot_path))
        except Exception:
            pass
        try:
            html_path.write_text(driver.page_source, encoding='utf-8')
        except Exception:
            pass
        if metadata:
            meta_path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
