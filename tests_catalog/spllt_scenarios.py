from __future__ import annotations

from collections import Counter
from copy import deepcopy


SPLLT_CONTROL_OTHER = "OTHER"
SPLLT_CONTROL_NEXT = "MOVE TO NEXT TRIAL"
SPLLT_BLOCK_COUNT = 3
SPLLT_MAX_RESPONSES = 25

SPLLT_TEST_CODES = {
    "spllt-a-1.00-ff",
    "spllt-b-1.00-ff",
    "spllt-c-1.00-ff",
    "spllt-d-1.00-ff",
}

SPLLT_VARIANTS = {
    "spllt-a-1.00-ff": {
        "variant": "A",
        "battery_code": "SPLLT-A",
        "quadrants": {
            "q1": ["LION", "HORSE", "TIGER", "COW"],
            "q2": ["TENT", "HOTEL", "CAVE", "HUT"],
            "q3": ["EMERALD", "SAPPHIRE", "OPAL", "PEARL"],
            "q4": ["TEACHER", "DENTIST", "ENGINEER", "PROFESSOR"],
        },
    },
    "spllt-b-1.00-ff": {
        "variant": "B",
        "battery_code": "SPLLT-B",
        "quadrants": {
            "q1": ["TRUMPET", "VIOLIN", "CLARINET", "FLUTE"],
            "q2": ["SUGAR", "GARLIC", "VANILLA", "CINNAMON"],
            "q3": ["COAL", "KEROSENE", "WOOD", "GASOLINE"],
            "q4": ["LETTUCE", "BEAN", "POTATO", "CORN"],
        },
    },
    "spllt-c-1.00-ff": {
        "variant": "C",
        "battery_code": "SPLLT-C",
        "quadrants": {
            "q1": ["EAGLE", "PIGEON", "OWL", "CANARY"],
            "q2": ["WRENCH", "SAW", "DRILL", "SANDER"],
            "q3": ["COPPER", "ALUMINUM", "BRONZE", "STEEL"],
            "q4": ["TENNIS", "GOLF", "SOCCER", "SOFTBALL"],
        },
    },
    "spllt-d-1.00-ff": {
        "variant": "D",
        "battery_code": "SPLLT-D",
        "quadrants": {
            "q1": ["PANTS", "SKIRT", "SHOE", "HAT"],
            "q2": ["VALLEY", "CANYON", "CLIFF", "MOUNTAIN"],
            "q3": ["LADYBUG", "SPIDER", "BEETLE", "ANT"],
            "q4": ["DAFFODIL", "CARNATION", "LILY", "ORCHID"],
        },
    },
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


def normalize_test_code(test_code: str | None) -> str:
    code = str(test_code or "spllt-a-1.00-ff").strip().lower()

    if code not in SPLLT_VARIANTS:
        raise KeyError(
            f"Unknown SPLLT test code {test_code!r}. "
            f"Supported: {sorted(SPLLT_VARIANTS)}"
        )

    return code


def variant_config(test_code: str | None) -> dict:
    return SPLLT_VARIANTS[normalize_test_code(test_code)]


def variant_name(test_code: str | None) -> str:
    return str(variant_config(test_code)["variant"])


def battery_code_for_test(test_code: str | None) -> str:
    return str(variant_config(test_code)["battery_code"])


def quadrants_for_test(test_code: str | None) -> dict[str, list[str]]:
    quadrants = variant_config(test_code)["quadrants"]
    return {
        name: list(words)
        for name, words in quadrants.items()
    }


def words_for_test(test_code: str | None) -> list[str]:
    quadrants = quadrants_for_test(test_code)
    return [
        *quadrants["q1"],
        *quadrants["q2"],
        *quadrants["q3"],
        *quadrants["q4"],
    ]


def _quadrant_sequence(words: list[str]) -> list[str]:
    """Create the distinctive 1/2/3/4 repeat pattern for one quadrant."""
    a, b, c, d = words

    return [
        a,
        b, b,
        c, c, c,
        d, d, d, d,
    ]


def build_scenarios(test_code: str | None) -> dict[str, list[str]]:
    """
    Build the same ten functional scenarios for one SPLLT variant.

    The scenario logic is positional, so A/B/C/D receive identical testing
    behavior while the visible response words come from that variant.
    """
    quadrants = quadrants_for_test(test_code)
    words = words_for_test(test_code)

    q1 = quadrants["q1"]
    q2 = quadrants["q2"]
    q3 = quadrants["q3"]

    return {
        "coverage": [
            *words,
            SPLLT_CONTROL_OTHER,
        ],

        "duplicates": [
            q1[0], q1[0],
            q1[1], q1[1], q1[1],
            q2[0], q2[0], q2[0], q2[0],
            SPLLT_CONTROL_OTHER, SPLLT_CONTROL_OTHER,
        ],

        "empty": [],

        "other_only": [
            SPLLT_CONTROL_OTHER,
            SPLLT_CONTROL_OTHER,
            SPLLT_CONTROL_OTHER,
            SPLLT_CONTROL_OTHER,
        ],

        "block_reset": [
            q1[0],
            q1[0],
            q3[0],
            SPLLT_CONTROL_OTHER,
        ],

        "max_25": [
            q1[0], q1[0], q1[0], q1[0], q1[0],
            q1[1], q1[1], q1[1], q1[1], q1[1],
            q2[0], q2[0], q2[0], q2[0], q2[0],
            q3[0], q3[0], q3[0], q3[0], q3[0],
            SPLLT_CONTROL_OTHER, SPLLT_CONTROL_OTHER,
            SPLLT_CONTROL_OTHER, SPLLT_CONTROL_OTHER,
            SPLLT_CONTROL_OTHER,
        ],

        "quadrant_q1": _quadrant_sequence(quadrants["q1"]),
        "quadrant_q2": _quadrant_sequence(quadrants["q2"]),
        "quadrant_q3": _quadrant_sequence(quadrants["q3"]),
        "quadrant_q4": _quadrant_sequence(quadrants["q4"]),
    }


def scenario_sequence(
    name: str,
    test_code: str | None = "spllt-a-1.00-ff",
) -> list[str]:
    """Return a copy so callers cannot mutate the scenario definition."""
    scenarios = build_scenarios(test_code)

    if name not in scenarios:
        raise KeyError(f"Unknown SPLLT scenario: {name}")

    return list(scenarios[name])


def expected_counts(sequence: list[str]) -> dict[str, int]:
    counts = Counter(sequence)
    return dict(sorted(counts.items()))


def expected_scenario_payload(
    name: str,
    test_code: str | None = "spllt-a-1.00-ff",
) -> dict:
    """
    Build the expected interaction payload for one scenario.

    Every recall block intentionally uses the same response sequence.
    """
    code = normalize_test_code(test_code)
    sequence = scenario_sequence(name, test_code=code)
    counts = expected_counts(sequence)

    block = {
        "sequence": list(sequence),
        "counts": dict(counts),
        "total_responses": len(sequence),
    }

    return {
        "test_code": code,
        "variant": variant_name(code),
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
    for test_code in sorted(SPLLT_TEST_CODES):
        words = words_for_test(test_code)

        if len(words) != 16:
            raise RuntimeError(
                f"{test_code} defines {len(words)} SPLLT words; expected 16."
            )

        if len(set(words)) != 16:
            raise RuntimeError(
                f"{test_code} contains duplicate words in its 16-word set."
            )

        scenarios = build_scenarios(test_code)
        allowed = set(words) | {SPLLT_CONTROL_OTHER}

        missing = [
            name
            for name in SPLLT_SCENARIO_ORDER
            if name not in scenarios
        ]

        if missing:
            raise RuntimeError(
                f"{test_code} scenario order references missing scenarios: "
                f"{missing}"
            )

        for name, sequence in scenarios.items():
            invalid = [
                response
                for response in sequence
                if response not in allowed
            ]

            if invalid:
                raise RuntimeError(
                    f"{test_code} scenario {name!r} has invalid responses: "
                    f"{invalid}"
                )

            if len(sequence) > SPLLT_MAX_RESPONSES:
                raise RuntimeError(
                    f"{test_code} scenario {name!r} has "
                    f"{len(sequence)} responses; max is "
                    f"{SPLLT_MAX_RESPONSES}."
                )


validate_scenarios()
