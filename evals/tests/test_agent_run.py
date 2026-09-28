"""Tests for running an agent over its eval cases, with the session stubbed."""

from __future__ import annotations

import json
import pathlib
import subprocess
import threading
import time

import pytest

from evals.agents import run, score
from scripts import transcript_usage


def _meeting(case: pathlib.Path) -> str:
    """A report that meets its case: the lowest blocking count and every citation."""
    _, expectation = score.load(case)
    cites = "\n".join(expectation.must_cite)
    return f"{cites}\nTarget: eval {case.name}\nOutcome: {expectation.blocking[0]} blocking, 0 design, 0 notes"


def _suite(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, *arguments: str) -> None:
    monkeypatch.setattr("sys.argv", ["run", "genesis-reviewer", *arguments])
    monkeypatch.setattr(run.tempfile, "mkdtemp", lambda **_: str(tmp_path))
    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(transcript_usage, "PROJECTS", tmp_path / "projects")


def _transcript(tmp_path: pathlib.Path, session_id: str, model: str) -> None:
    """A session's transcript: one response, 2k input, 200k cache read, 20k output."""
    project = tmp_path / "projects" / "-Users-ty-genesis"
    project.mkdir(exist_ok=True)
    response = {
        "id": f"msg_{session_id}",
        "role": "assistant",
        "model": model,
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 2_000,
            "cache_creation_input_tokens": 0,
            "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0},
            "cache_read_input_tokens": 200_000,
            "output_tokens": 20_000,
        },
    }
    (project / f"{session_id}.jsonl").write_text(json.dumps({"message": response}))


def test_a_suite_whose_reports_all_meet_their_cases_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    suite = run.SUITES / "genesis-reviewer"
    monkeypatch.setattr(
        run, "review", lambda _agent, case, _diff, _session_id: _meeting(suite / case)
    )
    _suite(monkeypatch, tmp_path)

    assert run.main() == 0
    out = capsys.readouterr().out
    assert "8/8 passed" in out
    assert (tmp_path / "jsonb-column.md").read_text() == _meeting(suite / "jsonb-column")


def test_one_miss_fails_the_suite_and_names_the_case(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    suite = run.SUITES / "genesis-reviewer"

    def review(_agent: str, case: str, _diff: str, _session_id: str) -> str:
        return "Outcome: no findings" if case == "stored-on-sale" else _meeting(suite / case)

    monkeypatch.setattr(run, "review", review)
    _suite(monkeypatch, tmp_path, "stored-on-sale", "clean-test-case")

    assert run.main() == 1
    out = capsys.readouterr().out
    assert "| clean-test-case | 0 | 0 blocking, 0 design | PASS |" in out
    assert (
        "| stored-on-sale | 1 to 3 | 0 blocking, 0 design | FAIL: 0 blocking, expected 1 to 3"
        in out
    )
    assert "1/2 passed" in out


def test_a_session_that_never_answers_fails_its_case_saying_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def review(_agent: str, _case: str, _diff: str, _session_id: str) -> str:
        raise subprocess.TimeoutExpired(cmd="claude", timeout=run.CASE_SECONDS)

    monkeypatch.setattr(run, "review", review)
    _suite(monkeypatch, tmp_path, "jsonb-column")

    assert run.main() == 1
    out = capsys.readouterr().out
    assert (
        f"| jsonb-column | 1 to 5 | no Outcome line | FAIL: no report within {run.CASE_SECONDS} seconds |"
        in out
    )


def test_a_session_that_exits_with_its_reason_on_stdout_fails_saying_why(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    limit = "You've hit your session limit"

    def review(_agent: str, _case: str, _diff: str, _session_id: str) -> str:
        raise subprocess.CalledProcessError(1, "claude", output=limit, stderr="")

    monkeypatch.setattr(run, "review", review)
    _suite(monkeypatch, tmp_path, "jsonb-column")

    assert run.main() == 1
    assert f"FAIL: the session exited 1: {limit} |" in capsys.readouterr().out


def test_an_unknown_case_name_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    _suite(monkeypatch, tmp_path, "no-such-case")

    with pytest.raises(SystemExit) as exit_info:
        run.main()
    assert exit_info.value.code == 2


def test_an_agent_with_no_suite_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["run", "storefront-scout"])

    with pytest.raises(SystemExit) as exit_info:
        run.main()
    assert exit_info.value.code == 2
    assert "storefront-scout has no eval suite" in capsys.readouterr().err


def test_the_agent_under_test_is_the_session_main_agent_and_sees_the_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert options["cwd"] == run.REPO
        assert options["timeout"] == run.CASE_SECONDS
        return subprocess.CompletedProcess(command, 0, stdout="Outcome: no findings", stderr="")

    monkeypatch.setattr(run.subprocess, "run", fake_run)

    report = run.review("genesis-reviewer", "jsonb-column", "+JSONB\n", "session-1")
    assert report == "Outcome: no findings"
    command = calls[0]
    assert command[:4] == ["claude", "-p", "--agent", "genesis-reviewer"]
    # The session is kept under a known id, so its transcript can be measured.
    assert command[command.index("--session-id") + 1] == "session-1"
    assert "--no-session-persistence" not in command
    assert "Target: eval jsonb-column" in command[-1]
    assert "+JSONB\n```" in command[-1]


def test_no_more_than_three_cases_run_at_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    suite = run.SUITES / "genesis-reviewer"
    lock = threading.Lock()
    running = [0]
    most = [0]

    def review(_agent: str, case: str, _diff: str, _session_id: str) -> str:
        with lock:
            running[0] += 1
            most[0] = max(most[0], running[0])
        time.sleep(0.05)
        with lock:
            running[0] -= 1
        return _meeting(suite / case)

    monkeypatch.setattr(run, "review", review)
    _suite(monkeypatch, tmp_path)

    assert run.main() == 0
    assert "8/8 passed" in capsys.readouterr().out
    assert most[0] == run.CASES_AT_ONCE == 3


def test_each_case_is_priced_from_its_sessions_transcript(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    suite = run.SUITES / "genesis-reviewer"

    def review(_agent: str, case: str, _diff: str, session_id: str) -> str:
        _transcript(tmp_path, session_id, "claude-opus-5")
        return _meeting(suite / case)

    monkeypatch.setattr(run, "review", review)
    _suite(monkeypatch, tmp_path, "jsonb-column", "clean-test-case")

    assert run.main() == 0
    out = capsys.readouterr().out
    # 2k input at $5, 200k cache read at $0.50, 20k output at $25, per million.
    assert "| PASS | $0.61 |" in out
    assert "Spent at list prices: $1.22." in out
    assert "Not in the total" not in out


def test_a_case_without_a_price_or_a_transcript_is_left_out_of_the_total_saying_why(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    suite = run.SUITES / "genesis-reviewer"

    def review(_agent: str, case: str, _diff: str, session_id: str) -> str:
        if case == "jsonb-column":
            _transcript(tmp_path, session_id, "claude-unpriced")
        return _meeting(suite / case)

    monkeypatch.setattr(run, "review", review)
    _suite(monkeypatch, tmp_path, "jsonb-column", "clean-test-case")

    assert run.main() == 0
    out = capsys.readouterr().out
    assert "| PASS | 20,000 out, 200,000 cache read; no price for claude-unpriced |" in out
    assert (
        "| clean-test-case | 0 | 0 blocking, 0 design | PASS | unknown: 0 transcripts found" in out
    )
    assert "Spent at list prices: $0.00." in out
    assert (
        "Not in the total: clean-test-case (tokens unknown), "
        "jsonb-column (no price for claude-unpriced)." in out
    )
