from dataclasses import dataclass, field


@dataclass
class TestRunResult:
    status: str
    errors: list[str] = field(default_factory=list)
