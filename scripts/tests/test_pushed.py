"""Tests for the guard that keeps marking behind a push, in cloud sessions."""

from __future__ import annotations

import pathlib
import subprocess
from typing import Any

import pytest

from scripts import pushed

LEDGER = pathlib.Path("/repo/.claude/runs.tsv")


class Git:
    """Stands in for `subprocess.run`, answering `git status` and `git branch -r`."""

    def __init__(self, status: str = "", remotes: str = "  origin/chore/brain-upkeep\n") -> None:
        self.status = status
        self.remotes = remotes
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        answer = self.status if "status" in command else self.remotes
        return subprocess.CompletedProcess(command, 0, stdout=answer, stderr="")


def test_on_a_machine_nothing_is_asked_of_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    git = Git(status=" M .claude/runs.tsv")
    monkeypatch.setattr(pushed.subprocess, "run", git)
    pushed.require_pushed(LEDGER)
    assert git.commands == []


def test_in_a_cloud_session_an_uncommitted_file_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setattr(pushed.subprocess, "run", Git(status=" M .claude/runs.tsv"))
    with pytest.raises(SystemExit, match=r"runs\.tsv has changes that are not committed"):
        pushed.require_pushed(LEDGER)


def test_in_a_cloud_session_an_unpushed_commit_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setattr(pushed.subprocess, "run", Git(remotes=""))
    with pytest.raises(SystemExit, match="on no remote branch"):
        pushed.require_pushed(LEDGER)


def test_in_a_cloud_session_a_pushed_file_may_be_marked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    git = Git()
    monkeypatch.setattr(pushed.subprocess, "run", git)
    pushed.require_pushed(LEDGER)
    assert [command[3] for command in git.commands] == ["status", "branch"]
