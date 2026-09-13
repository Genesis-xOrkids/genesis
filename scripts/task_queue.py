"""The dispatch queue: tasks typed into the hosted brain, worked by agents here.

The Dispatch panel writes a task into D1 behind the site's Access gate. The
watcher on the agents' machine (`scripts/dispatch_watch.py`) claims it, starts a
background dispatcher session for it, and records that session's id. The
dispatcher hands the work to the employee best placed to do it and ends by
calling `finish`, which closes the task with a one-line outcome.

Each task's dispatcher run is recorded in `agent_runs` like any other
employee's, keyed by the task rather than by a session. The session's own id is
not known when the run opens, but the task is: one task, one dispatcher run. The
Employees tab then shows the dispatcher as working with no special case, and the
nightly drain ledgers its runs with everyone else's.

Run as a module from the repository root:

    python3 -m scripts.task_queue finish 12 --outcome "Opened PR #40 with the fix"
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Any

from scripts.agent_activity import finish as finish_run
from scripts.agent_activity import stamp
from scripts.agent_activity import start as start_run
from scripts.brain_db import literal, query

DISPATCHER = "dispatcher"


def run_key(task_id: int) -> str:
    """The key a task's dispatcher run is recorded under, as both session and agent id."""
    return f"task-{int(task_id)}"


def report_started(host: str, moment: dt.datetime) -> None:
    """Record that a watcher has started on this machine."""
    at = literal(stamp(moment))
    query(
        f"INSERT INTO dispatchers (host, started_at, last_seen_at) VALUES ({literal(host)}, {at}, {at}) "
        "ON CONFLICT (host) DO UPDATE SET started_at = excluded.started_at, last_seen_at = excluded.last_seen_at"
    )


def heartbeat(host: str, moment: dt.datetime) -> None:
    """Record that this machine's watcher is still polling."""
    query(
        f"UPDATE dispatchers SET last_seen_at = {literal(stamp(moment))} WHERE host = {literal(host)}"
    )


def claim(moment: dt.datetime) -> dict[str, Any] | None:
    """Take the oldest pending task, or None when nothing is waiting.

    One statement, so two watchers cannot claim the same task, and a task the
    panel cancels before this runs is never claimed.
    """
    claimed = query(
        f"UPDATE tasks SET claimed_at = {literal(stamp(moment))} WHERE id = ("
        "SELECT id FROM tasks WHERE claimed_at IS NULL AND cancelled_at IS NULL "
        "ORDER BY created_at, id LIMIT 1"
        ") AND claimed_at IS NULL AND cancelled_at IS NULL RETURNING id, text, assignee"
    )
    return claimed[0] if claimed else None


def started(task_id: int, background_id: str, moment: dt.datetime) -> None:
    """Record the session a task is running in, and open the dispatcher's run for it."""
    query(f"UPDATE tasks SET background_id = {literal(background_id)} WHERE id = {int(task_id)}")
    start_run(DISPATCHER, run_key(task_id), run_key(task_id), stamp(moment))


def refuse(task_id: int, reason: str, moment: dt.datetime) -> None:
    """Close a claimed task that no session ever worked, with why.

    No dispatcher run is recorded, because none happened.
    """
    query(
        f"UPDATE tasks SET finished_at = {literal(stamp(moment))}, outcome = {literal(reason)} "
        f"WHERE id = {int(task_id)} AND finished_at IS NULL"
    )


def finish(task_id: int, outcome: str, moment: dt.datetime) -> None:
    """Close a task with its outcome, and the dispatcher's run for it with the same line."""
    if not outcome.strip():
        raise SystemExit("an outcome is needed: it is all the panel shows of what happened")
    at = stamp(moment)
    closed = query(
        f"UPDATE tasks SET finished_at = {literal(at)}, outcome = {literal(outcome.strip())} "
        f"WHERE id = {int(task_id)} AND claimed_at IS NOT NULL AND finished_at IS NULL RETURNING id"
    )
    if not closed:
        raise SystemExit(
            f"task #{int(task_id)} is not claimed and open, so there is nothing to finish"
        )
    finish_run(
        DISPATCHER, run_key(task_id), run_key(task_id), f"task #{int(task_id)}", outcome.strip(), at
    )


def working() -> list[dict[str, Any]]:
    """Tasks claimed and not yet finished, with the session each was started in."""
    return query(
        "SELECT id, background_id FROM tasks WHERE claimed_at IS NOT NULL AND finished_at IS NULL"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    finishing = commands.add_parser("finish", help="close a task with its outcome")
    finishing.add_argument("task", type=int, help="the task's id, e.g. 12")
    finishing.add_argument("--outcome", required=True, help="what happened, in one line")
    args = parser.parse_args()

    finish(args.task, args.outcome, dt.datetime.now(dt.UTC))
    print(f"task #{args.task} finished: {args.outcome.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
