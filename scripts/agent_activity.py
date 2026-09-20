"""Live agent activity: who is working now, and what finished.

Every employee's work runs as a subagent - a dispatcher session hands a task to
a specialist, a routine calls one, a person launches one - so one set of project
hooks sees all of it (`.claude/settings.json`). `SubagentStart` opens a row,
`SubagentStop` closes it with what the agent reported, and `SessionEnd` closes
any row its session left open.

That holds only while a named agent is still a subagent. With agent teams on, an
agent started with a name runs as a teammate instead: a session of its own, which
these hooks never see. Its run goes unrecorded, its report is never posted, and
its definition's `isolation: worktree` does not apply, so it works wherever its
caller was. `/build` and the dispatcher both name the agents they start, so the
whole build loop runs unrecorded and unisolated. This repository turns teams off
in `.claude/settings.json`, and `SessionStart` says so when something turns them
back on, because the failure is otherwise silent. The hosted Employees tab reads these rows as
they change, which is the only way it can show work in progress.

The rows live in the brain's D1 database rather than in git, because they are
written from wherever an agent runs - a worktree, a background session, a cloud
routine - and none of those can append to `.claude/runs.tsv` without a branch of
its own. The ledger stays in git all the same (PR #27): `ledger` writes finished
runs into it through the one writer that file has, and marks each row
`ledgered_at`. That is the same arrangement as the note inbox and its
`filed_at`: the row records that the run left, rather than a second copy of it
sitting behind the first.

A run is an agent's report, not just its exit. An agent ends its final message
with `Target:` and `Outcome:` lines. A run that ends without them is still
closed - the Employees tab shows it as ending without a report - but it has
nothing to put in the ledger, and `ledger` leaves it.

A run also records what it saw and what it spent. A review's `Commit:` line
names the commit it reviewed, recorded at the stop, or recorded as unknown with
the reason told to the session when it is not a full commit id. What it spent is
not read here: the response that ends a subagent is written to its transcript
after this hook fires, so the watcher measures a run once it has been finished a
minute (`unmeasured`, `measured`, and `scripts/dispatch_watch.py`).

Run as a module from the repository root, so `scripts` resolves:

    python3 -m scripts.agent_activity hook      # from a hook, event on stdin
    python3 -m scripts.agent_activity record --agent review --target 'PR #31' --outcome '...'
    python3 -m scripts.agent_activity ledger   # write finished runs into the ledger
    python3 -m scripts.agent_activity mark     # mark them, once the ledger is kept
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any

from scripts import task_queue, transcript_usage
from scripts.brain_db import assignments, literal, query, sql_value, stamp
from scripts.employees import defined_ids
from scripts.log_agent_run import LEDGER, append, key, recorded
from scripts.pushed import require_pushed

REPO = pathlib.Path(__file__).resolve().parents[1]
PULL_REQUEST = re.compile(r"PR #(\d+)")
COMMIT = re.compile(r"[0-9a-f]{40}")
# What a stop reports beside its finishing time, in the order `finish` writes it.
REPORTED = ("target", "outcome", "commit_sha")
TEAMS = "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"


# SessionEnd fires for every session in this repository, and most of them never
# run an employee. A marker for each session that did open a run lets the rest
# exit without waiting on the database for nothing to close.
MARKERS = pathlib.Path(tempfile.gettempdir()) / "genesis-agent-runs"


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
    commit_sha: str | None,
) -> bool:
    """Close a run with what the agent reported. Returns whether this closed it.

    A stop whose start was never written still records the run, with its start
    time unknown. A second stop for a run already closed changes nothing and
    returns False, which is what keeps a report from being posted twice: a row
    can be deduplicated after the fact, a pull request comment cannot.
    """
    closed = query(
        f"INSERT INTO agent_runs (agent, session_id, agent_id, finished_at, {', '.join(REPORTED)}) "
        f"VALUES ({literal(agent)}, {literal(session_id)}, {literal(agent_id)}, "
        f"{literal(finished_at)}, "
        + ", ".join(sql_value(value) for value in (target, outcome, commit_sha))
        + ") ON CONFLICT (session_id, agent_id) DO UPDATE SET finished_at = excluded.finished_at, "
        + ", ".join(f"{column} = excluded.{column}" for column in REPORTED)
        + " WHERE agent_runs.finished_at IS NULL RETURNING id"
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


def teams_note() -> str | None:
    """What to say when agent teams are on, because then naming an employee hides it."""
    setting = os.environ.get(TEAMS, "0")
    if setting == "0":
        return None
    return (
        f"{TEAMS} is {setting!r}: an agent started with a name runs as a teammate, so its run "
        "is not recorded, its report is not posted to the pull request, and its definition's "
        "`isolation: worktree` does not apply. Set it to 0 in this repository's "
        ".claude/settings.json, or start agents without a name."
    )


def hook(event: dict[str, Any], employees: set[str], moment: dt.datetime) -> str | None:
    """Handle one hook event. Returns what to tell the session, if anything."""
    name = event["hook_event_name"]
    if name == "SessionStart":
        return teams_note()
    if name == "SessionEnd":
        marker = MARKERS / event["session_id"]
        if marker.exists():
            close_session(event["session_id"], stamp(moment))
            marker.unlink()
        return None
    if name not in ("SubagentStart", "SubagentStop"):
        raise SystemExit(
            "agent_activity handles SessionStart, SubagentStart, SubagentStop and SessionEnd, "
            f"not {name}"
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
    commit, unknown = report_field(message, "Commit"), ""
    if commit is not None and not COMMIT.fullmatch(commit):
        unknown = f"; its Commit line {commit!r} is not a full commit id"
        commit = None
    finished = finish(
        agent, event["session_id"], event["agent_id"], target, outcome, stamp(moment), commit
    )
    if not finished:
        return f"{agent} run was already recorded"
    if target is None or outcome is None:
        return f"{agent} finished without Target/Outcome lines, so it is recorded as ending without a report{unknown}"

    said = f"{agent} run recorded: {target} - {outcome}{unknown}"
    pull_request = PULL_REQUEST.search(target)
    if pull_request:
        said += "; " + post_report(pull_request.group(1), agent, outcome, message)
    return said


def record(agent: str, session_id: str, target: str, outcome: str, moment: dt.datetime) -> None:
    """Record a command's run, which no subagent hook sees because it runs in the session itself.

    A command has no agent id of its own, so the run is keyed by the moment it
    was recorded: one call is one run. It has no transcript of its own either -
    its tokens are its session's - so they are unknown here, as is a commit.
    """
    at = stamp(moment)
    run_id = f"{agent}@{at}"
    start(agent, session_id, run_id, at)
    finish(agent, session_id, run_id, target, outcome, at, None)


def unmeasured(moment: dt.datetime) -> list[dict[str, Any]]:
    """Finished subagent runs whose spend is unknown, settled and not yet a day old.

    A command's run (`record`) is not a subagent's and has no transcript of its
    own - its tokens are its session's - so it is never asked about.
    """
    return query(
        "SELECT id, session_id, agent_id FROM agent_runs WHERE model IS NULL "
        f"AND finished_at < {literal(stamp(moment - transcript_usage.SETTLES_AFTER))} "
        f"AND finished_at > {literal(stamp(moment - transcript_usage.MEASURABLE_FOR))} "
        "AND agent_id NOT LIKE '%@%'"
    )


def measured(run_id: int, usage: transcript_usage.Usage) -> None:
    """Record what a run spent, unless it is already recorded or already history.

    A run the ledger holds is never measured again: the ledger's row is never
    rewritten, so a later measurement here would leave the two disagreeing about
    the same run.
    """
    query(
        f"UPDATE agent_runs SET {assignments(dataclasses.asdict(usage))} "
        f"WHERE id = {int(run_id)} AND model IS NULL AND ledgered_at IS NULL"
    )


def ledger(moment: dt.datetime) -> int:
    """Write finished, reported runs into `.claude/runs.tsv`. Returns how many are unmarked.

    A run whose spend could still be measured waits for the next drain, because
    a ledger row is never rewritten: ledgering it now would freeze empty token
    cells beside a database row that gets the real numbers a minute later.

    Nothing is marked here. The ledger is only kept once it is committed, and in a
    cloud session pushed, so `mark` runs after that. `append` is idempotent on
    `(agent, run_at, target)`, so writing unmarked runs again, after a run that
    failed before marking, adds nothing.
    """
    runs = _reported_unmarked(moment)
    for run in runs:
        append(
            run["agent"],
            run["target"],
            run["outcome"],
            dt.datetime.fromisoformat(run["finished_at"]),
            run["commit_sha"],
            transcript_usage.stored(run),
        )
    # A dispatcher's runs are its tasks, and are ledgered from the queue.
    return len(runs) + task_queue.ledger(moment)


def mark(moment: dt.datetime) -> int:
    """Mark as ledgered the finished runs `.claude/runs.tsv` holds. Returns how many.

    Only runs whose row is in the ledger are marked, so a run that finished after
    the ledger was written stays unmarked for the next pass. In a cloud session
    the ledger must be committed and pushed first.
    """
    require_pushed(LEDGER)
    held = recorded()
    runs = [
        run
        for run in _reported_unmarked(moment)
        if key(run["agent"], run["target"], dt.datetime.fromisoformat(run["finished_at"])) in held
    ]
    if runs:
        ids = ",".join(str(int(run["id"])) for run in runs)
        query(f"UPDATE agent_runs SET ledgered_at = {literal(stamp(moment))} WHERE id IN ({ids})")
    return len(runs) + task_queue.mark(moment, held)


def _reported_unmarked(moment: dt.datetime) -> list[dict[str, Any]]:
    """Reported runs the ledger does not hold, whose spend is settled.

    Settled means measured, or past being measurable, or a command's run, which
    has no transcript of its own to measure.
    """
    return query(
        f"SELECT id, agent, finished_at, {', '.join((*REPORTED, *transcript_usage.COLUMNS))} "
        "FROM agent_runs "
        "WHERE ledgered_at IS NULL AND finished_at IS NOT NULL "
        "AND target IS NOT NULL AND outcome IS NOT NULL "
        "AND (model IS NOT NULL OR agent_id LIKE '%@%' "
        f"OR finished_at < {literal(stamp(moment - transcript_usage.MEASURABLE_FOR))}) "
        "ORDER BY finished_at"
    )


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
    commands.add_parser("ledger", help="write finished runs into .claude/runs.tsv, marking nothing")
    commands.add_parser(
        "mark", help="mark the finished runs .claude/runs.tsv holds, once it is kept"
    )
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
        if said and event.get("hook_event_name") == "SessionStart":
            # Both, so the person reading the terminal and the session itself
            # each learn that naming an agent would hide it.
            print(
                json.dumps(
                    {
                        "systemMessage": said,
                        "hookSpecificOutput": {
                            "hookEventName": "SessionStart",
                            "additionalContext": said,
                        },
                    }
                )
            )
        elif said:
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

    if args.command == "ledger":
        count = ledger(moment)
        print(
            f"{count} unmarked run{'s' if count != 1 else ''} in .claude/runs.tsv; mark them once it is pushed"
        )
        return 0

    count = mark(moment)
    print(f"marked {count} run{'s' if count != 1 else ''} ledgered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
