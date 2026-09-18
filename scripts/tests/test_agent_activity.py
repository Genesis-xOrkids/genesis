"""Tests for the live agent activity recorder.

Nothing here reaches D1 or GitHub. `query` is replaced by a stand-in that keeps
the statements it was sent and answers the way D1 would, and `gh` is replaced by
a stand-in for `subprocess.run`, so a test can never write to the live activity
table or comment on a real pull request.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import pathlib
import subprocess
from typing import Any

import pytest

from scripts import agent_activity, brain_db, log_agent_run, transcript_usage

MOMENT = dt.datetime(2026, 9, 12, 14, 30, 5, tzinfo=dt.UTC)
EMPLOYEES = {"genesis-reviewer", "review"}
REPORT = "## Blocking\n### 1. something\n\nTarget: PR #12\nOutcome: 1 blocking, 0 design, 0 notes"


class Database:
    """Stands in for `brain_db.query`: records statements, answers as D1 would.

    `closes` is what an upsert's `RETURNING id` yields - one row when the stop
    closed the run, none when the run was already closed.
    """

    def __init__(self, closes: bool = True, rows: list[dict[str, Any]] | None = None) -> None:
        self.statements: list[str] = []
        self.closes = closes
        self.rows = rows or []

    def __call__(self, sql: str) -> list[dict[str, Any]]:
        self.statements.append(sql)
        if sql.startswith("SELECT"):
            return self.rows
        if "RETURNING" in sql:
            return [{"id": 1}] if self.closes else []
        return []


class GitHub:
    """Stands in for `subprocess.run` when it runs `gh`."""

    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.calls: list[tuple[list[str], str]] = []
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs["input"]))
        return subprocess.CompletedProcess(command, self.returncode, stdout="", stderr=self.stderr)


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Database:
    stand_in = Database()
    monkeypatch.setattr(agent_activity, "query", stand_in)
    return stand_in


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> GitHub:
    stand_in = GitHub()
    monkeypatch.setattr(agent_activity.subprocess, "run", stand_in)
    return stand_in


@pytest.fixture(autouse=True)
def markers(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    folder = tmp_path / "markers"
    monkeypatch.setattr(agent_activity, "MARKERS", folder)
    return folder


def stop(message: str, agent: str = "genesis-reviewer") -> dict[str, Any]:
    return {
        "hook_event_name": "SubagentStop",
        "session_id": "session-1",
        "agent_id": "agent-1",
        "agent_type": agent,
        "last_assistant_message": message,
    }


# --- reading the report ---


def test_the_last_target_and_outcome_lines_are_the_report() -> None:
    message = "Target: an earlier mention\n" + REPORT
    assert agent_activity.report_field(message, "Target") == "PR #12"
    assert agent_activity.report_field(message, "Outcome") == "1 blocking, 0 design, 0 notes"


def test_markdown_emphasis_around_the_labels_is_tolerated() -> None:
    message = "report body\n**Target:** branch search-precision\n**Outcome:** no findings"
    assert agent_activity.report_field(message, "Target") == "branch search-precision"
    assert agent_activity.report_field(message, "Outcome") == "no findings"


# --- who is recorded ---


def test_a_built_in_agent_is_not_an_employee_and_touches_nothing(
    database: Database, github: GitHub
) -> None:
    said = agent_activity.hook(stop(REPORT, agent="Explore"), EMPLOYEES, MOMENT)
    assert said is None
    assert database.statements == []
    assert github.calls == []


def test_a_start_opens_the_run_and_marks_its_session(
    database: Database, markers: pathlib.Path
) -> None:
    event = {**stop(""), "hook_event_name": "SubagentStart"}
    del event["last_assistant_message"]
    assert agent_activity.hook(event, EMPLOYEES, MOMENT) is None
    (statement,) = database.statements
    assert statement.startswith("INSERT INTO agent_runs")
    assert "'2026-09-12T14:30:05+00:00'" in statement
    assert "WHERE agent_runs.started_at IS NULL" in statement
    assert (markers / "session-1").exists()


# --- a stop, and the pull request ---


def test_a_pr_review_is_recorded_and_posted_as_a_comment_on_that_pr(
    database: Database, github: GitHub
) -> None:
    said = agent_activity.hook(stop(REPORT), EMPLOYEES, MOMENT)
    assert said is not None
    assert "report posted to PR #12" in said
    (statement,) = database.statements
    assert "'PR #12'" in statement
    assert "'1 blocking, 0 design, 0 notes'" in statement
    ((command, _),) = github.calls
    assert command == ["gh", "pr", "comment", "12", "--body-file", "-"]


@pytest.mark.usefixtures("database")
def test_the_comment_carries_the_findings_not_just_the_outcome(github: GitHub) -> None:
    agent_activity.hook(stop(REPORT), EMPLOYEES, MOMENT)
    ((_, body),) = github.calls
    assert body.startswith("🤖 **genesis-reviewer** — 1 blocking, 0 design, 0 notes")
    assert "### 1. something" in body


@pytest.mark.parametrize(
    "target",
    ["branch search-precision", "main (c0e8ec4..HEAD, 3 commits)"],
    ids=["a branch review", "a review of main over a range"],
)
@pytest.mark.usefixtures("database")
def test_a_target_with_no_pull_request_posts_nothing(github: GitHub, target: str) -> None:
    said = agent_activity.hook(
        stop(f"report\nTarget: {target}\nOutcome: no findings"), EMPLOYEES, MOMENT
    )
    assert said is not None
    assert said.startswith(f"genesis-reviewer run recorded: {target} - no findings")
    assert github.calls == []


@pytest.mark.parametrize(
    "message",
    ["Tools available: Read, Glob, Grep, Bash", "Target: PR #12"],
    ids=["a diagnostic with no closing lines", "a target without an outcome"],
)
def test_a_stop_without_a_report_is_closed_as_ending_without_one(
    database: Database, github: GitHub, message: str
) -> None:
    said = agent_activity.hook(stop(message), EMPLOYEES, MOMENT)
    assert said is not None
    assert "ending without a report" in said
    (statement,) = database.statements
    assert "NULL" in statement
    assert github.calls == []


@pytest.mark.usefixtures("github")
def test_a_stop_records_the_commit_it_saw_and_leaves_what_it_spent_to_the_watcher(
    database: Database,
) -> None:
    commit = "0123456789abcdef0123456789abcdef01234567"
    report = f"Target: PR #12\nCommit: {commit}\nOutcome: 0 blocking, 0 design, 0 notes"
    said = agent_activity.hook(stop(report), EMPLOYEES, MOMENT)
    assert said is not None
    assert "not a full commit id" not in said
    (statement,) = database.statements
    assert f"'PR #12', '0 blocking, 0 design, 0 notes', '{commit}')" in statement
    assert "commit_sha = excluded.commit_sha" in statement
    # The response that ends a run reaches its transcript after the stop.
    assert "output_tokens" not in statement


@pytest.mark.usefixtures("github")
def test_a_commit_line_that_is_not_a_full_commit_id_is_recorded_unknown_and_said(
    database: Database,
) -> None:
    report = "Target: PR #12\nCommit: 0123abc\nOutcome: 0 blocking, 0 design, 0 notes"
    said = agent_activity.hook(stop(report), EMPLOYEES, MOMENT)
    assert said is not None
    assert "its Commit line '0123abc' is not a full commit id" in said
    (statement,) = database.statements
    assert "'0 blocking, 0 design, 0 notes', NULL)" in statement


def test_runs_are_measured_once_settled_within_a_day_and_never_a_commands(
    database: Database,
) -> None:
    agent_activity.unmeasured(MOMENT)
    (asked,) = database.statements
    assert "WHERE model IS NULL AND finished_at < '2026-09-12T14:29:05+00:00'" in asked
    assert "AND finished_at > '2026-09-11T14:30:05+00:00'" in asked
    assert asked.endswith("AND agent_id NOT LIKE '%@%'")

    agent_activity.measured(7, transcript_usage.Usage("claude-opus-5", 3, 0, 900, 500, 120, 1))
    assert database.statements[-1] == (
        "UPDATE agent_runs SET model = 'claude-opus-5', input_tokens = 3, "
        "cache_creation_5m_input_tokens = 0, cache_creation_1h_input_tokens = 900, "
        "cache_read_input_tokens = 500, output_tokens = 120, partial_responses = 1 "
        "WHERE id = 7 AND model IS NULL AND ledgered_at IS NULL"
    )


def test_a_repeated_stop_is_not_posted_twice(database: Database, github: GitHub) -> None:
    database.closes = False
    said = agent_activity.hook(stop(REPORT), EMPLOYEES, MOMENT)
    assert said == "genesis-reviewer run was already recorded"
    assert github.calls == []


def test_a_failed_post_is_reported_and_the_run_is_still_recorded(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agent_activity.subprocess, "run", GitHub(returncode=1, stderr="gh: not authenticated")
    )
    said = agent_activity.hook(stop(REPORT), EMPLOYEES, MOMENT)
    assert said is not None
    assert "could NOT be posted to PR #12: gh: not authenticated" in said
    assert len(database.statements) == 1


def test_a_writer_failure_is_reported_and_nothing_is_posted(
    monkeypatch: pytest.MonkeyPatch, github: GitHub, capsys: pytest.CaptureFixture[str]
) -> None:
    def unreachable(_sql: str) -> list[dict[str, Any]]:
        raise SystemExit("wrangler did not answer within 60s")

    monkeypatch.setattr(agent_activity, "query", unreachable)
    monkeypatch.setattr(agent_activity, "defined_ids", lambda _repo: EMPLOYEES)
    monkeypatch.setattr("sys.argv", ["agent_activity", "hook"])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stop(REPORT))))
    assert agent_activity.main() == 0
    said = json.loads(capsys.readouterr().out)["systemMessage"]
    assert "could not be recorded: wrangler did not answer within 60s" in said
    assert github.calls == []


# --- sessions ending ---


def test_a_session_that_opened_no_run_ends_without_reaching_the_database(
    database: Database,
) -> None:
    event = {"hook_event_name": "SessionEnd", "session_id": "session-1"}
    assert agent_activity.hook(event, EMPLOYEES, MOMENT) is None
    assert database.statements == []


def test_a_session_that_opened_a_run_closes_what_it_left_open(
    database: Database, markers: pathlib.Path
) -> None:
    markers.mkdir()
    (markers / "session-1").touch()
    agent_activity.hook(
        {"hook_event_name": "SessionEnd", "session_id": "session-1"}, EMPLOYEES, MOMENT
    )
    (statement,) = database.statements
    assert statement.startswith("UPDATE agent_runs SET finished_at = '2026-09-12T14:30:05+00:00'")
    assert "AND finished_at IS NULL" in statement
    assert not (markers / "session-1").exists()


# --- commands, and the ledger ---


def test_a_command_run_is_keyed_by_the_moment_it_was_recorded(database: Database) -> None:
    agent_activity.record(
        "review", "session-1", "PR #12", "relayed the genesis-reviewer report", MOMENT
    )
    opened, closed = database.statements
    assert "'review@2026-09-12T14:30:05+00:00'" in opened
    assert "'review@2026-09-12T14:30:05+00:00'" in closed
    assert "'PR #12'" in closed


UNKNOWN_SPEND = dict.fromkeys(transcript_usage.COLUMNS)
REVIEW_RUN = {
    "id": 7,
    "agent": "genesis-reviewer",
    "target": "PR #12",
    "outcome": "clean",
    "finished_at": "2026-09-12T14:00:00+00:00",
    "commit_sha": "a" * 40,
    **dict(zip(transcript_usage.COLUMNS, ("claude-opus-5", 3, 0, 900, 500, 120, 1), strict=True)),
}
COMMAND_RUN = {
    "id": 8,
    "agent": "review",
    "target": "PR #12",
    "outcome": "relayed",
    "finished_at": "2026-09-12T14:01:00+00:00",
    "commit_sha": None,
    **UNKNOWN_SPEND,
}
HEADER = "\t".join(log_agent_run.COLUMNS)


def test_the_ledger_is_written_without_marking_and_again_harmlessly(
    database: Database, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    ledger = tmp_path / "runs.tsv"
    monkeypatch.setattr(log_agent_run, "LEDGER", ledger)
    monkeypatch.setattr(agent_activity.task_queue, "ledger", lambda _moment: 0)
    database.rows = [REVIEW_RUN, COMMAND_RUN]
    assert agent_activity.ledger(MOMENT) == 2
    # The same rows again, as after a run that failed before marking them.
    assert agent_activity.ledger(MOMENT) == 2
    assert ledger.read_text().splitlines() == [
        HEADER,
        f"2026-09-12T14:00:00+00:00\tgenesis-reviewer\tPR #12\tclean\t{'a' * 40}"
        "\tclaude-opus-5\t3\t0\t900\t500\t120\t1",
        # A command's tokens and commit are unknown: empty cells, never zeros.
        "2026-09-12T14:01:00+00:00\treview\tPR #12\trelayed" + "\t" * 8,
    ]
    assert [sql for sql in database.statements if sql.startswith("UPDATE")] == []
    # A reported run whose spend is still worth measuring is left for the next drain.
    asked = next(sql for sql in database.statements if sql.startswith("SELECT"))
    assert "AND (model IS NOT NULL OR agent_id LIKE '%@%' " in asked
    assert "OR finished_at < '2026-09-11T14:30:05+00:00')" in asked


def test_only_runs_the_ledger_holds_are_marked(
    database: Database, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    ledger = tmp_path / "runs.tsv"
    ledger.write_text(HEADER + "\n2026-09-12T14:00:00+00:00\tgenesis-reviewer\tPR #12\tclean\n")
    monkeypatch.setattr(log_agent_run, "LEDGER", ledger)
    monkeypatch.setattr(agent_activity, "LEDGER", ledger)
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    held_by_queue: list[set[tuple[str, str, str]]] = []
    monkeypatch.setattr(
        agent_activity.task_queue, "mark", lambda _moment, held: held_by_queue.append(held) or 0
    )
    # Run 8 finished after the ledger was written, so it stays for the next pass.
    database.rows = [REVIEW_RUN, COMMAND_RUN]
    assert agent_activity.mark(MOMENT) == 1
    assert [sql for sql in database.statements if sql.startswith("UPDATE")] == [
        "UPDATE agent_runs SET ledgered_at = '2026-09-12T14:30:05+00:00' WHERE id IN (7)"
    ]
    assert held_by_queue == [{("2026-09-12T14:00:00+00:00", "genesis-reviewer", "PR #12")}]


def test_marking_waits_for_the_ledger_to_be_pushed(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(_path: pathlib.Path) -> None:
        raise SystemExit(
            "runs.tsv has changes that are not committed; commit and push it before marking"
        )

    monkeypatch.setattr(agent_activity, "require_pushed", refuse)
    with pytest.raises(SystemExit, match="not committed"):
        agent_activity.mark(MOMENT)
    assert database.statements == []


def test_ledger_and_mark_include_the_dispatch_queue(
    database: Database, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(log_agent_run, "LEDGER", tmp_path / "runs.tsv")
    monkeypatch.setattr(agent_activity, "LEDGER", tmp_path / "runs.tsv")
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.setattr(agent_activity.task_queue, "ledger", lambda _moment: 3)
    monkeypatch.setattr(agent_activity.task_queue, "mark", lambda _moment, _held: 2)
    assert agent_activity.ledger(MOMENT) == 3
    assert agent_activity.mark(MOMENT) == 2
    assert database.statements[-1].startswith("SELECT")


def test_the_session_end_hook_has_as_long_as_one_statement_is_allowed() -> None:
    """SessionEnd hooks share a 1.5 second budget unless a hook sets its own timeout.

    A wrangler call takes several seconds, so without one the hook is cancelled
    on exit and the runs it should close stay open - which is what the first live
    run showed. The hook gets as long as the adapter gives any one statement.
    """
    settings = json.loads((agent_activity.REPO / ".claude/settings.json").read_text())
    (entry,) = settings["hooks"]["SessionEnd"]
    (hook,) = entry["hooks"]
    assert hook["timeout"] >= brain_db.TIMEOUT_SECONDS
