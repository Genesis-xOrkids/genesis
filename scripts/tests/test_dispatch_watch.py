"""Tests for the dispatch watcher.

The queue, `claude` and `git` are all stood in for, so a test never claims a
live task, starts a session, or creates or moves a checkout.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
from collections.abc import Callable
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
        self.open: list[dict[str, Any]] = []
        self.open_ids: set[int] = set()
        self.done: list[tuple[str, int, str]] = []

    def claim(self, _host: str, _moment: dt.datetime) -> dict[str, Any] | None:
        return self.pending.pop(0) if self.pending else None

    def started(self, task_id: int, session: str) -> None:
        self.done.append(("started", task_id, session))

    def close(self, task_id: int, reason: str, _moment: dt.datetime) -> None:
        self.done.append(("closed", task_id, reason))

    def open_tasks(self, _host: str) -> list[dict[str, Any]]:
        return self.open

    def still_open(self, task_ids: list[int]) -> set[int]:
        return self.open_ids & set(task_ids)


class Machine:
    """Stands in for `subprocess.run`: git worktrees, `claude --bg` and `claude agents`."""

    def __init__(self) -> None:
        self.commands: list[tuple[list[str], Any]] = []
        self.listing: list[dict[str, Any]] = []
        self.start: Callable[[str], subprocess.CompletedProcess[str]] = lambda name: completed(
            f"backgrounded · s-{name} · {name}\n  claude agents\n"
        )
        self.remove: Callable[[str], subprocess.CompletedProcess[str]] = lambda _path: completed()

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append((command, kwargs.get("cwd")))
        if command[:2] == ["claude", "--bg"]:
            return self.start(command[5])
        if command[:2] == ["claude", "agents"]:
            return completed(json.dumps(self.listing))
        if command[3:5] == ["worktree", "add"]:
            pathlib.Path(command[-2]).mkdir(parents=True)
            return completed()
        if command[3:5] == ["worktree", "remove"]:
            removed = self.remove(command[-1])
            if removed.returncode == 0:
                pathlib.Path(command[-1]).rmdir()
            return removed
        return completed()


@pytest.fixture
def queue(monkeypatch: pytest.MonkeyPatch) -> Queue:
    stand_in = Queue()
    for name in ("claim", "started", "close", "open_tasks", "still_open"):
        monkeypatch.setattr(dispatch_watch.task_queue, name, getattr(stand_in, name))
    return stand_in


@pytest.fixture
def machine(monkeypatch: pytest.MonkeyPatch) -> Machine:
    stand_in = Machine()
    monkeypatch.setattr(dispatch_watch.subprocess, "run", stand_in)
    return stand_in


@pytest.fixture
def tasks_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    folder = tmp_path / "genesis-dispatch-tasks"
    monkeypatch.setattr(dispatch_watch, "TASKS", folder)
    monkeypatch.setattr(dispatch_watch, "KEPT", set())
    return folder


def background(session_id: str, state: str, name: str) -> dict[str, Any]:
    return {"id": session_id, "kind": "background", "state": state, "name": name}


# --- dispatching ---


def test_each_pending_task_gets_a_session_in_a_worktree_of_its_own(
    queue: Queue, machine: Machine, tasks_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.pending = [
        {"id": 4, "text": "Review PR #40", "assignee": "genesis-reviewer"},
        {"id": 5, "text": "Tidy the wiki", "assignee": None},
    ]
    monkeypatch.setattr(dispatch_watch, "assignable", lambda: {"genesis-reviewer"})
    dispatch_watch.dispatch("mac", MOMENT)

    assert queue.done == [("started", 4, "s-task-4"), ("started", 5, "s-task-5")]
    adds = [command for command, _ in machine.commands if command[3:5] == ["worktree", "add"]]
    assert adds[0][3:] == [
        "worktree",
        "add",
        "-q",
        "--detach",
        str(tasks_dir / "task-4"),
        "origin/main",
    ]
    (first, first_cwd), _ = [(c, cwd) for c, cwd in machine.commands if c[:2] == ["claude", "--bg"]]
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
    assert first_cwd == tasks_dir / "task-4"
    assert "Task #4, for genesis-reviewer" in first[8]
    assert "python3 -m scripts.task_queue finish 4" in first[8]


@pytest.mark.usefixtures("tasks_dir")
def test_a_task_for_an_agent_nobody_defined_is_closed_without_a_session(
    queue: Queue, machine: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.pending = [{"id": 6, "text": "t", "assignee": "nobody"}]
    monkeypatch.setattr(dispatch_watch, "assignable", lambda: {"genesis-reviewer"})
    dispatch_watch.dispatch("mac", MOMENT)
    assert queue.done == [("closed", 6, "no agent is defined as 'nobody'")]
    assert machine.commands == []


@pytest.mark.usefixtures("tasks_dir")
def test_a_failed_start_closes_the_task_with_why(
    queue: Queue, machine: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.pending = [{"id": 7, "text": "t", "assignee": None}]
    monkeypatch.setattr(dispatch_watch, "assignable", set)
    machine.start = lambda _name: completed("", 1, "not logged in")
    dispatch_watch.dispatch("mac", MOMENT)
    assert queue.done == [("closed", 7, "claude --bg did not start a session: not logged in")]


@pytest.mark.usefixtures("tasks_dir")
def test_a_start_that_reports_failure_but_left_a_session_keeps_the_task(
    queue: Queue, machine: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.pending = [{"id": 7, "text": "t", "assignee": None}]
    monkeypatch.setattr(dispatch_watch, "assignable", set)
    machine.start = lambda _name: completed("something unexpected\n")
    machine.listing = [background("s7", "working", "task-7")]
    dispatch_watch.dispatch("mac", MOMENT)
    assert queue.done == [("started", 7, "s7")]


# --- closing tasks whose session stopped ---


@pytest.mark.parametrize("state", ["done", "failed", "stopped"])
def test_a_task_whose_session_stopped_is_closed_with_why(
    queue: Queue, machine: Machine, state: str
) -> None:
    queue.open = [{"id": 8, "background_id": "s8"}]
    # An interactive session has no short id or state, and must not trip the listing.
    machine.listing = [{"kind": "interactive", "pid": 1}, background("s8", state, "task-8")]
    dispatch_watch.reap("mac", MOMENT)
    assert queue.done == [
        ("closed", 8, f"its session s8 is {state} without finishing the task; see `claude logs s8`")
    ]


@pytest.mark.usefixtures("machine")
def test_a_task_whose_recorded_session_is_gone_is_closed(queue: Queue) -> None:
    queue.open = [{"id": 8, "background_id": "s8"}]
    dispatch_watch.reap("mac", MOMENT)
    assert queue.done == [("closed", 8, "its session s8 is no longer listed")]


def test_a_session_whose_id_was_never_recorded_is_found_by_its_name(
    queue: Queue, machine: Machine
) -> None:
    queue.open = [{"id": 9, "background_id": None}]
    machine.listing = [background("s9", "working", "task-9")]
    dispatch_watch.reap("mac", MOMENT)
    assert queue.done == [("started", 9, "s9")]


@pytest.mark.usefixtures("machine")
def test_a_task_claimed_with_no_session_at_all_is_closed_as_never_started(queue: Queue) -> None:
    queue.open = [{"id": 9, "background_id": None}]
    dispatch_watch.reap("mac", MOMENT)
    assert queue.done == [("closed", 9, "claimed, but no session was started for it")]


@pytest.mark.parametrize("state", ["working", "blocked"])
def test_a_task_whose_session_is_still_going_is_left_alone(
    queue: Queue, machine: Machine, state: str
) -> None:
    queue.open = [{"id": 8, "background_id": "s8"}]
    machine.listing = [background("s8", state, "task-8")]
    dispatch_watch.reap("mac", MOMENT)
    assert queue.done == []


@pytest.mark.usefixtures("queue")
def test_with_no_open_tasks_the_sessions_are_never_listed(machine: Machine) -> None:
    dispatch_watch.reap("mac", MOMENT)
    assert machine.commands == []


# --- worktrees of ended tasks ---


def test_ended_tasks_lose_their_worktrees_unless_work_is_left_in_them(
    queue: Queue,
    machine: Machine,
    tasks_dir: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for task_id in (3, 4, 5, 6):
        (tasks_dir / f"task-{task_id}").mkdir(parents=True)
    (tasks_dir / "notes").mkdir()
    queue.open_ids = {4}
    machine.listing = [background("s5", "working", "task-5")]
    machine.remove = lambda path: (
        completed("", 1, "fatal: contains modified or untracked files")
        if path.endswith("task-6")
        else completed()
    )

    dispatch_watch.sweep()
    dispatch_watch.sweep()

    removals = [
        pathlib.Path(c[-1]).name for c, _ in machine.commands if c[3:5] == ["worktree", "remove"]
    ]
    # 3 ended clean and goes; 4 is still open; 5's session is still working; 6
    # holds uncommitted work, is tried each sweep, and is reported once.
    assert removals == ["task-3", "task-6", "task-6"]
    assert sorted(place.name for place in tasks_dir.iterdir()) == [
        "notes",
        "task-4",
        "task-5",
        "task-6",
    ]
    assert capsys.readouterr().out.count("task #6: kept its worktree") == 1


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
