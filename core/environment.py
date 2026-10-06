from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class CNBEnvironment:
    name: str
    env_file: Path
    base_host: str

    @property
    def assessment_url(self) -> str:
        return f"{self.base_host}/assessments.pl?start=1"

    @property
    def login_url(self) -> str:
        return f"{self.base_host}/assessments.pl"

    @property
    def results_url(self) -> str:
        return (
            f"{self.base_host}/results.pl"
            "?op=view_sessions&adminid=mruganks"
        )


ENVIRONMENTS = {
    "prod": CNBEnvironment(
        name="prod",
        env_file=PROJECT_ROOT / ".env",
        base_host="https://penncnp.pmacs.upenn.edu",
    ),
    "dev": CNBEnvironment(
        name="dev",
        env_file=PROJECT_ROOT / ".env.dev",
        base_host="https://penncnp-dev.pmacs.upenn.edu",
    ),
}


ENVIRONMENT_ALIASES = {
    "1": "prod",
    "prod": "prod",
    "production": "prod",
    "p": "prod",
    "2": "dev",
    "dev": "dev",
    "development": "dev",
    "d": "dev",
}


def choose_environment() -> str:
    """
    Prompt for the CNB target environment.

    There is intentionally no default so a blank Enter cannot accidentally
    select production.
    """
    print()
    print("Choose environment:")
    print("  1. Production")
    print("  2. Development")

    while True:
        raw = input(
            "Environment [1/prod, 2/dev]: "
        ).strip().lower()

        environment = ENVIRONMENT_ALIASES.get(raw)

        if environment:
            return environment

        print("Invalid environment. Choose 1/prod or 2/dev.")


def _known_dotenv_keys() -> set[str]:
    """
    Return every variable name defined in either project env file.

    Clearing these before loading the selected file prevents a PROD-only
    value from remaining in os.environ during a DEV run, or vice versa.
    """
    keys: set[str] = set()

    for config in ENVIRONMENTS.values():
        if not config.env_file.is_file():
            continue

        values = dotenv_values(config.env_file)
        keys.update(
            str(key)
            for key in values.keys()
            if key
        )

    return keys


def activate_environment(environment: str) -> CNBEnvironment:
    """
    Load only the selected environment's project variables.

    PROD:
        <project root>/.env

    DEV:
        <project root>/.env.dev

    Environment-sensitive application modules are imported only after this
    function returns.
    """
    key = str(environment or "").strip().lower()

    if key not in ENVIRONMENTS:
        raise ValueError(
            f"Unsupported environment {environment!r}. "
            f"Expected one of: {sorted(ENVIRONMENTS)}"
        )

    config = ENVIRONMENTS[key]

    if not config.env_file.is_file():
        raise FileNotFoundError(
            f"Environment file not found: {config.env_file}"
        )

    # Remove values belonging to either project env file first. This gives us
    # true separation when switching between PROD and DEV within the same
    # Python process or when a prior dotenv load occurred.
    for variable_name in _known_dotenv_keys():
        os.environ.pop(variable_name, None)

    loaded = load_dotenv(
        dotenv_path=config.env_file,
        override=True,
    )

    if not loaded:
        raise RuntimeError(
            f"Could not load environment file: {config.env_file}"
        )

    # Expose the selected environment explicitly to downstream modules.
    os.environ["CNB_ENVIRONMENT"] = config.name
    os.environ["CNB_ENV_FILE"] = str(config.env_file)
    os.environ["CNB_BASE_HOST"] = config.base_host
    os.environ["CNB_ASSESSMENT_URL"] = config.assessment_url
    os.environ["CNB_LOGIN_URL"] = config.login_url
    os.environ["CNB_RESULTS_URL"] = config.results_url

    return config


def apply_environment_to_scrapers(config: CNBEnvironment) -> None:
    """
    Point already-imported scraper modules at the selected environment.
    """
    from scraping import base_scraper

    base_scraper.LOGIN_URL = config.login_url
    base_scraper.RESULTS_URL = config.results_url

    try:
        from scraping import spllt_scraper
    except ImportError:
        spllt_scraper = None

    if spllt_scraper is not None:
        spllt_scraper.LOGIN_URL = config.login_url
        spllt_scraper.RESULTS_URL = config.results_url

        if hasattr(spllt_scraper, "BASE_RESULTS_URL"):
            spllt_scraper.BASE_RESULTS_URL = (
                config.results_url.split("?", 1)[0]
            )


def apply_environment_to_context(
    ctx,
    config: CNBEnvironment,
) -> None:
    """
    Put the selected environment onto SessionContext so battery generation,
    relaunches, dataset lookup, and scraping stay on the same CNB host.
    """
    ctx.environment = config.name
    ctx.base_url = config.assessment_url
