"""Runtime configuration.

No silent fallbacks: a missing required setting raises at import, not at the
first query. Defaults exist only for local development values that are safe to
be wrong (the dev database URL), never for credentials or model routing.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GENESIS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://genesis:genesis@localhost:5434/genesis"
    sql_echo: bool = False

    # Which platform serves model calls. The first-party API is the default
    # because it keeps a cloud account out of the path of something that has no
    # other reason to need one; the AWS options exist for enterprise customers
    # whose security review requires them, and are selected per tenant.
    model_platform: str = "anthropic_api"
    # Only read for bedrock_mantle, which has no region default.
    aws_region: str | None = None


settings = Settings()
