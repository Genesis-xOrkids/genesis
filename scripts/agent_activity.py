"""Live agent activity: who is working now, and what finished.

Every employee's work runs as a subagent - a dispatcher session hands a task to
a specialist, a routine calls one, a person launches one - so one set of project
hooks sees all of it (`.claude/settings.json`). `SubagentStart` opens a row,
`SubagentStop` closes it with what the agent reported, and `SessionEnd` closes
any row its session left open. The hosted Employees tab reads these rows as
they change, which is the only way it can show work in progress.

The rows live in the brain's D1 database rather than in git, because they are
written from wherever an agent runs - a worktree, a background session, a cloud
routine - and none of those can append to `.claude/runs.tsv` without a branch of
its own. The ledger stays in git all the same (PR #27): `drain` moves finished
runs into it through the one writer that file has, and marks each row
`ledgered_at`. That is the same arrangement as the note inbox and its
`filed_at`: the row records that the run left, rather than a second copy of it
sitting behind the first.

A run is an agent's report, not just its exit. An agent ends its final message
with `Target:` and `Outcome:` lines. A run that ends without them is still
closed - the Employees tab shows it as ending without a report - but it has
nothing to put in the ledger, and `drain` leaves it.

Run as a module from the repository root, so `scripts` resolves:

    python3 -m scripts.agent_activity hook      # from a hook, event on stdin
    python3 -m scripts.agent_activity record --agent review --target 'PR #31' --outcome '...'
    python3 -m scripts.agent_activity drain
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any

from scripts.brain_db import literal, query
from scripts.employees import defined_ids
from scripts.log_agent_run import append

REPO = pathlib.Path(__file__).resolve().parents[1]
PULL_REQUEST = re.compile(r"PR #(\d+)")

# SessionEnd fires for every session in this repository, and most of them never
# run an employee. A marker for each session that did open a run lets the rest
# exit without waiting on the database for nothing to close.
MARKERS = pathlib.Path(tempfile.gettempdir()) / "genesis-agent-runs"


def stamp(moment: dt.datetime) -> str:
    """A timestamp as the ledger writes one: UTC, to the second, ISO 8601."""
    return moment.astimezone(dt.UTC).isoformat(timespec="seconds")


def sql_value(value: str | None) -> str:
    """A nullable text value as SQL, so an unreported target stays NULL rather than ''."""
    return "NULL" if value is None else literal(value)


def report_field(message: str, label: str) -> str | None:
    """The last `Label:` line of an agent's final message, markdown emphasis tolerated."""
    found = re.findall(rf"^[*_]*{label}:[*_]*[ \t]*(.+?)[ \t]*$", message, re.M)
    return found[-1] if found else None


def start(agent: str, session_id: str, agent_id: str, started_at: str) -> None:
    """Open a run.

    Idempotent on `(session_id, agent_id)`. The start hook runs async, so it can
    land after its own stop; then it fills in the start time and changes
    nothing else.
    """
    query(
        "INSERT INTO agent_runs (agent, session_id, agent_id, started_at) VALUES ("
        f"{literal(agent)}, {literal(session_id)}, {literal(agent_id)}, {literal(started_at)}) "
        "ON CONFLICT (session_id, agent_id) DO UPDATE SET started_at = excluded.started_at "
        "WHERE agent_runs.started_at IS NULL"
    )


def finish(
    agent: str,
    session_id: str,
    agent_id: str,
    target: str | None,
    outcome: str | None,
    finished_at: str,
) -> bool:
    """Close a run with what the agent reported. Returns whether this closed it.

    A stop whose start was never written still records the run, with its start
    time unknown. A second stop for a run already closed changes nothing and
    returns False, which is what keeps a report from being posted twice: a row
    can be deduplicated after the fact, a pull request comment cannot.
    """
    closed = query(
        "INSERT INTO agent_runs (agent, session_id, agent_id, finished_at, target, outcome) VALUES ("
        f"{literal(agent)}, {literal(session_id)}, {literal(agent_id)}, {literal(finished_at)}, "
        f"{sql_value(target)}, {sql_value(outcome)}) "
        "ON CONFLICT (session_id, agent_id) DO UPDATE SET finished_at = excluded.finished_at, "
        "target = excluded.target, outcome = excluded.outcome "
        "WHERE agent_runs.finished_at IS NULL RETURNING id"
    )
    return bool(closed)


def close_session(session_id: str, ended_at: str) -> None:
    """Close every run a session left open: it ended, so nothing in it is still working."""
    query(
        f"UPDATE agent_runs SET finished_at = {literal(ended_at)} "
        f"WHERE session_id = {literal(session_id)} AND finished_at IS NULL"
    )


def post_report(number: str, agent: str, outcome: str, message: str) -> str:
    """Post an agent's whole report to the pull request it names, and say how that went.

    The agent does not post it: a read-only agent cannot, and the guard on
    `genesis-reviewer` denies `gh pr comment` along with every other write. The
    hook does it, which keeps that property and works however the agent was
    launched. The run is recorded either way, so a failed post is reported as
    one rather than implying the report reached the pull request.
    """
    body = f"🤖 **{agent}** — {outcome}\n\n{message}\n"
    try:
        posted = subprocess.run(
            ["gh", "pr", "comment", number, "--body-file", "-"],
            input=body,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return f"the report could NOT be posted to PR #{number}: gh is not on PATH"
    if posted.returncode != 0:
        detail = (posted.stderr or posted.stdout).strip()[:300]
        return f"the report could NOT be posted to PR #{number}: {detail}"
    return f"report posted to PR #{number}"


def hook(event: dict[str, Any], employees: set[str], moment: dt.datetime) -> str | None:
    """Handle one hook event. Returns what to tell the session, if anything."""
    name = event["hook_event_name"]
    if name == "SessionEnd":
        marker = MARKERS / event["session_id"]
        if marker.exists():
            close_session(event["session_id"], stamp(moment))
            marker.unlink()
        return None
    if name not in ("SubagentStart", "SubagentStop"):
        raise SystemExit(
            f"agent_activity handles SubagentStart, SubagentStop and SessionEnd, not {name}"
        )

    agent = event["agent_type"]
    if agent not in employees:
        # Explore, general-purpose and the other built-in agents are tools a
        # session reaches for, not employees, and have no card to show on.
        return None
    if name == "SubagentStart":
        MARKERS.mkdir(parents=True, exist_ok=True)
        (MARKERS / event["session_id"]).touch()
        start(agent, event["session_id"], event["agent_id"], stamp(moment))
        return None

    message = event["last_assistant_message"]
    target, outcome = report_field(message, "Target"), report_field(message, "Outcome")
    if not finish(agent, event["session_id"], event["agent_id"], target, outcome, stamp(moment)):
        return f"{agent} run was already recorded"
    if target is None or outcome is None:
        return f"{agent} finished without Target/Outcome lines, so it is recorded as ending without a report"

    said = f"{agent} run recorded: {target} - {outcome}"
    pull_request = PULL_REQUEST.search(target)
    if pull_request:
        said += "; " + post_report(pull_request.group(1), agent, outcome, message)
    return said


def record(agent: str, session_id: str, target: str, outcome: str, moment: dt.datetime) -> None:
    """Record a command's run, which no subagent hook sees because it runs in the session itself.

    A command has no agent id of its own, so the run is keyed by the moment it
    was recorded: one call is one run.
    """
    at = stamp(moment)
    run_id = f"{agent}@{at}"
    start(agent, session_id, run_id, at)
    finish(agent, session_id, run_id, target, outcome, at)


def drain(moment: dt.datetime) -> int:
    """Move finished, reported runs into `.claude/runs.tsv`. Returns how many.

    Every run goes through `append`, which is idempotent on `(agent, run_at,
    target)`, before any row is marked. A drain that fails part-way leaves its
    rows unmarked, and the next one appends them again as no-ops.
    """
    runs = query(
        "SELECT id, agent, target, outcome, finished_at FROM agent_runs "
        "WHERE ledgered_at IS NULL AND finished_at IS NOT NULL "
        "AND target IS NOT NULL AND outcome IS NOT NULL ORDER BY finished_at"
    )
    for run in runs:
        append(
            run["agent"],
            run["target"],
            run["outcome"],
            dt.datetime.fromisoformat(run["finished_at"]),
        )
    if runs:
        ids = ",".join(str(int(run["id"])) for run in runs)
        query(f"UPDATE agent_runs SET ledgered_at = {literal(stamp(moment))} WHERE id IN ({ids})")
    return len(runs)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hook", help="handle one hook event read from stdin")
    recording = commands.add_parser("record", help="record a command's run from inside its session")
    recording.add_argument("--agent", required=True, help="employee id, e.g. review")
    recording.add_argument("--target", required=True, help="what it ran against, e.g. 'PR #31'")
    recording.add_argument("--outcome", required=True, help="what it did, in a few words")
    commands.add_parser("drain", help="move finished runs into .claude/runs.tsv")
    args = parser.parse_args()
    moment = dt.datetime.now(dt.UTC)

    if args.command == "hook":
        event = json.load(sys.stdin)
        try:
            said = hook(event, defined_ids(REPO), moment)
        except SystemExit as error:
            # A run that happened but could not be written is not the same as
            # nothing to record, so the session is told which.
            said = f"{event.get('agent_type') or 'agent'} activity could not be recorded: {error}"
        if said:
            print(json.dumps({"systemMessage": said}))
        return 0

    if args.command == "record":
        if args.agent not in defined_ids(REPO):
            raise SystemExit(f"no employee is defined as {args.agent!r}")
        session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
        if not session_id:
            raise SystemExit(
                "CLAUDE_CODE_SESSION_ID is not set; record runs from inside a Claude Code session"
            )
        record(args.agent, session_id, args.target, args.outcome, moment)
        print(f"recorded {args.agent} run: {args.target} - {args.outcome}")
        return 0

    count = drain(moment)
    print(f"drained {count} run{'s' if count != 1 else ''} into .claude/runs.tsv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
