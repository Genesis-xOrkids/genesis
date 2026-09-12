"""Tests for the dispatch watcher.

The queue, `claude` and `git` are all stood in for, so a test never claims a
live task, starts a session, or moves a checkout.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
from typing import Any

import pytest

from scripts import dispatch_watch

MOMENT = dt.datetime(2026, 9, 12, 3, 0, 0, tzinfo=dt.UTC)


def completed(
    stdout: str = "", returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


class Queue:
    """Stands in for `task_queue`: hands out `pending` tasks, records what the watcher did."""

    def __init__(self) -> None:
        self.pending: list[dict[str, Any]] = []
        self.open_tasks: list[dict[str, Any]] = []
        self.done: list[tuple[str, int, str]] = []

    def claim(self, _moment: dt.datetime) -> dict[str, Any] | None:
        return self.pending.pop(0) if self.pending else None

    def started(self, task_id: int, session: str, _moment: dt.datetime) -> None:
        self.done.append(("started", task_id, session))

    def refuse(self, task_id: int, reason: str, _moment: dt.datetime) -> None:
        self.done.append(("refused", task_id, reason))

    def finish(self, task_id: int, outcome: str, _moment: dt.datetime) -> None:
        self.done.append(("finished", task_id, outcome))

    def working(self) -> list[dict[str, Any]]:
        return self.open_tasks


@pytest.fixture
def queue(monkeypatch: pytest.MonkeyPatch) -> Queue:
    stand_in = Queue()
    for name in ("claim", "started", "refuse", "finish", "working"):
        monkeypatch.setattr(dispatch_watch.task_queue, name, getattr(stand_in, name))
    return stand_in


def never(what: str) -> Any:
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail(what)

    return refuse


# --- dispatching ---


def test_each_pending_task_gets_a_session_named_for_it(
    queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.pending = [
        {"id": 4, "text": "Review PR #40", "assignee": "genesis-reviewer"},
        {"id": 5, "text": "Tidy the wiki", "assignee": None},
    ]
    commands: list[list[str]] = []

    def claude(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return completed(f"backgrounded · s{len(commands)} · {command[5]}\n  claude agents\n")

    monkeypatch.setattr(dispatch_watch.subprocess, "run", claude)
    monkeypatch.setattr(dispatch_watch, "assignable", lambda: {"genesis-reviewer"})
    dispatch_watch.dispatch(MOMENT)

    assert queue.done == [("started", 4, "s1"), ("started", 5, "s2")]
    first = commands[0]
    assert first[:8] == [
        "claude",
        "--bg",
        "--agent",
        "dispatcher",
        "--name",
        "task-4",
        "--permission-mode",
        "auto",
    ]
    assert "Task #4, for genesis-reviewer" in first[8]
    assert "python3 -m scripts.task_queue finish 4" in first[8]


def test_a_task_for_an_agent_nobody_defined_is_refused_without_a_session(
    queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.pending = [{"id": 6, "text": "t", "assignee": "nobody"}]
    monkeypatch.setattr(dispatch_watch, "assignable", lambda: {"genesis-reviewer"})
    monkeypatch.setattr(dispatch_watch.subprocess, "run", never("no session may start"))
    dispatch_watch.dispatch(MOMENT)
    assert queue.done == [("refused", 6, "no agent is defined as 'nobody'")]


def test_a_session_that_fails_to_start_refuses_its_task_with_why(
    queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.pending = [{"id": 7, "text": "t", "assignee": None}]
    monkeypatch.setattr(dispatch_watch, "assignable", set)
    monkeypatch.setattr(
        dispatch_watch.subprocess, "run", lambda *_a, **_k: completed("", 1, "not logged in")
    )
    dispatch_watch.dispatch(MOMENT)
    assert queue.done == [("refused", 7, "claude --bg did not start a session: not logged in")]


# --- closing tasks whose session stopped ---


@pytest.mark.parametrize(
    ("state", "why"),
    [
        ("done", "is done"),
        ("failed", "is failed"),
        ("stopped", "is stopped"),
        (None, "is no longer listed"),
    ],
)
def test_a_task_whose_session_stopped_is_closed_with_why(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, state: str | None, why: str
) -> None:
    queue.open_tasks = [{"id": 8, "background_id": "s8"}]
    # An interactive session has no short id or state, and must not trip the listing.
    listing: list[dict[str, Any]] = [{"kind": "interactive", "pid": 1}]
    if state is not None:
        listing.append({"id": "s8", "kind": "background", "state": state})
    monkeypatch.setattr(
        dispatch_watch.subprocess, "run", lambda *_a, **_k: completed(json.dumps(listing))
    )
    dispatch_watch.reap(MOMENT)
    assert queue.done == [
        ("finished", 8, f"its session s8 {why} without finishing the task; see `claude logs s8`")
    ]


@pytest.mark.parametrize("state", ["working", "blocked"])
def test_a_task_whose_session_is_still_going_is_left_alone(
    queue: Queue, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    queue.open_tasks = [{"id": 8, "background_id": "s8"}]
    listing = [{"id": "s8", "kind": "background", "state": state}]
    monkeypatch.setattr(
        dispatch_watch.subprocess, "run", lambda *_a, **_k: completed(json.dumps(listing))
    )
    dispatch_watch.reap(MOMENT)
    assert queue.done == []


def test_a_task_claimed_with_no_session_is_closed_as_never_started(
    queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.open_tasks = [{"id": 9, "background_id": None}]
    monkeypatch.setattr(dispatch_watch.subprocess, "run", lambda *_a, **_k: completed("[]"))
    dispatch_watch.reap(MOMENT)
    assert queue.done == [("refused", 9, "claimed, but no session was started for it")]


@pytest.mark.usefixtures("queue")
def test_with_no_open_tasks_the_sessions_are_never_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dispatch_watch.subprocess, "run", never("claude agents must not run"))
    dispatch_watch.reap(MOMENT)


# --- the checkout, and installing ---


def test_the_checkout_follows_main_and_says_when_it_moved(monkeypatch: pytest.MonkeyPatch) -> None:
    heads = {"HEAD": "aaa", "origin/main": "bbb"}
    calls: list[list[str]] = []

    def git(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        args = command[3:]
        calls.append(args)
        if args[0] == "rev-parse":
            return completed(heads[args[1]] + "\n")
        if args[0] == "checkout":
            heads["HEAD"] = heads["origin/main"]
        return completed()

    monkeypatch.setattr(dispatch_watch.subprocess, "run", git)
    assert dispatch_watch.follow_main() is True
    assert ["checkout", "-q", "--detach", "origin/main"] in calls
    assert dispatch_watch.follow_main() is False


def test_install_refuses_a_checkout_on_a_branch_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    agent = tmp_path / "LaunchAgents" / "com.genesis.dispatch-watch.plist"
    monkeypatch.setattr(dispatch_watch, "LAUNCH_AGENT", agent)
    monkeypatch.setattr(
        dispatch_watch.subprocess, "run", lambda *_a, **_k: completed("refs/heads/main\n")
    )
    with pytest.raises(SystemExit, match="is on a branch"):
        dispatch_watch.install()
    assert not agent.exists()
