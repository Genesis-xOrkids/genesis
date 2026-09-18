"""Tests for the git run ledger's one writer."""

from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib

import pytest

from scripts import log_agent_run, transcript_usage

SITE_BUILD = pathlib.Path(__file__).resolve().parents[2] / "second-brain/site/build.py"

RUN_AT = dt.datetime(2026, 9, 12, 14, 0, tzinfo=dt.UTC)


@pytest.fixture
def ledger(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "runs.tsv"
    monkeypatch.setattr(log_agent_run, "LEDGER", path)
    return path


def test_the_first_run_creates_the_ledger_with_its_header(ledger: pathlib.Path) -> None:
    usage = transcript_usage.Usage("claude-opus-5", 3, 0, 900, 500, 120, 1)
    _, new = log_agent_run.append("genesis-reviewer", "PR #12", "clean", RUN_AT, "a" * 40, usage)
    assert new
    assert ledger.read_text().splitlines() == [
        "run_at\tagent\ttarget\toutcome\tcommit_sha\tmodel\tinput_tokens"
        "\tcache_creation_5m_input_tokens\tcache_creation_1h_input_tokens"
        "\tcache_read_input_tokens\toutput_tokens\tpartial_responses",
        f"2026-09-12T14:00:00+00:00\tgenesis-reviewer\tPR #12\tclean\t{'a' * 40}"
        "\tclaude-opus-5\t3\t0\t900\t500\t120\t1",
    ]


def test_an_older_row_without_the_later_columns_still_keys_its_run(ledger: pathlib.Path) -> None:
    ledger.write_text(
        "run_at\tagent\ttarget\toutcome\n2026-09-12T14:00:00+00:00\tgenesis-reviewer\tPR #12\tclean\n"
    )
    _, new = log_agent_run.append("genesis-reviewer", "PR #12", "clean", RUN_AT, None, None)
    assert not new


def test_the_same_run_is_one_row_even_when_its_outcome_is_reworded(ledger: pathlib.Path) -> None:
    log_agent_run.append("genesis-reviewer", "PR #12", "clean", RUN_AT, None, None)
    _, new = log_agent_run.append("genesis-reviewer", "PR #12", "no findings", RUN_AT, None, None)
    assert not new
    assert len(ledger.read_text().splitlines()) == 2


def test_another_target_at_the_same_moment_is_another_run(ledger: pathlib.Path) -> None:
    log_agent_run.append("genesis-reviewer", "PR #12", "clean", RUN_AT, None, None)
    _, new = log_agent_run.append("genesis-reviewer", "PR #13", "clean", RUN_AT, None, None)
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
        log_agent_run.append("genesis-reviewer", target, "clean", run_at, None, None)
    assert not ledger.exists()


def test_the_site_reads_every_row_the_writer_writes_and_the_rows_before_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """The site build is the ledger's other reader; a row it refuses stops the deploy."""
    (tmp_path / ".claude").mkdir()
    monkeypatch.setattr(log_agent_run, "LEDGER", tmp_path / ".claude/runs.tsv")
    log_agent_run.append("genesis-reviewer", "PR #11", "clean", RUN_AT, None, None)
    usage = transcript_usage.Usage("claude-opus-5", 3, 0, 900, 500, 120, 1)
    later = RUN_AT.replace(hour=15)
    log_agent_run.append("genesis-reviewer", "PR #12", "1 blocking", later, "b" * 40, usage)
    written = log_agent_run.LEDGER.read_text().splitlines()
    # A row from before the commit and tokens were kept stops at the report.
    written.insert(1, "2026-09-11T10:00:00+00:00\treview\tPR #10\trelayed")
    log_agent_run.LEDGER.write_text("\n".join(written) + "\n")

    spec = importlib.util.spec_from_file_location("site_build", SITE_BUILD)
    assert spec is not None
    assert spec.loader is not None
    site_build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(site_build)
    monkeypatch.setattr(site_build, "REPO", tmp_path)

    assert [(run["agent"], run["what"]) for run in site_build.read_runs()] == [
        ("review", "PR #10 — relayed"),
        ("genesis-reviewer", "PR #11 — clean"),
        ("genesis-reviewer", "PR #12 — 1 blocking"),
    ]
