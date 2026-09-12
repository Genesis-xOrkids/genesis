"""How well the catalog is being fed, per enabled storefront, computed in SQL.

This is the catalog-steward's source of numbers. It prints a markdown report,
and the steward narrates it without computing anything of its own.

    uv run python -m scripts.catalog_health

It only reads. A storefront's last run, how long since it last succeeded, what
its runs in the last seven days came to, and which quarantined records were
written or rewritten in that time, by source and stage. Quarantined records are
grouped by their source rather than joined to a storefront, because the source
name is a connector's to choose and this report should not depend on its shape.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from sqlalchemy import Connection, DateTime, bindparam, text

from api.genesis_api.db import read_connection

WINDOW_DAYS = 7

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
        where started_at > :now - make_interval(days => :days)
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
           round((extract(epoch from :now - storefronts.last_ingested_at) / 3600)::numeric, 1)
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
    where updated_at > :now - make_interval(days => :days)
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


def storefronts(connection: Connection, now: datetime.datetime) -> list[StorefrontHealth]:
    """Every enabled storefront's health at `now`, by domain."""
    rows = connection.execute(STOREFRONTS, {"now": now, "days": WINDOW_DAYS}).mappings()
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


def quarantine(connection: Connection, now: datetime.datetime) -> list[QuarantineGroup]:
    """Records quarantined in the window before `now`, most first."""
    rows = connection.execute(QUARANTINE, {"now": now, "days": WINDOW_DAYS}).mappings()
    return [QuarantineGroup(**row) for row in rows]


def _float(value: object) -> float | None:
    return None if value is None else float(str(value))


def _moment(value: datetime.datetime | None, missing: str) -> str:
    return missing if value is None else value.astimezone(datetime.UTC).strftime("%Y-%m-%d %H:%M")


def _cell(text_value: str) -> str:
    return " ".join(text_value.split()).replace("|", "\\|")


def report(connection: Connection, now: datetime.datetime) -> str:
    """The markdown report the steward posts."""
    healths = storefronts(connection, now)
    groups = quarantine(connection, now)
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
    with read_connection() as connection:
        print(report(connection, datetime.datetime.now(datetime.UTC)))


if __name__ == "__main__":
    main()
