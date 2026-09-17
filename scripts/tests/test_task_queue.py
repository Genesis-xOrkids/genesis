"""Tests for the dispatch queue.

`query` is replaced by a stand-in that keeps the statements it was sent and
answers as D1 would, so nothing reaches the live database. The ledger a drain
writes is a file in a temporary directory.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from typing import Any

import pytest

from scripts import log_agent_run, task_queue, transcript_usage

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
    return stand_in


def test_a_claim_takes_the_oldest_pending_task_for_this_machine_in_one_statement(
    database: Database,
) -> None:
    claimed = {"id": 4, "request_id": "req-00000004", "text": "t", "assignee": None}
    database.answers["UPDATE tasks SET claimed_at"] = [claimed]
    assert task_queue.claim("mac", MOMENT) == claimed
    (statement,) = database.statements
    assert statement.startswith(f"UPDATE tasks SET claimed_at = {AT}, claimed_by = 'mac' ")
    assert "ORDER BY created_at, id LIMIT 1" in statement
    # Checked in the subquery and again on the row, so a task cancelled between
    # the two is not claimed.
    assert statement.count("claimed_at IS NULL AND cancelled_at IS NULL") == 2
    assert statement.endswith("RETURNING id, request_id, text, assignee")


@pytest.mark.usefixtures("database")
def test_nothing_waiting_claims_nothing() -> None:
    assert task_queue.claim("mac", MOMENT) is None


def test_a_session_is_recorded_once_and_never_replaced(database: Database) -> None:
    task_queue.started(4, "7c5dcf5d")
    assert database.statements == [
        "UPDATE tasks SET background_id = '7c5dcf5d' WHERE id = 4 AND background_id IS NULL"
    ]


def test_finishing_records_the_dispatchers_outcome_on_the_task_and_nowhere_else(
    database: Database,
) -> None:
    database.answers["UPDATE tasks SET finished_at"] = [{"id": 4}]
    task_queue.finish(4, " Opened PR #40 ", MOMENT)
    # One statement: the task is the dispatcher's run, so there is no copy to write.
    (statement,) = database.statements
    assert statement.startswith(f"UPDATE tasks SET finished_at = {AT}, outcome = 'Opened PR #40' ")
    assert statement.endswith(
        "AND claimed_at IS NOT NULL AND finished_at IS NULL AND closed_at IS NULL RETURNING id"
    )


def test_a_task_that_is_not_claimed_and_open_cannot_be_finished(database: Database) -> None:
    with pytest.raises(SystemExit, match="not claimed and open"):
        task_queue.finish(4, "done", MOMENT)
    assert len(database.statements) == 1


def test_a_task_cannot_be_finished_without_an_outcome(database: Database) -> None:
    with pytest.raises(SystemExit, match="outcome is needed"):
        task_queue.finish(4, "  ", MOMENT)
    assert database.statements == []


def test_closing_records_the_watchers_reason_and_never_an_outcome(database: Database) -> None:
    task_queue.close(4, "no agent is defined as 'nobody'", MOMENT)
    (statement,) = database.statements
    assert statement.startswith(
        f"UPDATE tasks SET closed_at = {AT}, closed_reason = 'no agent is defined as ''nobody''' "
    )
    assert "outcome" not in statement
    assert statement.endswith("WHERE id = 4 AND finished_at IS NULL AND closed_at IS NULL")


def test_a_watcher_sees_only_the_open_tasks_it_claimed(database: Database) -> None:
    task_queue.open_tasks("mac")
    (statement,) = database.statements
    assert statement.startswith("SELECT id, request_id, background_id FROM tasks")
    assert "WHERE claimed_by = 'mac' AND finished_at IS NULL AND closed_at IS NULL" in statement


def test_which_tasks_are_still_open_is_asked_in_one_statement(database: Database) -> None:
    database.answers["SELECT request_id FROM tasks"] = [{"request_id": "req-00000005"}]
    assert task_queue.still_open(["req-00000004", "req-00000005"]) == {"req-00000005"}
    (statement,) = database.statements
    assert "WHERE request_id IN ('req-00000004','req-00000005') " in statement
    assert statement.endswith("AND finished_at IS NULL AND closed_at IS NULL")


def test_the_tasks_to_measure_are_the_ended_ones_whose_spend_is_unknown(
    database: Database,
) -> None:
    database.answers["SELECT id, request_id, background_id FROM tasks WHERE request_id"] = [
        {"id": 5, "request_id": "req-00000005", "background_id": "s5"}
    ]
    assert task_queue.unmeasured(["req-00000005"]) == [
        {"id": 5, "request_id": "req-00000005", "background_id": "s5"}
    ]
    assert task_queue.unmeasured([]) == []
    (statement,) = database.statements
    assert statement.endswith(
        "AND (finished_at IS NOT NULL OR closed_at IS NOT NULL) AND model IS NULL"
    )


def test_a_measurement_is_written_once_and_never_over_another(database: Database) -> None:
    task_queue.measured(5, transcript_usage.Usage("claude-sonnet-5", 10, 0, 2000, 8000, 400, 0))
    assert database.statements == [
        "UPDATE tasks SET model = 'claude-sonnet-5', input_tokens = 10, "
        "cache_creation_5m_input_tokens = 0, cache_creation_1h_input_tokens = 2000, "
        "cache_read_input_tokens = 8000, output_tokens = 400, partial_responses = 0 "
        "WHERE id = 5 AND model IS NULL"
    ]


def test_asking_about_no_tasks_asks_nothing(database: Database) -> None:
    assert task_queue.still_open([]) == set()
    assert database.statements == []


SPENT = dict(
    zip(transcript_usage.COLUMNS, ("claude-sonnet-5", 10, 0, 2000, 8000, 400, 0), strict=True)
)
TASK_RUNS = [
    {"id": 12, "outcome": "Opened PR #40", "finished_at": "2026-09-12T02:50:00+00:00", **SPENT},
    {
        "id": 13,
        "outcome": "Reviewed PR #41",
        "finished_at": "2026-09-12T02:55:00+00:00",
        **dict.fromkeys(transcript_usage.COLUMNS),
    },
]
TASK_RUNS_SELECT = "SELECT id, outcome, finished_at, model, "


def test_finished_tasks_are_ledgered_as_dispatcher_runs_without_marking(
    database: Database, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    ledger = tmp_path / "runs.tsv"
    monkeypatch.setattr(log_agent_run, "LEDGER", ledger)
    database.answers[TASK_RUNS_SELECT] = TASK_RUNS[:1]
    assert task_queue.ledger() == 1
    # The same task again, as after a run that failed before marking it.
    assert task_queue.ledger() == 1
    assert ledger.read_text().splitlines() == [
        "\t".join(log_agent_run.COLUMNS),
        # A task names no commit; its session's tokens are the watcher's measurement.
        "2026-09-12T02:50:00+00:00\tdispatcher\ttask #12\tOpened PR #40\t"
        "\tclaude-sonnet-5\t10\t0\t2000\t8000\t400\t0",
    ]
    select = next(sql for sql in database.statements if sql.startswith("SELECT"))
    # Finished only: a closed task has no report to ledger.
    assert "WHERE finished_at IS NOT NULL AND ledgered_at IS NULL" in select
    assert [sql for sql in database.statements if sql.startswith("UPDATE")] == []


def test_only_tasks_the_ledger_holds_are_marked(database: Database) -> None:
    database.answers[TASK_RUNS_SELECT] = TASK_RUNS
    held = {("2026-09-12T02:50:00+00:00", "dispatcher", "task #12")}
    assert task_queue.mark(MOMENT, held) == 1
    assert [sql for sql in database.statements if sql.startswith("UPDATE")] == [
        f"UPDATE tasks SET ledgered_at = {AT} WHERE id IN (12)"
    ]


def test_a_watcher_start_resets_its_start_and_a_poll_moves_only_last_seen(
    database: Database,
) -> None:
    task_queue.report_started("mac", MOMENT)
    task_queue.heartbeat("mac", MOMENT)
    started, polled = database.statements
    assert "ON CONFLICT (host) DO UPDATE SET started_at = excluded.started_at" in started
    assert polled == f"UPDATE dispatchers SET last_seen_at = {AT} WHERE host = 'mac'"
