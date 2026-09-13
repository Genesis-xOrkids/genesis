"""How well the catalog is being fed, per enabled storefront, computed in SQL.

This is the catalog-steward's source of numbers. It prints a markdown report,
and the steward narrates it without computing anything of its own.

    uv run python -m scripts.catalog_health

It only reads. A storefront's last run, how long since it last succeeded, what
its runs in the last seven days came to, and which quarantined records were
written or rewritten in that time, by source and stage. Quarantined records are
grouped by their source rather than joined to a storefront, because the source
name is a connector's to choose and this report should not depend on its shape.

A cloud session cannot open a Postgres connection: its traffic leaves through an
HTTPS proxy. There the statements go to Neon's SQL-over-HTTPS endpoint on
`GENESIS_NEON_HOST`, and Claude Code's agent proxy attaches the read-only
connection string stored as the cloud environment's API credential, in the
`Neon-Connection-String` header, so the session never holds it.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, DateTime, TextClause, bindparam, text

from api.genesis_api.db import read_connection

WINDOW_DAYS = 7
TIMEOUT_SECONDS = 60

# Reads one statement with its named parameters, returning its rows.
Read = Callable[[TextClause, Mapping[str, object]], list[dict[str, Any]]]

STOREFRONTS = text(
    """
    with recent as (
        select storefront_id,
               count(*) filter (where status = 'succeeded') as succeeded,
               count(*) filter (where status = 'failed') as failed,
               count(*) filter (where status = 'blocked') as blocked,
               count(*) filter (where status = 'disallowed') as disallowed,
               sum(records_seen) as records_seen,
               sum(quarantined) as quarantined
        from ingestion_runs
        where started_at > cast(:now as timestamptz) - make_interval(days => cast(:days as int))
        group by storefront_id
    ),
    latest as (
        select distinct on (storefront_id) storefront_id, status, started_at, error
        from ingestion_runs
        order by storefront_id, started_at desc, id desc
    )
    select storefronts.domain,
           latest.status::text as last_status,
           latest.started_at as last_started_at,
           latest.error as last_error,
           storefronts.last_ingested_at,
           round((extract(epoch from cast(:now as timestamptz) - storefronts.last_ingested_at) / 3600)::numeric, 1)
               as hours_since_success,
           coalesce(recent.succeeded, 0) as succeeded,
           coalesce(recent.failed, 0) as failed,
           coalesce(recent.blocked, 0) as blocked,
           coalesce(recent.disallowed, 0) as disallowed,
           coalesce(recent.records_seen, 0) as records_seen,
           coalesce(recent.quarantined, 0) as quarantined,
           round(100.0 * recent.quarantined / nullif(recent.records_seen, 0), 1)
               as quarantined_pct
    from storefronts
    left join latest on latest.storefront_id = storefronts.id
    left join recent on recent.storefront_id = storefronts.id
    where storefronts.enabled
    order by storefronts.domain
    """
).bindparams(bindparam("now", type_=DateTime(timezone=True)))

QUARANTINE = text(
    """
    select source, stage, count(*) as records
    from ingestion_failures
    where updated_at > cast(:now as timestamptz) - make_interval(days => cast(:days as int))
    group by source, stage
    order by records desc, source, stage
    """
).bindparams(bindparam("now", type_=DateTime(timezone=True)))


@dataclass(frozen=True)
class StorefrontHealth:
    """One enabled storefront. None means there is nothing recorded to say."""

    domain: str
    last_status: str | None
    last_started_at: datetime.datetime | None
    last_error: str | None
    last_ingested_at: datetime.datetime | None
    hours_since_success: float | None
    succeeded: int
    failed: int
    blocked: int
    disallowed: int
    records_seen: int
    quarantined: int
    quarantined_pct: float | None


@dataclass(frozen=True)
class QuarantineGroup:
    """Quarantined records sharing a source and the stage that rejected them."""

    source: str
    stage: str
    records: int


def read_from(connection: Connection) -> Read:
    """Read through a database connection, as a machine with the database URL does."""

    def read(statement: TextClause, params: Mapping[str, object]) -> list[dict[str, Any]]:
        return [dict(row) for row in connection.execute(statement, params).mappings()]

    return read


# Postgres type ids Neon's HTTP endpoint answers with, and how each becomes the
# value the driver would have given. Every other type arrives as text already.
FROM_TEXT: dict[int, Callable[[str], object]] = {
    20: int,
    21: int,
    23: int,
    1700: float,
    1114: datetime.datetime.fromisoformat,
    1184: datetime.datetime.fromisoformat,
}


def read_over_https(host: str) -> Read:
    """Read through Neon's SQL-over-HTTPS endpoint, as a cloud session must."""

    def read(statement: TextClause, params: Mapping[str, object]) -> list[dict[str, Any]]:
        names = list(params)
        sql = re.sub(
            r"(?<!:):([a-z_]+)\b",
            lambda match: f"${names.index(match.group(1)) + 1}",
            statement.text,
        )
        values = [
            value.isoformat() if isinstance(value, datetime.datetime) else value
            for value in params.values()
        ]
        request = urllib.request.Request(
            f"https://{host}/sql",
            data=json.dumps({"query": sql, "params": values}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                answer = json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read()[:400].decode(errors="replace")
            raise SystemExit(f"Neon refused the query ({error.code}): {detail}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise SystemExit(f"could not reach Neon: {error}") from error
        convert = {field["name"]: FROM_TEXT.get(field["dataTypeID"]) for field in answer["fields"]}
        return [
            {name: _typed(value, convert[name]) for name, value in row.items()}
            for row in answer["rows"]
        ]

    return read


def _typed(value: object, convert: Callable[[str], object] | None) -> object:
    """A value from Neon's HTTP answer as the driver would give it. Null stays null."""
    if value is None or convert is None:
        return value
    return convert(str(value))


def storefronts(read: Read, now: datetime.datetime) -> list[StorefrontHealth]:
    """Every enabled storefront's health at `now`, by domain."""
    rows = read(STOREFRONTS, {"now": now, "days": WINDOW_DAYS})
    return [
        StorefrontHealth(
            **{
                **row,
                "hours_since_success": _float(row["hours_since_success"]),
                "quarantined_pct": _float(row["quarantined_pct"]),
            }
        )
        for row in rows
    ]


def quarantine(read: Read, now: datetime.datetime) -> list[QuarantineGroup]:
    """Records quarantined in the window before `now`, most first."""
    rows = read(QUARANTINE, {"now": now, "days": WINDOW_DAYS})
    return [QuarantineGroup(**row) for row in rows]


def _float(value: object) -> float | None:
    return None if value is None else float(str(value))


def _moment(value: datetime.datetime | None, missing: str) -> str:
    return missing if value is None else value.astimezone(datetime.UTC).strftime("%Y-%m-%d %H:%M")


def _cell(text_value: str) -> str:
    return " ".join(text_value.split()).replace("|", "\\|")


def report(read: Read, now: datetime.datetime) -> str:
    """The markdown report the steward posts."""
    healths = storefronts(read, now)
    groups = quarantine(read, now)
    lines = [
        f"# Catalog health at {_moment(now, '')} UTC",
        "",
        f"## Storefronts ({len(healths)} enabled)",
        "",
        f"Runs, records and quarantine cover the {WINDOW_DAYS} days before this report.",
        "",
        "| Storefront | Last run | Last run started | Last success | Hours since success"
        " | Succeeded | Failed | Blocked | Disallowed | Records seen | Quarantined"
        " | Quarantined % |",
        "|---|---|---|---|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    lines.extend(
        f"| {health.domain} | {health.last_status or 'no runs'}"
        f" | {_moment(health.last_started_at, '-')}"
        f" | {_moment(health.last_ingested_at, 'none recorded')}"
        f" | {'-' if health.hours_since_success is None else health.hours_since_success}"
        f" | {health.succeeded} | {health.failed} | {health.blocked} | {health.disallowed}"
        f" | {health.records_seen} | {health.quarantined}"
        f" | {'-' if health.quarantined_pct is None else health.quarantined_pct} |"
        for health in healths
    )
    errors = [health for health in healths if health.last_error]
    if errors:
        lines += ["", "## Last run errors", ""]
        lines.extend(
            f"- **{health.domain}**: {_cell(health.last_error or '')}" for health in errors
        )
    lines += ["", f"## Quarantined records, last {WINDOW_DAYS} days", ""]
    if groups:
        lines += ["| Source | Stage | Records |", "|---|---|--:|"]
        lines.extend(f"| {group.source} | {group.stage} | {group.records} |" for group in groups)
    else:
        lines.append("None.")
    return "\n".join(lines)


def main() -> None:
    now = datetime.datetime.now(datetime.UTC)
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        host = os.environ.get("GENESIS_NEON_HOST")
        if not host:
            raise SystemExit("GENESIS_NEON_HOST is not set on this cloud environment")
        print(report(read_over_https(host), now))
        return
    with read_connection() as connection:
        print(report(read_from(connection), now))


if __name__ == "__main__":
    main()
