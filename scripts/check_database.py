"""Verify a database is usable before pointing the app at it.

Run this after changing GENESIS_DATABASE_URL. It answers the questions that
otherwise surface as a confusing failure halfway through a migration: can we
connect, is pgvector actually available, is the schema current, and does a
vector round-trip work.

    PYTHONPATH=. uv run python scripts/check_database.py

The PYTHONPATH is needed because the project is a workspace rather than an
installed package, so the app modules are only importable from the repo root.
"""

from __future__ import annotations

import sys
from urllib.parse import urlparse

from sqlalchemy import text

from api.genesis_api.db import engine
from api.genesis_api.settings import settings


def main() -> int:
    parsed = urlparse(settings.database_url)
    host = parsed.hostname or "?"
    print(f"host     {host}")
    print(f"database {(parsed.path or '/').lstrip('/')}")

    if "neon.tech" in host and "sslmode" not in (parsed.query or ""):
        print("  warning: Neon requires sslmode=require; the connection will be refused")
    if "-pooler" in host:
        print("  warning: this is the pooled endpoint. Use the direct host for migrations.")

    try:
        with engine().connect() as connection:
            version = connection.execute(text("select version()")).scalar_one()
            print(f"connected {str(version).split(',')[0]}")

            available = connection.execute(
                text("select 1 from pg_available_extensions where name = 'vector'")
            ).scalar_one_or_none()
            installed = connection.execute(
                text("select extversion from pg_extension where extname = 'vector'")
            ).scalar_one_or_none()
            if installed:
                print(f"pgvector  installed, version {installed}")
            elif available:
                print("pgvector  available but not installed; the first migration installs it")
            else:
                print("pgvector  NOT AVAILABLE on this server - the catalog schema cannot deploy")
                return 1

            revision = connection.execute(
                text(
                    "select version_num from alembic_version"
                    " where exists (select 1 from information_schema.tables"
                    " where table_name = 'alembic_version')"
                )
            ).scalar_one_or_none()
            print(
                f"schema    {revision or 'not migrated yet - run: cd api && uv run alembic upgrade head'}"
            )

            tables = connection.execute(
                text(
                    "select count(*) from information_schema.tables"
                    " where table_schema = 'public' and table_name <> 'alembic_version'"
                )
            ).scalar_one()
            print(f"tables    {tables}")

            if installed:
                # A vector round-trip, because "the extension is installed" and
                # "vectors work" are different claims.
                distance = connection.execute(
                    text("select ('[1,0,0]'::vector) <=> ('[0,1,0]'::vector)")
                ).scalar_one()
                print(f"vector    cosine distance round-trip ok ({distance})")
    except Exception as exc:  # noqa: BLE001 - this script's whole job is to report the failure
        print(f"FAILED    {type(exc).__name__}: {str(exc)[:200]}")
        return 1

    print("\nready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
