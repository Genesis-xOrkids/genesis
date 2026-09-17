"""The dispatch queue: tasks typed into the hosted brain, worked by agents here.

The Dispatch panel writes a task into D1 behind the site's Access gate. A
watcher on the agents' machine (`scripts/dispatch_watch.py`) claims it and
starts a background dispatcher session for it, and the dispatcher hands the work
to the employee best placed to do it.

A task ends one of two ways, recorded apart because they mean different things.
`finish` is the dispatcher reporting an outcome. `close` is the watcher giving
up on a task nobody will finish - no session ever started for it, or its session
stopped without finishing - and its reason is the watcher's, never an outcome.
Only a finished task has a report, so only a finished task reaches the ledger.

A claimed task that a session worked is the dispatcher's run: it started when
the task was claimed, and ended when the task was finished or closed. It is not
copied into `agent_runs`. The Employees tab reads it from here, and `ledger`
writes the finished ones into `.claude/runs.tsv`.

What a task's session spent is recorded on the task by the watcher, once the
session has stopped and its transcript is whole (`measured`), and carried into
the ledger with the task.

Run as a module from the repository root:

    python3 -m scripts.task_queue finish 12 --outcome "Opened PR #40 with the fix"
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import sys
from typing import Any

from scripts import transcript_usage
from scripts.brain_db import assignments, literal, query, stamp
from scripts.log_agent_run import append, key

DISPATCHER = "dispatcher"


def report_started(host: str, moment: dt.datetime) -> None:
    """Record that a watcher has started on this machine."""
    at = literal(stamp(moment))
    query(
        f"INSERT INTO dispatchers (host, started_at, last_seen_at) VALUES ({literal(host)}, {at}, {at}) "
        "ON CONFLICT (host) DO UPDATE SET started_at = excluded.started_at, "
        "last_seen_at = excluded.last_seen_at"
    )


def heartbeat(host: str, moment: dt.datetime) -> None:
    """Record that this machine's watcher is still polling."""
    query(
        f"UPDATE dispatchers SET last_seen_at = {literal(stamp(moment))} WHERE host = {literal(host)}"
    )


def claim(host: str, moment: dt.datetime) -> dict[str, Any] | None:
    """Take the oldest pending task for this machine, or None when nothing is waiting.

    One statement, so two watchers cannot claim the same task, and a task the
    panel cancels before this runs is never claimed.
    """
    claimed = query(
        f"UPDATE tasks SET claimed_at = {literal(stamp(moment))}, claimed_by = {literal(host)} "
        "WHERE id = (SELECT id FROM tasks WHERE claimed_at IS NULL AND cancelled_at IS NULL "
        "ORDER BY created_at, id LIMIT 1) "
        "AND claimed_at IS NULL AND cancelled_at IS NULL RETURNING id, request_id, text, assignee"
    )
    return claimed[0] if claimed else None


def started(task_id: int, background_id: str) -> None:
    """Record the session a task is running in, unless one is already recorded."""
    query(
        f"UPDATE tasks SET background_id = {literal(background_id)} "
        f"WHERE id = {int(task_id)} AND background_id IS NULL"
    )


def close(task_id: int, reason: str, moment: dt.datetime) -> None:
    """Close a claimed task that nobody will finish, with the watcher's reason."""
    query(
        f"UPDATE tasks SET closed_at = {literal(stamp(moment))}, closed_reason = {literal(reason)} "
        f"WHERE id = {int(task_id)} AND finished_at IS NULL AND closed_at IS NULL"
    )


def finish(task_id: int, outcome: str, moment: dt.datetime) -> None:
    """Close a task with the outcome its dispatcher reports."""
    if not outcome.strip():
        raise SystemExit("an outcome is needed: it is all the panel shows of what happened")
    finished = query(
        f"UPDATE tasks SET finished_at = {literal(stamp(moment))}, "
        f"outcome = {literal(outcome.strip())} WHERE id = {int(task_id)} "
        "AND claimed_at IS NOT NULL AND finished_at IS NULL AND closed_at IS NULL RETURNING id"
    )
    if not finished:
        raise SystemExit(
            f"task #{int(task_id)} is not claimed and open, so there is nothing to finish"
        )


def open_tasks(host: str) -> list[dict[str, Any]]:
    """Tasks this machine claimed that are neither finished nor closed.

    Only this machine's. A session's id means something only on the machine it
    runs on, so one watcher never judges another's tasks.
    """
    return query(
        f"SELECT id, request_id, background_id FROM tasks WHERE claimed_by = {literal(host)} "
        "AND finished_at IS NULL AND closed_at IS NULL"
    )


def still_open(request_ids: list[str]) -> set[str]:
    """Which of these tasks, by request id, are neither finished nor closed."""
    if not request_ids:
        return set()
    listed = ",".join(literal(request_id) for request_id in request_ids)
    rows = query(
        f"SELECT request_id FROM tasks WHERE request_id IN ({listed}) "
        "AND finished_at IS NULL AND closed_at IS NULL"
    )
    return {str(row["request_id"]) for row in rows}


def unmeasured(request_ids: list[str]) -> list[dict[str, Any]]:
    """Which of these tasks have ended with what their session spent still unknown."""
    if not request_ids:
        return []
    listed = ",".join(literal(request_id) for request_id in request_ids)
    return query(
        f"SELECT id, request_id, background_id FROM tasks WHERE request_id IN ({listed}) "
        "AND (finished_at IS NOT NULL OR closed_at IS NOT NULL) AND model IS NULL"
    )


def measured(task_id: int, usage: transcript_usage.Usage) -> None:
    """Record what a task's session spent, unless it is already recorded."""
    query(
        f"UPDATE tasks SET {assignments(dataclasses.asdict(usage))} "
        f"WHERE id = {int(task_id)} AND model IS NULL"
    )


def ledger() -> int:
    """Write finished dispatcher runs into `.claude/runs.tsv`. Returns how many are unmarked.

    A closed task has no report, so it stays out of the ledger. Nothing is marked
    here: `mark` does that once the ledger has been kept. `append` is idempotent
    on `(agent, run_at, target)`, so writing the same unmarked tasks again adds
    nothing.
    """
    runs = _finished_unmarked()
    for run in runs:
        append(
            DISPATCHER,
            f"task #{int(run['id'])}",
            run["outcome"],
            dt.datetime.fromisoformat(run["finished_at"]),
            None,
            transcript_usage.stored(run),
        )
    return len(runs)


def mark(moment: dt.datetime, held: set[tuple[str, str, str]]) -> int:
    """Mark as ledgered the finished tasks whose runs are in `held`. Returns how many."""
    runs = [
        run
        for run in _finished_unmarked()
        if key(DISPATCHER, f"task #{int(run['id'])}", dt.datetime.fromisoformat(run["finished_at"]))
        in held
    ]
    if runs:
        listed = ",".join(str(int(run["id"])) for run in runs)
        query(f"UPDATE tasks SET ledgered_at = {literal(stamp(moment))} WHERE id IN ({listed})")
    return len(runs)


def _finished_unmarked() -> list[dict[str, Any]]:
    return query(
        f"SELECT id, outcome, finished_at, {', '.join(transcript_usage.COLUMNS)} FROM tasks "
        "WHERE finished_at IS NOT NULL AND ledgered_at IS NULL ORDER BY finished_at"
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
