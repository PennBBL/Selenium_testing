from __future__ import annotations

from collections import Counter
from copy import deepcopy


SPLLT_WORDS = [
    "LION",
    "HORSE",
    "TIGER",
    "COW",
    "TENT",
    "HOTEL",
    "CAVE",
    "HUT",
    "EMERALD",
    "SAPPHIRE",
    "OPAL",
    "PEARL",
    "TEACHER",
    "DENTIST",
    "ENGINEER",
    "PROFESSOR",
]

SPLLT_CONTROL_OTHER = "OTHER"
SPLLT_CONTROL_NEXT = "MOVE TO NEXT TRIAL"
SPLLT_BLOCK_COUNT = 3
SPLLT_MAX_RESPONSES = 25


SPLLT_QUADRANTS = {
    "q1": ["LION", "HORSE", "TIGER", "COW"],
    "q2": ["TENT", "HOTEL", "CAVE", "HUT"],
    "q3": ["EMERALD", "SAPPHIRE", "OPAL", "PEARL"],
    "q4": ["TEACHER", "DENTIST", "ENGINEER", "PROFESSOR"],
}


def _quadrant_sequence(words: list[str]) -> list[str]:
    """Create the distinctive 1/2/3/4 repeat pattern for one quadrant."""
    a, b, c, d = words
    return [
        a,
        b, b,
        c, c, c,
        d, d, d, d,
    ]


# One sequence = one full SPLLT administration scenario.
# The plugin repeats the exact same sequence in all three recall blocks.
SPLLT_SCENARIOS = {
    "coverage": [
        *SPLLT_WORDS,
        SPLLT_CONTROL_OTHER,
    ],

    "duplicates": [
        "LION", "LION",
        "HORSE", "HORSE", "HORSE",
        "TENT", "TENT", "TENT", "TENT",
        SPLLT_CONTROL_OTHER, SPLLT_CONTROL_OTHER,
    ],

    "empty": [],

    "other_only": [
        SPLLT_CONTROL_OTHER,
        SPLLT_CONTROL_OTHER,
        SPLLT_CONTROL_OTHER,
        SPLLT_CONTROL_OTHER,
    ],

    # Small, distinctive pattern repeated in every block. This is useful for
    # checking that response state resets cleanly between recall blocks.
    "block_reset": [
        "LION",
        "LION",
        "EMERALD",
        SPLLT_CONTROL_OTHER,
    ],

    # Exactly 25 responses, matching the App.js counter max.
    "max_25": [
        "LION", "LION", "LION", "LION", "LION",
        "HORSE", "HORSE", "HORSE", "HORSE", "HORSE",
        "TENT", "TENT", "TENT", "TENT", "TENT",
        "EMERALD", "EMERALD", "EMERALD", "EMERALD", "EMERALD",
        SPLLT_CONTROL_OTHER, SPLLT_CONTROL_OTHER, SPLLT_CONTROL_OTHER,
        SPLLT_CONTROL_OTHER, SPLLT_CONTROL_OTHER,
    ],

    "quadrant_q1": _quadrant_sequence(SPLLT_QUADRANTS["q1"]),
    "quadrant_q2": _quadrant_sequence(SPLLT_QUADRANTS["q2"]),
    "quadrant_q3": _quadrant_sequence(SPLLT_QUADRANTS["q3"]),
    "quadrant_q4": _quadrant_sequence(SPLLT_QUADRANTS["q4"]),
}


SPLLT_SCENARIO_ORDER = [
    "coverage",
    "duplicates",
    "empty",
    "other_only",
    "block_reset",
    "max_25",
    "quadrant_q1",
    "quadrant_q2",
    "quadrant_q3",
    "quadrant_q4",
]


def scenario_sequence(name: str) -> list[str]:
    """Return a copy so callers cannot accidentally mutate the master scenario."""
    if name not in SPLLT_SCENARIOS:
        raise KeyError(f"Unknown SPLLT scenario: {name}")
    return list(SPLLT_SCENARIOS[name])


def expected_counts(sequence: list[str]) -> dict[str, int]:
    counts = Counter(sequence)
    return dict(sorted(counts.items()))


def expected_scenario_payload(name: str) -> dict:
    """
    Build the expected interaction payload for one scenario.

    Every block intentionally uses the exact same response sequence.
    """
    sequence = scenario_sequence(name)
    counts = expected_counts(sequence)

    block = {
        "sequence": list(sequence),
        "counts": dict(counts),
        "total_responses": len(sequence),
    }

    return {
        "scenario": name,
        "block_count": SPLLT_BLOCK_COUNT,
        "same_sequence_all_blocks": True,
        "expected_per_block": deepcopy(block),
        "blocks": {
            str(i): deepcopy(block)
            for i in range(SPLLT_BLOCK_COUNT)
        },
    }


def validate_scenarios() -> None:
    allowed = set(SPLLT_WORDS) | {SPLLT_CONTROL_OTHER}

    missing = [name for name in SPLLT_SCENARIO_ORDER if name not in SPLLT_SCENARIOS]
    if missing:
        raise RuntimeError(f"SPLLT scenario order references missing scenarios: {missing}")

    for name, sequence in SPLLT_SCENARIOS.items():
        invalid = [response for response in sequence if response not in allowed]
        if invalid:
            raise RuntimeError(f"SPLLT scenario {name!r} has invalid responses: {invalid}")

        if len(sequence) > SPLLT_MAX_RESPONSES:
            raise RuntimeError(
                f"SPLLT scenario {name!r} has {len(sequence)} responses; "
                f"max is {SPLLT_MAX_RESPONSES}."
            )


validate_scenarios()
