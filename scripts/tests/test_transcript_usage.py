"""Tests for reading what a session or subagent spent from its transcript.

Each transcript here is written to a temporary file in the shape Claude Code
writes: one JSON object per line, a response spread over several lines that share
its message id, and `<synthetic>` notices beside the real responses.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from scripts import transcript_usage
from scripts.transcript_usage import UnmeasuredError, Usage


def response(
    response_id: str,
    output_tokens: int,
    *,
    model: str = "claude-opus-5",
    input_tokens: int = 2,
    written_5m: int = 0,
    written_1h: int = 0,
    read: int = 0,
    stop_reason: str | None = "tool_use",
) -> dict[str, Any]:
    return {
        "type": "assistant",
        "message": {
            "id": response_id,
            "role": "assistant",
            "model": model,
            "stop_reason": stop_reason,
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": written_5m + written_1h,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": written_5m,
                    "ephemeral_1h_input_tokens": written_1h,
                },
                "cache_read_input_tokens": read,
                "output_tokens": output_tokens,
            },
        },
    }


def transcript(tmp_path: pathlib.Path, *entries: dict[str, Any] | str) -> pathlib.Path:
    path = tmp_path / "agent-a1.jsonl"
    path.write_text(
        "\n".join(entry if isinstance(entry, str) else json.dumps(entry) for entry in entries)
        + "\n"
    )
    return path


def test_each_response_is_counted_once_from_its_last_line(tmp_path: pathlib.Path) -> None:
    path = transcript(
        tmp_path,
        {"type": "user", "message": {"role": "user", "content": "review this"}},
        # One response over two lines: the first carries a streaming count.
        response("msg_1", 1, written_5m=1000, stop_reason=None),
        response("msg_1", 250, written_5m=1000),
        response("msg_2", 80, written_1h=40, read=1000),
        # One whose final line never came: its output is counted as far as it
        # streamed, and the response is counted as partial.
        response("msg_4", 6, read=1000, stop_reason=None),
        response("msg_4", 6, read=1000, stop_reason=None),
        {
            "type": "assistant",
            "message": {
                "id": "msg_3",
                "role": "assistant",
                "model": "<synthetic>",
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        },
    )
    assert transcript_usage.read(path) == Usage("claude-opus-5", 6, 1000, 40, 2000, 336, 1)


@pytest.mark.parametrize(
    ("entries", "reason"),
    [
        ([], "holds no API responses"),
        (
            [response("msg_1", 5), response("msg_2", 5, model="claude-sonnet-5")],
            "more than one model: claude-opus-5, claude-sonnet-5",
        ),
        (['{"type": "assistant", "message": {'], "line 1 of its transcript is not JSON"),
    ],
    ids=["no responses", "two models", "a line that is not JSON"],
)
def test_a_transcript_that_cannot_say_what_it_cost_says_why(
    tmp_path: pathlib.Path, entries: list[dict[str, Any] | str], reason: str
) -> None:
    with pytest.raises(UnmeasuredError, match=reason):
        transcript_usage.read(transcript(tmp_path, *entries))


def test_cache_writes_not_split_by_lifetime_are_not_guessed_at(tmp_path: pathlib.Path) -> None:
    unsplit = response("msg_1", 5, written_5m=100)
    del unsplit["message"]["usage"]["cache_creation"]
    with pytest.raises(UnmeasuredError, match="not split by lifetime"):
        transcript_usage.read(transcript(tmp_path, unsplit))


def test_cache_writes_that_do_not_add_up_are_refused(tmp_path: pathlib.Path) -> None:
    disagreeing = response("msg_1", 5, written_5m=100)
    disagreeing["message"]["usage"]["cache_creation_input_tokens"] = 150
    with pytest.raises(UnmeasuredError, match="do not add up"):
        transcript_usage.read(transcript(tmp_path, disagreeing))


def test_a_transcript_that_does_not_exist_is_unmeasured(tmp_path: pathlib.Path) -> None:
    with pytest.raises(UnmeasuredError, match="could not be read"):
        transcript_usage.read(tmp_path / "missing.jsonl")


def test_a_row_with_no_model_holds_unknown_tokens_and_ledger_cells_stay_empty() -> None:
    unknown = dict.fromkeys(transcript_usage.COLUMNS)
    assert transcript_usage.stored(unknown) is None
    assert transcript_usage.cells(None) == [""] * len(transcript_usage.COLUMNS)

    known = dict(zip(transcript_usage.COLUMNS, ("claude-opus-5", 1, 2, 3, 4, 5, 0), strict=True))
    usage = transcript_usage.stored(known)
    assert usage == Usage("claude-opus-5", 1, 2, 3, 4, 5, 0)
    assert transcript_usage.cells(usage) == ["claude-opus-5", "1", "2", "3", "4", "5", "0"]
