"""Tests for the report of what each agent has cost.

`query` is replaced by a stand-in that answers the two statements the report
sends, so nothing reaches the live database.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts import agent_report


def row(agent: str, model: str | None, runs: int, *tokens: int) -> dict[str, Any]:
    spent = (
        dict(zip(agent_report.TOKENS, tokens, strict=True))
        if model
        else dict.fromkeys(agent_report.TOKENS)
    )
    return {
        "agent": agent,
        "model": model,
        "runs": runs,
        "reported": runs,
        "measured": runs if model else 0,
        **spent,
    }


def answer(
    monkeypatch: pytest.MonkeyPatch, runs: list[dict[str, Any]], tasks: list[dict[str, Any]]
) -> list[str]:
    statements: list[str] = []

    def query(sql: str) -> list[dict[str, Any]]:
        statements.append(sql)
        return runs if "FROM agent_runs" in sql else tasks

    monkeypatch.setattr(agent_report, "query", query)
    return statements


def test_known_tokens_are_priced_and_unknown_ones_are_counted_but_left_out(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    statements = answer(
        monkeypatch,
        runs=[
            # 1M uncached input and 1M output on Opus 5: $5 + $25.
            row("genesis-reviewer", "claude-opus-5", 2, 1_000_000, 0, 0, 0, 1_000_000),
            row("genesis-reviewer", None, 3),
        ],
        # 1M one-hour cache writes on Sonnet 5, at twice its $2 input: $4.
        tasks=[row("dispatcher", "claude-sonnet-5", 1, 0, 0, 1_000_000, 0, 0)],
    )
    assert agent_report.main() == 0
    lines = capsys.readouterr().out.splitlines()

    assert (
        "| genesis-reviewer | claude-opus-5 | 2 | 2 | 2 | 1,000,000 | 0 | 0 | 0 | 1,000,000 | $30.00 |"
        in lines
    )
    assert "| genesis-reviewer | unknown | 3 | 3 | 0 | - | - | - | - | - | - |" in lines
    assert (
        "| dispatcher | claude-sonnet-5 | 1 | 1 | 1 | 0 | 0 | 1,000,000 | 0 | 0 | $4.00 |" in lines
    )
    assert lines[-2:] == [
        "Total at list prices: $34.00.",
        "Not in the total: 3 runs with unknown tokens.",
    ]
    # The sums are the database's: nothing is added up here but the prices.
    assert all("GROUP BY" in sql and "SUM(output_tokens)" in sql for sql in statements)


def test_a_model_with_no_price_is_named_rather_than_priced_at_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer(
        monkeypatch, runs=[row("genesis-reviewer", "claude-fable-5-1", 1, 5, 0, 0, 0, 5)], tasks=[]
    )
    report = agent_report.report(agent_report.query(agent_report.AGENT_RUNS))
    assert "| no price for claude-fable-5-1 |" in report
    assert report.endswith(
        "Total at list prices: $0.00.\nNot in the total: 1 run on a model with no price."
    )


def test_nothing_recorded_says_so() -> None:
    assert agent_report.report([]) == "No finished runs are recorded yet."
