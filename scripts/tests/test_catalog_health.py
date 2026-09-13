"""Tests for the catalog health numbers, against the test database."""

from __future__ import annotations

import datetime
import io
import json
import urllib.request
from typing import Any

import pytest
from sqlalchemy import insert
from sqlalchemy.orm import Session

from api.genesis_api.models import IngestionFailure
from api.genesis_api.models.enums import IngestionRunStatus, StorefrontRoute
from api.genesis_api.writer import WriteSpec, write
from scripts import catalog_health

NOW = datetime.datetime(2026, 9, 12, 12, 0, tzinfo=datetime.UTC)
HOUR = datetime.timedelta(hours=1)
DAY = datetime.timedelta(days=1)


def _storefront(
    session: Session,
    domain: str,
    *,
    enabled: bool = True,
    last_ingested_at: datetime.datetime | None = None,
) -> int:
    result = write(
        session,
        [
            WriteSpec(
                entity="Storefront",
                natural_key={"domain": domain},
                values={
                    "retailer_name": "Health Test",
                    "route": StorefrontRoute.public_feed,
                    "enabled": enabled,
                    "last_ingested_at": last_ingested_at,
                },
            )
        ],
    )[0]
    session.flush()
    return result.id


def _run(
    session: Session,
    storefront_id: int,
    status: IngestionRunStatus,
    started_at: datetime.datetime,
    *,
    records_seen: int = 0,
    quarantined: int = 0,
    error: str | None = None,
) -> None:
    write(
        session,
        [
            WriteSpec(
                entity="IngestionRun",
                values={
                    "storefront_id": storefront_id,
                    "status": status,
                    "route": StorefrontRoute.public_feed,
                    "started_at": started_at,
                    "finished_at": started_at + HOUR,
                    "records_seen": records_seen,
                    "quarantined": quarantined,
                    "error": error,
                },
            )
        ],
    )
    session.flush()


def _health(session: Session, domain: str) -> catalog_health.StorefrontHealth:
    healths = catalog_health.storefronts(catalog_health.read_from(session.connection()), NOW)
    return next(health for health in healths if health.domain == domain)


def test_the_last_run_and_the_time_since_success_come_from_the_database(session: Session) -> None:
    storefront_id = _storefront(session, "stale.health.test", last_ingested_at=NOW - 30 * HOUR)
    _run(session, storefront_id, IngestionRunStatus.succeeded, NOW - 30 * HOUR)
    _run(session, storefront_id, IngestionRunStatus.blocked, NOW - 2 * HOUR, error="HTTP 403")

    health = _health(session, "stale.health.test")

    assert (health.last_status, health.last_error) == ("blocked", "HTTP 403")
    assert health.last_started_at == NOW - 2 * HOUR
    assert health.hours_since_success == 30.0
    assert (health.succeeded, health.failed, health.blocked, health.disallowed) == (1, 0, 1, 0)


def test_only_runs_inside_the_window_are_counted(session: Session) -> None:
    storefront_id = _storefront(session, "window.health.test", last_ingested_at=NOW - DAY)
    _run(
        session,
        storefront_id,
        IngestionRunStatus.succeeded,
        NOW - 8 * DAY,
        records_seen=100,
        quarantined=50,
    )
    _run(
        session,
        storefront_id,
        IngestionRunStatus.succeeded,
        NOW - DAY,
        records_seen=200,
        quarantined=10,
    )

    health = _health(session, "window.health.test")

    assert (health.succeeded, health.records_seen, health.quarantined) == (1, 200, 10)
    assert health.quarantined_pct == 5.0


def test_a_storefront_with_no_runs_is_unknown_not_zero(session: Session) -> None:
    _storefront(session, "new.health.test")

    health = _health(session, "new.health.test")

    assert health.last_status is None
    assert health.hours_since_success is None
    assert health.quarantined_pct is None
    assert (health.succeeded, health.records_seen, health.quarantined) == (0, 0, 0)
    row = next(
        line
        for line in catalog_health.report(
            catalog_health.read_from(session.connection()), NOW
        ).splitlines()
        if line.startswith("| new.health.test ")
    )
    assert row.startswith("| new.health.test | no runs | - | none recorded | - |")


def test_disabled_storefronts_are_left_out(session: Session) -> None:
    _storefront(session, "off.health.test", enabled=False)

    domains = {
        health.domain
        for health in catalog_health.storefronts(
            catalog_health.read_from(session.connection()), NOW
        )
    }

    assert "off.health.test" not in domains


def test_quarantined_records_are_grouped_by_source_and_stage_inside_the_window(
    session: Session,
) -> None:
    table = IngestionFailure.__table__
    rows = [
        ("shopify-public:group.health.test", "a", "normalize", NOW - HOUR),
        ("shopify-public:group.health.test", "b", "normalize", NOW - 2 * DAY),
        ("shopify-public:group.health.test", "c", "price", NOW - DAY),
        ("shopify-public:group.health.test", "d", "normalize", NOW - 9 * DAY),
    ]
    session.execute(
        insert(table),
        [
            {
                "source": source,
                "source_id": source_id,
                "stage": stage,
                "error": "bad record",
                "payload": "{}",
                "updated_at": updated_at,
            }
            for source, source_id, stage, updated_at in rows
        ],
    )

    groups = [
        group
        for group in catalog_health.quarantine(catalog_health.read_from(session.connection()), NOW)
        if group.source == "shopify-public:group.health.test"
    ]

    assert groups == [
        catalog_health.QuarantineGroup("shopify-public:group.health.test", "normalize", 2),
        catalog_health.QuarantineGroup("shopify-public:group.health.test", "price", 1),
    ]


def test_a_multi_line_error_stays_on_its_one_line_in_the_report(session: Session) -> None:
    storefront_id = _storefront(session, "error.health.test")
    _run(
        session,
        storefront_id,
        IngestionRunStatus.failed,
        NOW - HOUR,
        error="ValueError: feed changed\n  at page 3 | products",
    )

    report = catalog_health.report(catalog_health.read_from(session.connection()), NOW)

    assert "- **error.health.test**: ValueError: feed changed at page 3 \\| products" in report


class Neon:
    """Stands in for `urlopen` in front of Neon's HTTP endpoint, keeping what it was sent."""

    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = answer
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, **_options: float) -> io.BytesIO:
        self.requests.append(request)
        return io.BytesIO(json.dumps(self.answer).encode())


def test_over_https_the_parameters_are_numbered_and_the_values_typed_as_the_driver_would(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    neon = Neon(
        {
            "fields": [
                {"name": "source", "dataTypeID": 1043},
                {"name": "stage", "dataTypeID": 1043},
                {"name": "records", "dataTypeID": 20},
            ],
            "rows": [{"source": "shopify-public:a.test", "stage": "normalize", "records": "31"}],
        }
    )
    monkeypatch.setattr(catalog_health.urllib.request, "urlopen", neon)

    groups = catalog_health.quarantine(catalog_health.read_over_https("ep-x.neon.test"), NOW)

    assert groups == [catalog_health.QuarantineGroup("shopify-public:a.test", "normalize", 31)]
    (request,) = neon.requests
    assert request.full_url == "https://ep-x.neon.test/sql"
    sent = json.loads(request.data or b"")
    assert "cast($1 as timestamptz) - make_interval(days => cast($2 as int))" in sent["query"]
    assert ":now" not in sent["query"]
    assert ":days" not in sent["query"]
    assert sent["params"] == [NOW.isoformat(), catalog_health.WINDOW_DAYS]
    # The connection string is the agent proxy's to attach, never the session's.
    assert request.get_header("Neon-connection-string") is None


def test_timestamps_and_numerics_over_https_come_back_as_the_driver_gives_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fields = [
        ("domain", 1043),
        ("last_status", 25),
        ("last_started_at", 1184),
        ("last_error", 25),
        ("last_ingested_at", 1184),
        ("hours_since_success", 1700),
        ("succeeded", 20),
        ("failed", 20),
        ("blocked", 20),
        ("disallowed", 20),
        ("records_seen", 20),
        ("quarantined", 20),
        ("quarantined_pct", 1700),
    ]
    row = {
        "domain": "a.test",
        "last_status": "succeeded",
        "last_started_at": "2026-09-06 04:30:15.822288+00",
        "last_error": None,
        "last_ingested_at": None,
        "hours_since_success": None,
        "succeeded": "2",
        "failed": "0",
        "blocked": "0",
        "disallowed": "0",
        "records_seen": "588",
        "quarantined": "2",
        "quarantined_pct": "0.3",
    }
    answer = {"fields": [{"name": name, "dataTypeID": oid} for name, oid in fields], "rows": [row]}
    monkeypatch.setattr(catalog_health.urllib.request, "urlopen", Neon(answer))

    (health,) = catalog_health.storefronts(catalog_health.read_over_https("ep-x.neon.test"), NOW)

    assert health.last_started_at == datetime.datetime(
        2026, 9, 6, 4, 30, 15, 822288, tzinfo=datetime.UTC
    )
    assert health.last_ingested_at is None
    assert health.hours_since_success is None
    assert (health.succeeded, health.records_seen, health.quarantined_pct) == (2, 588, 0.3)


def test_a_cloud_session_without_the_neon_host_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.delenv("GENESIS_NEON_HOST", raising=False)
    with pytest.raises(SystemExit, match="GENESIS_NEON_HOST is not set"):
        catalog_health.main()
