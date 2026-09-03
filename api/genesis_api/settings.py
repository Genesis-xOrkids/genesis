"""Runtime configuration.

No silent fallbacks: a missing required setting raises at import, not at the
first query. Defaults exist only for local development values that are safe to
be wrong (the dev database URL), never for credentials or model routing.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchored to the repository root rather than the working directory. A relative
# ".env" resolves against wherever the process was started, so running Alembic
# from api/ silently picked up the built-in local default instead of the
# configured database. That failure is silent and dangerous in exactly the wrong
# direction: it reports success while migrating the wrong database.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GENESIS_", env_file=REPO_ROOT / ".env", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://genesis:genesis@localhost:5434/genesis"
    sql_echo: bool = False

    # Tests always run here, never against database_url. Otherwise pointing
    # .env at a hosted database silently turns every `pytest` run into writes
    # against it, and the tests that commit would be writing to whatever branch
    # the app is configured for.
    test_database_url: str = "postgresql+psycopg://genesis:genesis@localhost:5434/genesis"

    # Which platform serves model calls. The first-party API is the default
    # because it keeps a cloud account out of the path of something that has no
    # other reason to need one; the AWS options exist for enterprise customers
    # whose security review requires them, and are selected per tenant.
    model_platform: str = "anthropic_api"
    # Only read for bedrock_mantle, which has no region default.
    aws_region: str | None = None


settings = Settings()
