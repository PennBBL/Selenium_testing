from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SessionContext:
    driver: Any
    wait: Any
    logger: Any
    artifacts: Any
    subid: str
    battery_code: str
    output_dir: Path
    base_url: str = 'https://penncnp.pmacs.upenn.edu/assessments.pl?start=1'
    env_code: str = 'TEST'
    browser: str = 'chrome'
    headless: bool = False
    completed_tests: list[dict] = field(default_factory=list)
