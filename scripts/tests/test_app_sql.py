"""Tests for reading the application database: through a connection, or over Neon's HTTPS endpoint."""

from __future__ import annotations

import datetime
import decimal
import io
import json
import urllib.request
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from scripts import app_sql

NOW = datetime.datetime(2026, 9, 12, 12, 0, tzinfo=datetime.UTC)
FAILURES = text(
    "select source, stage, count(*) as records from ingestion_failures "
    "where updated_at > cast(:now as timestamptz) - make_interval(days => cast(:days as int)) "
    "group by source, stage"
)


class Neon:
    """Stands in for `urlopen` in front of Neon's HTTP endpoint, keeping what it was sent."""

    def __init__(self, fields: list[tuple[str, int]], row: dict[str, object]) -> None:
        self.answer = {
            "fields": [{"name": name, "dataTypeID": type_id} for name, type_id in fields],
            "rows": [row],
        }
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, **_options: float) -> io.BytesIO:
        self.requests.append(request)
        return io.BytesIO(json.dumps(self.answer).encode())


def test_over_https_parameters_are_numbered_and_no_connection_string_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    neon = Neon(
        [("source", 1043), ("stage", 1043), ("records", 20)],
        {"source": "shopify-public:a.test", "stage": "normalize", "records": "31"},
    )
    monkeypatch.setattr(app_sql.urllib.request, "urlopen", neon)

    rows = app_sql.read_over_https("ep-x.neon.test")(FAILURES, {"now": NOW, "days": 7})

    assert rows == [{"source": "shopify-public:a.test", "stage": "normalize", "records": 31}]
    (request,) = neon.requests
    assert request.full_url == "https://ep-x.neon.test/sql"
    sent = json.loads(request.data or b"")
    assert "cast($1 as timestamptz) - make_interval(days => cast($2 as int))" in sent["query"]
    assert ":now" not in sent["query"]
    assert sent["params"] == [NOW.isoformat(), 7]
    # The connection string is the agent proxy's to attach, never the session's.
    assert request.get_header("Neon-connection-string") is None


def test_each_type_comes_back_as_the_driver_gives_it(monkeypatch: pytest.MonkeyPatch) -> None:
    # Values as Neon's endpoint sent them for these types on 2026-09-13.
    fields = [
        ("yes", 16),
        ("no", 16),
        ("unknown", 16),
        ("small", 21),
        ("big", 20),
        ("ratio", 701),
        ("amount", 1700),
        ("day", 1082),
        ("local", 1114),
        ("moment", 1184),
        ("id", 2950),
        ("code", 1042),
    ]
    row: dict[str, object] = {
        "yes": True,
        "no": False,
        "unknown": None,
        "small": 1,
        "big": "3",
        "ratio": 2.5,
        "amount": "3.25",
        "day": "2026-09-13",
        "local": "2026-09-13 01:02:03",
        "moment": "2026-09-13 01:02:03+00",
        "id": "d29400c6-d451-4736-836b-ab387e8eb5cc",
        "code": "z ",
    }
    monkeypatch.setattr(app_sql.urllib.request, "urlopen", Neon(fields, row))

    (read,) = app_sql.read_over_https("ep-x.neon.test")(text("select 1"), {})

    assert read == {
        "yes": True,
        "no": False,
        "unknown": None,
        "small": 1,
        "big": 3,
        "ratio": 2.5,
        "amount": decimal.Decimal("3.25"),
        "day": datetime.date(2026, 9, 13),
        "local": datetime.datetime(2026, 9, 13, 1, 2, 3),  # noqa: DTZ001 - `timestamp` has no zone, and neither does what the driver gives
        "moment": datetime.datetime(2026, 9, 13, 1, 2, 3, tzinfo=datetime.UTC),
        "id": uuid.UUID("d29400c6-d451-4736-836b-ab387e8eb5cc"),
        "code": "z ",
    }


def test_a_type_the_reader_does_not_convert_is_refused_by_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app_sql.urllib.request, "urlopen", Neon([("status", 32776)], {"status": "succeeded"})
    )
    with pytest.raises(SystemExit, match=r"column status has Postgres type id 32776.*status::text"):
        app_sql.read_over_https("ep-x.neon.test")(text("select status from ingestion_runs"), {})


def test_a_boolean_that_is_not_a_boolean_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        app_sql.urllib.request, "urlopen", Neon([("enabled", 16)], {"enabled": "f"})
    )
    with pytest.raises(SystemExit, match="for a boolean"):
        app_sql.read_over_https("ep-x.neon.test")(text("select enabled from storefronts"), {})


def test_a_cloud_session_without_the_neon_host_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.delenv("GENESIS_NEON_HOST", raising=False)
    with pytest.raises(SystemExit, match="GENESIS_NEON_HOST is not set"), app_sql.reader():
        pass


def test_on_a_machine_the_reader_cannot_write(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    with app_sql.reader() as read, pytest.raises(DBAPIError, match="read-only transaction"):
        read(text("update storefronts set enabled = enabled where false"), {})
