"""Tests for the git run ledger's one writer."""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest

from scripts import log_agent_run

RUN_AT = dt.datetime(2026, 9, 12, 14, 0, tzinfo=dt.UTC)


@pytest.fixture
def ledger(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "runs.tsv"
    monkeypatch.setattr(log_agent_run, "LEDGER", path)
    return path


def test_the_first_run_creates_the_ledger_with_its_header(ledger: pathlib.Path) -> None:
    _, new = log_agent_run.append("genesis-reviewer", "PR #12", "clean", RUN_AT)
    assert new
    assert ledger.read_text().splitlines() == [
        "run_at\tagent\ttarget\toutcome",
        "2026-09-12T14:00:00+00:00\tgenesis-reviewer\tPR #12\tclean",
    ]


def test_the_same_run_is_one_row_even_when_its_outcome_is_reworded(ledger: pathlib.Path) -> None:
    log_agent_run.append("genesis-reviewer", "PR #12", "clean", RUN_AT)
    _, new = log_agent_run.append("genesis-reviewer", "PR #12", "no findings", RUN_AT)
    assert not new
    assert len(ledger.read_text().splitlines()) == 2


def test_another_target_at_the_same_moment_is_another_run(ledger: pathlib.Path) -> None:
    log_agent_run.append("genesis-reviewer", "PR #12", "clean", RUN_AT)
    _, new = log_agent_run.append("genesis-reviewer", "PR #13", "clean", RUN_AT)
    assert new
    assert len(ledger.read_text().splitlines()) == 3


@pytest.mark.parametrize(
    ("target", "run_at", "refusal"),
    [
        ("", RUN_AT, "target is empty"),
        ("PR #12\tsplit", RUN_AT, "tab or newline"),
        ("PR #12", dt.datetime(2026, 9, 12, 14, 0), "no timezone"),  # noqa: DTZ001 - the refusal under test
    ],
    ids=["an empty target", "a tab in the target", "a time with no zone"],
)
def test_a_row_that_would_corrupt_the_ledger_is_refused(
    ledger: pathlib.Path, target: str, run_at: dt.datetime, refusal: str
) -> None:
    with pytest.raises(SystemExit, match=refusal):
        log_agent_run.append("genesis-reviewer", target, "clean", run_at)
    assert not ledger.exists()
