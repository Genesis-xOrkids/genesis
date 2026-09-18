"""What each agent has cost, from the runs the hooks recorded.

    uv run python -m scripts.agent_report

The watcher records the tokens each agent run and each dispatched task's session
spent, from their transcripts (`scripts/dispatch_watch.py`). This sums them in the
database and prices the sums with the product's own price table, so an agent's
cost and a model call's cost come from one list of prices. That table's package
loads the gateway and its dependencies, which is why this runs under `uv`, while
the watcher and the hooks, which run under a bare `python3`, never import it.

Prices are list rates; on a subscription the dollars are relative weight, not a
bill. A run whose tokens are unknown is counted but not priced, and neither is a
run on a model the table has no price for: the report says how many of each there
were rather than pricing them at zero. Output is counted as far as each response's
transcript recorded it, so where a response never got its final count the report
says how many, and the output beside it is a lower bound.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from typing import Any

from intelligence.model_gateway.pricing import UnknownModelError, cost_usd
from scripts import task_queue, transcript_usage
from scripts.brain_db import query

# Every count a transcript measures: the tokens, then the responses left partial.
COUNTS = transcript_usage.COLUMNS[1:]
SUMS = (
    "COUNT(*) AS runs, SUM(outcome IS NOT NULL) AS reported, SUM(model IS NOT NULL) AS measured, "
    + ", ".join(f"SUM({column}) AS {column}" for column in COUNTS)
)
AGENT_RUNS = (
    f"SELECT agent, model, {SUMS} FROM agent_runs WHERE finished_at IS NOT NULL "
    "GROUP BY agent, model ORDER BY agent, model"
)
# A dispatched task is its dispatcher's run, ended when it was finished or closed.
TASKS = (
    f"SELECT '{task_queue.DISPATCHER}' AS agent, model, {SUMS} FROM tasks "
    "WHERE finished_at IS NOT NULL OR closed_at IS NOT NULL GROUP BY model ORDER BY model"
)
HEADER = (
    "Agent",
    "Model",
    "Runs",
    "Reported",
    "Tokens known",
    "Input",
    "Cache writes, 5 min",
    "Cache writes, 1 hour",
    "Cache reads",
    "Output",
    "Partial responses",
    "Cost at list price",
)


def price(row: dict[str, Any]) -> Decimal:
    """What one agent's runs on one model cost. Raises `UnknownModelError` for an unpriced model."""
    return cost_usd(
        row["model"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        cache_read_tokens=row["cache_read_input_tokens"],
        cache_write_tokens=row["cache_creation_5m_input_tokens"],
        cache_write_1h_tokens=row["cache_creation_1h_input_tokens"],
    )


def report(rows: list[dict[str, Any]]) -> str:
    """A markdown table, one row per agent and model, and what its total leaves out."""
    if not rows:
        return "No finished runs are recorded yet."
    lines = ["| " + " | ".join(HEADER) + " |", "|" + "---|" * len(HEADER)]
    total, unknown, unpriced, partial = Decimal(0), 0, 0, 0
    for row in rows:
        if row["model"] is None:
            unknown += row["runs"]
            cells = [row["agent"], "unknown", *_counts(row, 3), *["-"] * len(COUNTS), "-"]
        else:
            try:
                cost = price(row)
            except UnknownModelError:
                unpriced += row["measured"]
                spent = f"no price for {row['model']}"
            else:
                total += cost
                spent = f"${cost:,.2f}"
            partial += row["partial_responses"]
            cells = [row["agent"], row["model"], *_counts(row, 3 + len(COUNTS)), spent]
        lines.append("| " + " | ".join(cells) + " |")

    left_out = [
        f"{count} run{'' if count == 1 else 's'} {why}"
        for count, why in ((unknown, "with unknown tokens"), (unpriced, "on a model with no price"))
        if count
    ]
    lines += ["", f"Total at list prices: ${total:,.2f}."]
    if left_out:
        lines.append(f"Not in the total: {', '.join(left_out)}.")
    if partial:
        lines.append(
            f"Output is a lower bound: {partial:,} response{'' if partial == 1 else 's'} "
            "never got a final count in their transcript."
        )
    return "\n".join(lines)


def _counts(row: dict[str, Any], how_many: int) -> list[str]:
    """The row's counts after agent and model, in `HEADER` order, with thousands separated."""
    columns = ("runs", "reported", "measured", *COUNTS)[:how_many]
    return [f"{row[column]:,}" for column in columns]


def main() -> int:
    print(report(query(AGENT_RUNS) + query(TASKS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
