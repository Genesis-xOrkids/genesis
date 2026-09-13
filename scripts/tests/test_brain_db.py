"""Tests for how the brain's database is reached: wrangler on a machine, HTTPS in a cloud session.

Neither `wrangler` nor D1 is reached: `subprocess.run` and `urlopen` are stood in for.
"""

from __future__ import annotations

import io
import json
import subprocess
import tomllib
import urllib.request
from typing import Any

import pytest

from scripts import brain_db

DATABASE_ID = tomllib.loads(brain_db.WRANGLER_TOML.read_text())["d1_databases"][0]["database_id"]


class D1:
    """Stands in for `urlopen`, keeping the requests it was sent."""

    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = answer
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, **_options: float) -> io.BytesIO:
        self.requests.append(request)
        return io.BytesIO(json.dumps(self.answer).encode())


@pytest.fixture
def cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-1")


@pytest.mark.usefixtures("cloud")
def test_a_cloud_session_queries_d1_over_https_and_sends_no_key_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d1 = D1({"success": True, "errors": [], "result": [{"success": True, "results": [{"id": 4}]}]})
    monkeypatch.setattr(brain_db.urllib.request, "urlopen", d1)

    assert brain_db.query("SELECT id FROM tasks") == [{"id": 4}]
    (request,) = d1.requests
    assert request.full_url == (
        f"https://api.cloudflare.com/client/v4/accounts/account-1/d1/database/{DATABASE_ID}/query"
    )
    assert json.loads(request.data or b"") == {"sql": "SELECT id FROM tasks"}
    assert request.get_header("Authorization") is None


@pytest.mark.usefixtures("cloud")
def test_a_failed_statement_in_the_cloud_raises_with_what_d1_said(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer = {
        "success": False,
        "errors": [{"code": 7500, "message": "no such table"}],
        "result": [],
    }
    monkeypatch.setattr(brain_db.urllib.request, "urlopen", D1(answer))
    with pytest.raises(SystemExit, match="no such table"):
        brain_db.query("SELECT id FROM nowhere")


def test_a_cloud_session_without_the_account_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    with pytest.raises(SystemExit, match="CLOUDFLARE_ACCOUNT_ID is not set"):
        brain_db.query("SELECT 1")


def test_on_a_machine_the_statement_goes_through_wrangler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout='[{"success": true, "results": []}]')

    monkeypatch.setattr(brain_db.subprocess, "run", run)
    assert brain_db.query("SELECT 1") == []
    assert commands[0][:5] == ["npx", "--yes", "wrangler", "d1", "execute"]
