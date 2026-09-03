"""Alembic environment.

The models are the schema authority: this file points autogenerate at
``Base.metadata`` and at the same database URL the application uses, so a drift
check is just ``upgrade head`` followed by ``revision --autogenerate``.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from api.genesis_api.models import Base
from api.genesis_api.settings import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to) -> bool:  # type: ignore[no-untyped-def]
    """Keep extension-owned objects out of autogenerate.

    pgvector and pg_trgm install their own types and indexes; without this,
    autogenerate proposes dropping them on every run.
    """
    return not (type_ == "table" and name in {"spatial_ref_sys"})


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
