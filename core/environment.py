from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


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
        # Preserve the results-page behavior currently used by the project.
        return (
            f"{self.base_host}/results.pl"
            "?op=view_sessions&adminid=mruganks"
        )


ENVIRONMENTS = {
    "prod": CNBEnvironment(
        name="prod",
        env_file=Path(".env"),
        base_host="https://penncnp.pmacs.upenn.edu",
    ),
    "dev": CNBEnvironment(
        name="dev",
        env_file=Path(".env.dev"),
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

    There is intentionally no default. This prevents an accidental production
    run when the operator intended to use development.
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

        print(
            "Invalid environment. Choose 1/prod or 2/dev."
        )


def activate_environment(environment: str) -> CNBEnvironment:
    """
    Load the selected .env file and return its CNB URL configuration.

    override=True is important because some existing modules may have already
    called load_dotenv() during import. The operator's explicit environment
    choice must win over values loaded earlier in the process.
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

    loaded = load_dotenv(
        dotenv_path=config.env_file,
        override=True,
    )

    if not loaded:
        raise RuntimeError(
            f"Could not load environment file: {config.env_file}"
        )

    # Make the selected environment visible to the rest of the process.
    os.environ["CNB_ENVIRONMENT"] = config.name
    os.environ["CNB_BASE_HOST"] = config.base_host
    os.environ["CNB_ASSESSMENT_URL"] = config.assessment_url
    os.environ["CNB_LOGIN_URL"] = config.login_url
    os.environ["CNB_RESULTS_URL"] = config.results_url

    return config


def apply_environment_to_scrapers(config: CNBEnvironment) -> None:
    """
    Update scraper module URL globals after environment selection.

    This is needed because the existing scraper modules currently define URL
    constants at import time. Applying the selected values here keeps both
    generic score scraping and SPLLT dataset-specific scraping on the same
    CNB environment as the test run.
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
        spllt_scraper.BASE_RESULTS_URL = (
            config.results_url.split("?", 1)[0]
        )


def apply_environment_to_context(ctx, config: CNBEnvironment) -> None:
    """
    Put the selected environment onto SessionContext.

    launch_battery() and SPLLT relaunches can then keep using ctx.base_url
    without needing environment-specific branching of their own.
    """
    ctx.environment = config.name
    ctx.base_url = config.assessment_url
