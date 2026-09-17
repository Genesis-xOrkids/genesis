"""What a Claude Code session or subagent spent, read from its own transcript.

Claude Code writes every conversation as JSON lines, and each API response it
records carries the `usage` the API reported. One response spans several lines,
one per content block, that share its message id. Its input and cache counts are
final from its first line; its output count grows line by line and is final only
on the line that carries the response's stop reason. Each response is counted
once, from its last line. Lines whose model is `<synthetic>` are Claude Code's
own notices - an API error, an interruption - not calls, and are skipped.

A transcript does not always get a response's final line. Measured on 2026-09-16
across this Mac's transcripts, 341 of 22,730 responses had none - most of them
several tool calls at once - and their output stayed at the count streamed so
far: about 1.5% of all output. `partial_responses` counts them, so the gap is a
recorded fact beside the tokens rather than a silent undercount.

A transcript is also whole only a little after its run stops: the response that
ends a subagent is written after its `SubagentStop` hook has fired. So runs are
measured by the watcher once they have been finished a while
(`scripts/dispatch_watch.py`), never by the hook.

The tokens are facts. Cost is derived from them where it is read
(`scripts/agent_report.py`), with the price table the product uses, and never
stored. This module uses only the standard library, because the watcher and the
hooks run under a bare `python3`.

A transcript that cannot say what it cost raises `UnmeasuredError` with the
reason: it cannot be read, it holds no responses, it used more than one model
(its tokens would have no single price), or its cache writes are not split by
lifetime (a five-minute write and a one-hour write are priced differently).
Callers record the tokens as unknown and say why - never as zero.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import astuple, dataclass, fields
from typing import Any

SYNTHETIC = "<synthetic>"


class UnmeasuredError(Exception):
    """A transcript that cannot say what it cost; the message says why."""


@dataclass(frozen=True)
class Usage:
    """The tokens a run used, as its transcript recorded them, all on one model.

    `partial_responses` is how many responses never got their final line, whose
    output is counted as far as it streamed.
    """

    model: str
    input_tokens: int
    cache_creation_5m_input_tokens: int
    cache_creation_1h_input_tokens: int
    cache_read_input_tokens: int
    output_tokens: int
    partial_responses: int


COLUMNS = tuple(field.name for field in fields(Usage))


def read(transcript: pathlib.Path) -> Usage:
    """Sum the usage every response in a transcript recorded, each response once."""
    try:
        lines = transcript.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise UnmeasuredError(f"its transcript could not be read: {error}") from error

    responses: dict[str, tuple[str, dict[str, Any], bool]] = {}
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise UnmeasuredError(f"line {number} of its transcript is not JSON") from error
        message = entry.get("message") if isinstance(entry, dict) else None
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        usage, model, response_id = message.get("usage"), message.get("model"), message.get("id")
        if not isinstance(usage, dict) or model == SYNTHETIC:
            continue
        if not isinstance(model, str) or not isinstance(response_id, str):
            raise UnmeasuredError(
                f"line {number} of its transcript reports usage with no model or id"
            )
        responses[response_id] = (model, usage, message.get("stop_reason") is not None)

    if not responses:
        raise UnmeasuredError("its transcript holds no API responses")
    models = {model for model, _usage, _final in responses.values()}
    if len(models) > 1:
        raise UnmeasuredError(f"it used more than one model: {', '.join(sorted(models))}")

    totals = [0, 0, 0, 0, 0]
    for _model, usage, _final in responses.values():
        for index, count in enumerate(_counts(usage)):
            totals[index] += count
    partial = sum(1 for _model, _usage, final in responses.values() if not final)
    return Usage(models.pop(), *totals, partial)


def stored(row: dict[str, Any]) -> Usage | None:
    """The usage a database row records, or None when its tokens are unknown."""
    if row["model"] is None:
        return None
    return Usage(*(row[column] for column in COLUMNS))


def cells(usage: Usage | None) -> list[str]:
    """Usage as ledger cells, in `COLUMNS` order; unknown tokens are empty cells."""
    if usage is None:
        return [""] * len(COLUMNS)
    return [str(value) for value in astuple(usage)]


def _counts(usage: dict[str, Any]) -> tuple[int, int, int, int, int]:
    """One response's tokens, in `Usage` order after the model."""
    lifetimes = usage.get("cache_creation")
    if not isinstance(lifetimes, dict):
        raise UnmeasuredError("its cache writes are not split by lifetime")
    counts = (
        _count(usage.get("input_tokens")),
        _count(lifetimes.get("ephemeral_5m_input_tokens")),
        _count(lifetimes.get("ephemeral_1h_input_tokens")),
        _count(usage.get("cache_read_input_tokens")),
        _count(usage.get("output_tokens")),
    )
    if counts[1] + counts[2] != usage.get("cache_creation_input_tokens"):
        raise UnmeasuredError("its cache writes by lifetime do not add up to the writes reported")
    return counts


def _count(value: object) -> int:
    if not isinstance(value, int) or value < 0:
        raise UnmeasuredError(f"a response reports {value!r} where a token count belongs")
    return value
