"""Tests for the dispatch watcher.

The queue, `claude`, `git` and `scutil` are all stood in for, so a test never
claims a live task, starts a session, or creates or moves a checkout.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import plistlib
import subprocess
from collections.abc import Callable
from typing import Any

import pytest

from scripts import dispatch_watch, transcript_usage

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
        self.open_requests: set[str] = set()
        self.to_measure: list[dict[str, Any]] = []
        self.done: list[tuple[str, int, str]] = []
        self.spent: list[tuple[int, transcript_usage.Usage]] = []

    def claim(self, _host: str, _moment: dt.datetime) -> dict[str, Any] | None:
        return self.pending.pop(0) if self.pending else None

    def started(self, task_id: int, session: str) -> None:
        self.done.append(("started", task_id, session))

    def close(self, task_id: int, reason: str, _moment: dt.datetime) -> None:
        self.done.append(("closed", task_id, reason))

    def open_tasks(self, _host: str) -> list[dict[str, Any]]:
        return self.open

    def still_open(self, request_ids: list[str]) -> set[str]:
        return self.open_requests & set(request_ids)

    def unmeasured(self, request_ids: list[str], _moment: dt.datetime) -> list[dict[str, Any]]:
        return [task for task in self.to_measure if task["request_id"] in request_ids]

    def measured(self, task_id: int, usage: transcript_usage.Usage) -> None:
        self.spent.append((task_id, usage))


class Machine:
    """Stands in for `subprocess.run`: git worktrees, `claude --bg` and `claude agents`."""

    def __init__(self) -> None:
        self.commands: list[tuple[list[str], Any]] = []
        self.listing: list[dict[str, Any]] = []
        self.start: Callable[[str], subprocess.CompletedProcess[str]] = lambda name: completed(
            f"backgrounded · s-{name} · {name}\n  claude agents\n"
        )
        # Every worktree's HEAD is on origin/main unless a test says otherwise.
        self.refs: Callable[[str], subprocess.CompletedProcess[str]] = lambda _path: completed(
            "refs/remotes/origin/main\n"
        )
        self.remove: Callable[[str], subprocess.CompletedProcess[str]] = lambda _path: completed()

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append((command, kwargs.get("cwd")))
        if command[:2] == ["claude", "--bg"]:
            return self.start(command[5])
        if command[:2] == ["claude", "agents"]:
            return completed(json.dumps(self.listing))
        if command[3:4] == ["for-each-ref"]:
            return self.refs(command[2])
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
    for name in ("claim", "started", "close", "open_tasks", "still_open", "unmeasured", "measured"):
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


def task(task_id: int, request_id: str, assignee: str | None = None) -> dict[str, Any]:
    return {"id": task_id, "request_id": request_id, "text": "t", "assignee": assignee}


# --- dispatching ---


def test_each_pending_task_gets_a_session_in_a_worktree_named_by_its_request(
    queue: Queue, machine: Machine, tasks_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.pending = [
        {
            "id": 4,
            "request_id": "req-00000004",
            "text": "Review PR #40",
            "assignee": "genesis-reviewer",
        },
        {"id": 5, "request_id": "req-00000005", "text": "Tidy the wiki", "assignee": None},
    ]
    monkeypatch.setattr(dispatch_watch, "assignable", lambda: {"genesis-reviewer"})
    dispatch_watch.dispatch("mac", MOMENT)

    assert queue.done == [
        ("started", 4, "s-task-req-00000004"),
        ("started", 5, "s-task-req-00000005"),
    ]
    adds = [command for command, _ in machine.commands if command[3:5] == ["worktree", "add"]]
    assert adds[0][3:] == [
        "worktree",
        "add",
        "-q",
        "--detach",
        str(tasks_dir / "task-req-00000004"),
        "HEAD",
    ]
    (first, first_cwd), _ = [(c, cwd) for c, cwd in machine.commands if c[:2] == ["claude", "--bg"]]
    assert first[:8] == [
        "claude",
        "--bg",
        "--agent",
        "dispatcher",
        "--name",
        "task-req-00000004",
        "--permission-mode",
        "auto",
    ]
    assert first_cwd == tasks_dir / "task-req-00000004"
    assert "Task #4, for genesis-reviewer" in first[8]
    assert "python3 -m scripts.task_queue finish 4" in first[8]


@pytest.mark.usefixtures("tasks_dir")
def test_a_task_for_an_agent_nobody_defined_is_closed_without_a_session(
    queue: Queue, machine: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.pending = [task(6, "req-00000006", assignee="nobody")]
    monkeypatch.setattr(dispatch_watch, "assignable", lambda: {"genesis-reviewer"})
    dispatch_watch.dispatch("mac", MOMENT)
    assert queue.done == [("closed", 6, "no agent is defined as 'nobody'")]
    assert machine.commands == []


@pytest.mark.usefixtures("tasks_dir")
def test_a_failed_start_closes_the_task_with_why(
    queue: Queue, machine: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.pending = [task(7, "req-00000007")]
    monkeypatch.setattr(dispatch_watch, "assignable", set)
    machine.start = lambda _name: completed("", 1, "not logged in")
    dispatch_watch.dispatch("mac", MOMENT)
    assert queue.done == [("closed", 7, "claude --bg did not start a session: not logged in")]


@pytest.mark.usefixtures("tasks_dir")
def test_a_start_that_reports_failure_but_left_a_session_keeps_the_task(
    queue: Queue, machine: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.pending = [task(7, "req-00000007")]
    monkeypatch.setattr(dispatch_watch, "assignable", set)
    machine.start = lambda _name: completed("something unexpected\n")
    machine.listing = [background("s7", "working", "task-req-00000007")]
    dispatch_watch.dispatch("mac", MOMENT)
    assert queue.done == [("started", 7, "s7")]


def test_a_worktree_that_already_exists_is_never_started_in(
    queue: Queue, machine: Machine, tasks_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    place = tasks_dir / "task-req-00000003"
    place.mkdir(parents=True)
    queue.pending = [task(3, "req-00000003")]
    monkeypatch.setattr(dispatch_watch, "assignable", set)
    dispatch_watch.dispatch("mac", MOMENT)
    assert queue.done == [("closed", 3, f"{place} already exists, so this task cannot have it")]
    assert not [
        c
        for c, _ in machine.commands
        if c[:2] == ["claude", "--bg"] or c[3:5] == ["worktree", "add"]
    ]


def test_a_request_id_the_page_would_not_generate_is_never_a_path(
    queue: Queue, machine: Machine, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.pending = [task(9, "../../elsewhere")]
    monkeypatch.setattr(dispatch_watch, "assignable", set)
    dispatch_watch.dispatch("mac", MOMENT)
    assert queue.done == [("closed", 9, "'../../elsewhere' is not a request id the page generates")]
    assert not [c for c, _ in machine.commands if c[3:5] == ["worktree", "add"]]


# --- closing tasks whose session stopped ---


@pytest.mark.parametrize("state", ["done", "failed", "stopped"])
def test_a_task_whose_session_stopped_is_closed_with_why(
    queue: Queue, machine: Machine, state: str
) -> None:
    queue.open = [{"id": 8, "request_id": "req-00000008", "background_id": "s8"}]
    # An interactive session has no short id or state, and must not trip the listing.
    machine.listing = [
        {"kind": "interactive", "pid": 1},
        background("s8", state, "task-req-00000008"),
    ]
    dispatch_watch.reap("mac", MOMENT)
    assert queue.done == [
        ("closed", 8, f"its session s8 is {state} without finishing the task; see `claude logs s8`")
    ]


@pytest.mark.usefixtures("machine")
def test_a_task_whose_recorded_session_is_gone_is_closed(queue: Queue) -> None:
    queue.open = [{"id": 8, "request_id": "req-00000008", "background_id": "s8"}]
    dispatch_watch.reap("mac", MOMENT)
    assert queue.done == [("closed", 8, "its session s8 is no longer listed")]


def test_a_session_whose_id_was_never_recorded_is_found_by_its_name(
    queue: Queue, machine: Machine
) -> None:
    queue.open = [{"id": 9, "request_id": "req-00000009", "background_id": None}]
    machine.listing = [background("s9", "working", "task-req-00000009")]
    dispatch_watch.reap("mac", MOMENT)
    assert queue.done == [("started", 9, "s9")]


def test_an_earlier_task_with_the_same_number_is_not_mistaken_for_this_one(
    queue: Queue, machine: Machine
) -> None:
    # Task numbers restart when the table is rebuilt; request ids do not.
    queue.open = [{"id": 1, "request_id": "req-new00001", "background_id": None}]
    machine.listing = [background("old", "done", "task-req-old00001")]
    dispatch_watch.reap("mac", MOMENT)
    assert queue.done == [("closed", 1, "claimed, but no session was started for it")]


@pytest.mark.usefixtures("machine")
def test_a_task_claimed_with_no_session_at_all_is_closed_as_never_started(queue: Queue) -> None:
    queue.open = [{"id": 9, "request_id": "req-00000009", "background_id": None}]
    dispatch_watch.reap("mac", MOMENT)
    assert queue.done == [("closed", 9, "claimed, but no session was started for it")]


@pytest.mark.parametrize("state", ["working", "blocked"])
def test_a_task_whose_session_is_still_going_is_left_alone(
    queue: Queue, machine: Machine, state: str
) -> None:
    queue.open = [{"id": 8, "request_id": "req-00000008", "background_id": "s8"}]
    machine.listing = [background("s8", state, "task-req-00000008")]
    dispatch_watch.reap("mac", MOMENT)
    assert queue.done == []


@pytest.mark.usefixtures("queue")
def test_with_no_open_tasks_the_sessions_are_never_listed(machine: Machine) -> None:
    dispatch_watch.reap("mac", MOMENT)
    assert machine.commands == []


# --- worktrees of ended tasks ---


def test_ended_tasks_lose_their_worktrees_unless_work_would_be_lost(
    queue: Queue,
    machine: Machine,
    tasks_dir: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for request_id in ("req-clean", "req-open1", "req-going", "req-dirty", "req-unpushed"):
        (tasks_dir / f"task-{request_id}").mkdir(parents=True)
    (tasks_dir / "notes").mkdir()
    queue.open_requests = {"req-open1"}
    machine.listing = [background("s5", "working", "task-req-going")]
    machine.refs = lambda path: (
        completed("")
        if path.endswith("task-req-unpushed")
        else completed("refs/remotes/origin/main\n")
    )
    machine.remove = lambda path: (
        completed("", 1, "fatal: contains modified or untracked files")
        if path.endswith("task-req-dirty")
        else completed()
    )

    dispatch_watch.sweep(MOMENT)
    dispatch_watch.sweep(MOMENT)

    removals = [
        pathlib.Path(c[-1]).name for c, _ in machine.commands if c[3:5] == ["worktree", "remove"]
    ]
    # clean ended and goes; open1 is still open; going's session is still
    # working; dirty holds uncommitted work and is tried each sweep; unpushed
    # holds commits on no branch and is never tried. Each kept one is reported once.
    assert removals == ["task-req-clean", "task-req-dirty", "task-req-dirty"]
    assert sorted(place.name for place in tasks_dir.iterdir()) == [
        "notes",
        "task-req-dirty",
        "task-req-going",
        "task-req-open1",
        "task-req-unpushed",
    ]
    out = capsys.readouterr().out
    assert out.count("task-req-dirty: kept its worktree: fatal: contains modified") == 1
    assert (
        out.count("task-req-unpushed: kept its worktree: its HEAD is on no branch or remote") == 1
    )


def test_an_ended_tasks_stopped_session_is_measured_once_and_an_unreadable_one_said_once(
    queue: Queue,
    machine: Machine,
    tasks_dir: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    projects = tmp_path / "projects"
    (projects / "-tasks-task-req-done").mkdir(parents=True)
    (projects / "-tasks-task-req-done" / "full-done.jsonl").write_text(
        json.dumps(
            {
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "model": "claude-sonnet-5",
                    "usage": {
                        "input_tokens": 4,
                        "cache_creation_input_tokens": 50,
                        "cache_creation": {
                            "ephemeral_5m_input_tokens": 0,
                            "ephemeral_1h_input_tokens": 50,
                        },
                        "cache_read_input_tokens": 600,
                        "output_tokens": 70,
                    },
                }
            }
        )
    )
    monkeypatch.setattr(dispatch_watch, "PROJECTS", projects)
    monkeypatch.setattr(dispatch_watch, "UNMEASURED", set())
    for request_id in ("req-done", "req-lost", "req-going"):
        (tasks_dir / f"task-{request_id}").mkdir(parents=True)
    queue.to_measure = [
        {"id": 1, "request_id": "req-done", "background_id": "s1"},
        {"id": 2, "request_id": "req-lost", "background_id": "s2"},
        {"id": 3, "request_id": "req-going", "background_id": "s3"},
    ]
    machine.listing = [
        {**background("s1", "done", "task-req-done"), "sessionId": "full-done"},
        {**background("s2", "failed", "task-req-lost"), "sessionId": "full-lost"},
        {**background("s3", "working", "task-req-going"), "sessionId": "full-going"},
    ]
    # Worktrees that hold work stay, so the same tasks come round on the next sweep.
    machine.remove = lambda _path: completed("", 1, "fatal: contains modified or untracked files")

    dispatch_watch.sweep(MOMENT)
    dispatch_watch.sweep(MOMENT)

    # The stopped session is measured on each sweep until the task records it; the
    # stand-in never records it, which is why it appears twice. The working
    # session is left until it stops.
    assert queue.spent == [
        (1, transcript_usage.Usage("claude-sonnet-5", 4, 0, 50, 600, 70, 1)),
        (1, transcript_usage.Usage("claude-sonnet-5", 4, 0, 50, 600, 70, 1)),
    ]
    assert (
        capsys.readouterr().out.count(
            "task #2: its tokens are unknown: 0 transcripts found for session full-lost"
        )
        == 1
    )


def test_a_settled_runs_transcript_is_measured_and_a_missing_one_said_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    projects = tmp_path / "projects"
    subagents = projects / "-Users-ty-genesis" / "session-1" / "subagents"
    subagents.mkdir(parents=True)
    (subagents / "agent-a1.jsonl").write_text(
        json.dumps(
            {
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "model": "claude-opus-5",
                    "stop_reason": "end_turn",
                    "usage": {
                        "input_tokens": 2,
                        "cache_creation_input_tokens": 300,
                        "cache_creation": {
                            "ephemeral_5m_input_tokens": 300,
                            "ephemeral_1h_input_tokens": 0,
                        },
                        "cache_read_input_tokens": 9000,
                        "output_tokens": 400,
                    },
                }
            }
        )
    )
    monkeypatch.setattr(dispatch_watch, "PROJECTS", projects)
    monkeypatch.setattr(dispatch_watch, "UNMEASURED", set())
    settled = [
        {"id": 7, "session_id": "session-1", "agent_id": "a1"},
        {"id": 8, "session_id": "session-elsewhere", "agent_id": "a2"},
    ]
    recorded: list[tuple[int, transcript_usage.Usage]] = []
    monkeypatch.setattr(dispatch_watch.agent_activity, "unmeasured", lambda _moment: settled)
    monkeypatch.setattr(
        dispatch_watch.agent_activity,
        "measured",
        lambda run_id, usage: recorded.append((run_id, usage)),
    )

    dispatch_watch.measure_runs(MOMENT)
    dispatch_watch.measure_runs(MOMENT)

    # The stand-in never records a measurement, so the settled run comes round again.
    assert recorded == [(7, transcript_usage.Usage("claude-opus-5", 2, 300, 0, 9000, 400, 0))] * 2
    out = capsys.readouterr().out
    assert out.count("run #8: its tokens are unknown: 0 transcripts found for agent a2") == 1


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


def test_install_fixes_the_machines_name_in_the_launch_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    agent = tmp_path / "LaunchAgents" / "com.genesis.dispatch-watch.plist"
    monkeypatch.setattr(dispatch_watch, "LAUNCH_AGENT", agent)
    monkeypatch.setattr(dispatch_watch, "LOG", tmp_path / "Logs" / "genesis-dispatch.log")

    def answer(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "symbolic-ref" in command:
            return completed("", 1)
        if command[:3] == ["scutil", "--get", "LocalHostName"]:
            return completed("Tylers-MacBook-Air-4\n")
        return completed()

    monkeypatch.setattr(dispatch_watch.subprocess, "run", answer)
    assert dispatch_watch.install() == 0
    with agent.open("rb") as handle:
        written = plistlib.load(handle)
    assert written["ProgramArguments"][-4:] == [
        "scripts.dispatch_watch",
        "run",
        "--host",
        "Tylers-MacBook-Air-4",
    ]


def test_run_needs_the_name_install_fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["dispatch_watch", "run"])
    with pytest.raises(SystemExit) as exit_info:
        dispatch_watch.main()
    assert exit_info.value.code == 2
