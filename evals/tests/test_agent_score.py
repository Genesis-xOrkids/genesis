"""Tests for the agent eval scorer, and for the seeded cases themselves."""

from __future__ import annotations

import pathlib

import pytest

from evals.agents import score

CASES = pathlib.Path(__file__).resolve().parents[1] / "agents" / "genesis-reviewer"
EXPECT = score.Expectation(blocking=(1, 3), design=None, must_cite=("No JSON/JSONB",))


def test_the_last_outcome_line_gives_the_counts() -> None:
    report = "Outcome: an earlier draft\n## Blocking\n\nTarget: eval x\nOutcome: 2 blocking, 1 design, 0 notes"
    assert score.outcome(report) == score.Counts(blocking=2, design=1)


def test_no_findings_is_none_of_either() -> None:
    assert score.outcome("Target: eval x\nOutcome: no findings") == score.Counts(
        blocking=0, design=0
    )


def test_markdown_emphasis_around_the_label_is_tolerated() -> None:
    assert score.outcome("**Outcome:** 1 blocking, 0 design, 0 notes") == score.Counts(1, 0)


def test_a_report_with_no_outcome_line_fails_as_unfinished() -> None:
    assert score.score("I could not reach the diff.", EXPECT) == [
        "the report has no Outcome line, so it is not a finished review"
    ]


def test_a_report_that_meets_its_case_passes() -> None:
    report = "Finding cites CLAUDE.md, No JSON/JSONB.\nOutcome: 1 blocking, 2 design, 0 notes"
    assert score.score(report, EXPECT) == []


def test_a_count_outside_the_expected_range_fails_with_both_numbers() -> None:
    report = "No JSON/JSONB.\nOutcome: 0 blocking, 0 design, 0 notes"
    assert score.score(report, EXPECT) == ["0 blocking, expected 1 to 3"]


def test_a_missing_citation_fails_by_name() -> None:
    assert score.score("Outcome: 1 blocking, 0 design, 0 notes", EXPECT) == [
        "does not cite 'No JSON/JSONB'"
    ]


def test_a_design_range_is_checked_only_when_the_case_gives_one() -> None:
    bounded = score.Expectation(blocking=(0, 0), design=(0, 1), must_cite=())
    assert score.score("Outcome: 0 blocking, 3 design, 0 notes", bounded) == [
        "3 design, expected 0 to 1"
    ]
    unbounded = score.Expectation(blocking=(0, 0), design=None, must_cite=())
    assert score.score("Outcome: 0 blocking, 3 design, 0 notes", unbounded) == []


@pytest.mark.parametrize(
    ("expect", "refusal"),
    [
        ('must_cite = ["x"]\n', "how many blocking findings"),
        ("blocking = [2, 1]\n", "low <= high"),
        ("blocking = [0, 0]\nseverity = 1\n", "fields nothing reads"),
    ],
    ids=["no blocking count", "an inverted range", "an unread field"],
)
def test_an_incomplete_case_is_refused(tmp_path: pathlib.Path, expect: str, refusal: str) -> None:
    (tmp_path / "diff.patch").write_text("diff --git a/x b/x\n")
    (tmp_path / "expect.toml").write_text(expect)
    with pytest.raises(ValueError, match=refusal):
        score.load(tmp_path)


def test_every_seeded_case_loads_and_the_set_is_five_violations_and_three_clean() -> None:
    cases = sorted(folder for folder in CASES.iterdir() if folder.is_dir())
    expectations = [score.load(case)[1] for case in cases]
    assert len(cases) == 8
    assert sum(1 for expectation in expectations if expectation.blocking[0] >= 1) == 5
    assert sum(1 for expectation in expectations if expectation.blocking == (0, 0)) == 3


def test_the_command_exits_non_zero_on_a_miss(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "report.md"
    report.write_text("Target: eval jsonb-column\nOutcome: 0 blocking, 0 design, 0 notes")
    monkeypatch.setattr("sys.argv", ["score", str(CASES / "jsonb-column"), str(report)])
    assert score.main() == 1
    assert "FAIL jsonb-column: 0 blocking, expected 1 to 5" in capsys.readouterr().out
