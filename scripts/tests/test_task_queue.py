"""Tests for the dispatch queue.

`query` is replaced in both `task_queue` and `agent_activity` - a task's
dispatcher run is written through the recorder - by one stand-in that keeps the
statements it was sent and answers as D1 would, so nothing reaches the live
database.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from scripts import agent_activity, task_queue

MOMENT = dt.datetime(2026, 9, 12, 3, 0, 0, tzinfo=dt.UTC)
AT = "'2026-09-12T03:00:00+00:00'"


class Database:
    """Stands in for `brain_db.query`, answering by a statement's opening words."""

    def __init__(self) -> None:
        self.statements: list[str] = []
        self.answers: dict[str, list[dict[str, Any]]] = {}

    def __call__(self, sql: str) -> list[dict[str, Any]]:
        self.statements.append(sql)
        for opening, rows in self.answers.items():
            if sql.startswith(opening):
                return rows
        return []


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Database:
    stand_in = Database()
    monkeypatch.setattr(task_queue, "query", stand_in)
    monkeypatch.setattr(agent_activity, "query", stand_in)
    return stand_in


def test_a_claim_takes_the_oldest_pending_task_in_one_statement(database: Database) -> None:
    database.answers["UPDATE tasks SET claimed_at"] = [{"id": 4, "text": "t", "assignee": None}]
    assert task_queue.claim(MOMENT) == {"id": 4, "text": "t", "assignee": None}
    (statement,) = database.statements
    assert "ORDER BY created_at, id LIMIT 1" in statement
    # Checked in the subquery and again on the row, so a task cancelled between
    # the two is not claimed.
    assert statement.count("claimed_at IS NULL AND cancelled_at IS NULL") == 2
    assert statement.endswith("RETURNING id, text, assignee")


@pytest.mark.usefixtures("database")
def test_nothing_waiting_claims_nothing() -> None:
    assert task_queue.claim(MOMENT) is None


def test_starting_records_the_session_and_opens_the_dispatcher_run(database: Database) -> None:
    task_queue.started(4, "7c5dcf5d", MOMENT)
    recorded, opened = database.statements
    assert recorded == "UPDATE tasks SET background_id = '7c5dcf5d' WHERE id = 4"
    assert opened.startswith("INSERT INTO agent_runs")
    assert "'dispatcher', 'task-4', 'task-4'" in opened


def test_finishing_closes_the_task_and_its_run_with_the_same_line(database: Database) -> None:
    database.answers["UPDATE tasks SET finished_at"] = [{"id": 4}]
    task_queue.finish(4, " Opened PR #40 ", MOMENT)
    closed_task, closed_run = database.statements
    assert "outcome = 'Opened PR #40'" in closed_task
    assert "claimed_at IS NOT NULL AND finished_at IS NULL" in closed_task
    assert "'task #4', 'Opened PR #40'" in closed_run


def test_a_task_that_is_not_claimed_and_open_cannot_be_finished(database: Database) -> None:
    with pytest.raises(SystemExit, match="not claimed and open"):
        task_queue.finish(4, "done", MOMENT)
    assert len(database.statements) == 1


def test_a_task_cannot_be_finished_without_an_outcome(database: Database) -> None:
    with pytest.raises(SystemExit, match="outcome is needed"):
        task_queue.finish(4, "  ", MOMENT)
    assert database.statements == []


def test_a_refused_task_is_closed_without_a_dispatcher_run(database: Database) -> None:
    task_queue.refuse(4, "no agent is defined as 'nobody'", MOMENT)
    (statement,) = database.statements
    assert statement.startswith(f"UPDATE tasks SET finished_at = {AT}")
    assert "outcome = 'no agent is defined as ''nobody'''" in statement


def test_a_watcher_start_resets_its_start_and_a_poll_moves_only_last_seen(
    database: Database,
) -> None:
    task_queue.report_started("mac", MOMENT)
    task_queue.heartbeat("mac", MOMENT)
    started, polled = database.statements
    assert "ON CONFLICT (host) DO UPDATE SET started_at = excluded.started_at" in started
    assert polled == f"UPDATE dispatchers SET last_seen_at = {AT} WHERE host = 'mac'"
