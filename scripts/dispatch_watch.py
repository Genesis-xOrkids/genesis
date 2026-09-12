"""Watch the dispatch queue, and start a dispatcher session for each task.

The Dispatch panel on the hosted brain writes tasks into D1. This runs on the
machine the agents work on, under launchd, so it is always polling while the
machine is awake. Every 30 seconds it:

1. keeps its own checkout at `origin/main`, and exits when that moves so launchd
   restarts it on the new code;
2. records a heartbeat, so the panel can say whether anything is on duty;
3. closes tasks whose session has stopped without finishing them;
4. claims each pending task and starts a background `dispatcher` session for it.

Polling costs no tokens: nothing starts a model until there is a task.

It runs from a checkout of its own, a detached worktree at `origin/main`, and
refuses to install anywhere else. It moves that checkout's HEAD, so running it
from a branch someone is working on would move theirs.

    git worktree add --detach ../genesis-dispatch origin/main
    cd ../genesis-dispatch
    python3 -m scripts.dispatch_watch install      # write the LaunchAgent and load it
    python3 -m scripts.dispatch_watch uninstall    # unload it and remove it
    python3 -m scripts.dispatch_watch run          # the loop launchd keeps alive
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import plistlib
import re
import socket
import subprocess
import sys
import time
from typing import Any

from scripts import task_queue
from scripts.employees import CLAUDE_AGENTS, agent_id

REPO = pathlib.Path(__file__).resolve().parents[1]
POLL_SECONDS = 30
LABEL = "com.genesis.dispatch-watch"
LAUNCH_AGENT = pathlib.Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
LOG = pathlib.Path.home() / "Library/Logs/genesis-dispatch.log"

# States `claude agents` reports for a session that is still on its task:
# running, or waiting on a person (a permission prompt, a question). Anything
# else - done, failed, stopped, or no longer listed - means it has stopped.
STILL_GOING = {"working", "blocked"}
BACKGROUNDED = re.compile(r"^backgrounded · (\S+)")


def log(message: str) -> None:
    """One timestamped line to stdout, which launchd writes to the log file."""
    print(f"{task_queue.stamp(dt.datetime.now(dt.UTC))} {message}", flush=True)


def git(*args: str) -> str:
    finished = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False
    )
    if finished.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {finished.stderr.strip()[:300]}")
    return finished.stdout.strip()


def follow_main() -> bool:
    """Move this checkout to `origin/main`. Returns whether it moved."""
    git("fetch", "-q", "origin", "main")
    if git("rev-parse", "HEAD") == git("rev-parse", "origin/main"):
        return False
    git("checkout", "-q", "--detach", "origin/main")
    return True


def assignable() -> set[str]:
    """The agents a task can be given to: every defined agent but the dispatcher itself."""
    return {agent_id(path) for path in (REPO / CLAUDE_AGENTS).glob("*.md")} - {
        task_queue.DISPATCHER
    }


def prompt(task: dict[str, Any]) -> str:
    """What the dispatcher session is started with."""
    who = f", for {task['assignee']}" if task["assignee"] else ""
    return (
        f"Task #{task['id']}{who}, from the Dispatch panel:\n\n{task['text']}\n\n"
        f"Handle it as your instructions describe, and finish it with "
        f'`python3 -m scripts.task_queue finish {task["id"]} --outcome "..."`.'
    )


def start_session(task: dict[str, Any]) -> str:
    """Start a background dispatcher session for a task. Returns its short id."""
    started = subprocess.run(
        [
            "claude",
            "--bg",
            "--agent",
            task_queue.DISPATCHER,
            "--name",
            f"task-{task['id']}",
            "--permission-mode",
            "auto",
            prompt(task),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    found = BACKGROUNDED.match(started.stdout)
    if started.returncode != 0 or not found:
        detail = (started.stderr or started.stdout).strip()[:300]
        raise SystemExit(f"claude --bg did not start a session: {detail}")
    return found.group(1)


def sessions() -> dict[str, str]:
    """Every background session `claude agents` knows, finished ones included, by short id."""
    listed = subprocess.run(
        ["claude", "agents", "--json", "--all"], capture_output=True, text=True, check=False
    )
    if listed.returncode != 0:
        raise SystemExit(f"claude agents failed: {listed.stderr.strip()[:300]}")
    return {
        session["id"]: session["state"]
        for session in json.loads(listed.stdout)
        if session["kind"] == "background"
    }


def reap(moment: dt.datetime) -> None:
    """Close every task whose session has stopped without finishing it.

    Without this a session that failed, was stopped, or ended its turn without
    calling `finish` would leave its task claimed, and the dispatcher working,
    forever.
    """
    open_tasks = task_queue.working()
    if not open_tasks:
        return
    states = sessions()
    for task in open_tasks:
        session = task["background_id"]
        if session is None:
            task_queue.refuse(task["id"], "claimed, but no session was started for it", moment)
            log(f"task #{task['id']}: claimed with no session, closed")
            continue
        state = states.get(session)
        if state in STILL_GOING:
            continue
        why = "is no longer listed" if state is None else f"is {state}"
        task_queue.finish(
            task["id"],
            f"its session {session} {why} without finishing the task; see `claude logs {session}`",
            moment,
        )
        log(f"task #{task['id']}: session {session} {why}, closed")


def dispatch(moment: dt.datetime) -> None:
    """Claim every pending task and start a session for each."""
    agents = assignable()
    while task := task_queue.claim(moment):
        if task["assignee"] and task["assignee"] not in agents:
            reason = f"no agent is defined as {task['assignee']!r}"
            task_queue.refuse(task["id"], reason, moment)
            log(f"task #{task['id']}: {reason}")
            continue
        try:
            session = start_session(task)
        except SystemExit as error:
            task_queue.refuse(task["id"], str(error), moment)
            log(f"task #{task['id']}: {error}")
            continue
        task_queue.started(task["id"], session, moment)
        log(f"task #{task['id']}: started session {session}")


def run() -> int:
    host = socket.gethostname()
    task_queue.report_started(host, dt.datetime.now(dt.UTC))
    log(f"watching the dispatch queue on {host} from {REPO}")
    while True:
        try:
            if follow_main():
                # Exiting hands the new code to launchd, which starts it again.
                log("main moved; restarting on the new code")
                return 0
            moment = dt.datetime.now(dt.UTC)
            task_queue.heartbeat(host, moment)
            reap(moment)
            dispatch(moment)
        except SystemExit as error:
            # A failed poll - no network, wrangler logged out - is logged and
            # tried again. The heartbeat stops moving meanwhile, so the panel
            # shows nothing on duty rather than a watcher that looks healthy.
            log(f"poll failed: {error}")
        time.sleep(POLL_SECONDS)


def install() -> int:
    if (
        subprocess.run(
            ["git", "-C", str(REPO), "symbolic-ref", "-q", "HEAD"], capture_output=True, check=False
        ).returncode
        == 0
    ):
        raise SystemExit(
            f"{REPO} is on a branch. The watcher moves its checkout to origin/main, so it runs "
            "from a detached worktree of its own:\n"
            "    git worktree add --detach ../genesis-dispatch origin/main"
        )
    LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LAUNCH_AGENT.open("wb") as handle:
        plistlib.dump(
            {
                "Label": LABEL,
                "ProgramArguments": [sys.executable, "-m", "scripts.dispatch_watch", "run"],
                "WorkingDirectory": str(REPO),
                "RunAtLoad": True,
                "KeepAlive": True,
                "StandardOutPath": str(LOG),
                "StandardErrorPath": str(LOG),
                # launchd starts jobs with a minimal PATH; the watcher needs the
                # one that finds git, claude and npx.
                "EnvironmentVariables": {
                    "PATH": os.environ["PATH"],
                    "HOME": str(pathlib.Path.home()),
                },
            },
            handle,
        )
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True, check=False)
    loaded = subprocess.run(
        ["launchctl", "bootstrap", domain, str(LAUNCH_AGENT)],
        capture_output=True,
        text=True,
        check=False,
    )
    if loaded.returncode != 0:
        raise SystemExit(f"launchctl bootstrap failed: {loaded.stderr.strip()}")
    print(f"installed {LABEL}; logging to {LOG}")
    return 0


def uninstall() -> int:
    subprocess.run(
        ["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True, check=False
    )
    LAUNCH_AGENT.unlink(missing_ok=True)
    print(f"uninstalled {LABEL}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", choices=["run", "install", "uninstall"])
    command = parser.parse_args().command
    return {"run": run, "install": install, "uninstall": uninstall}[command]()


if __name__ == "__main__":
    sys.exit(main())
