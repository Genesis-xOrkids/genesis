"""Record one agent run in the ledger.

An agent that only reads leaves no trace of having run. `genesis-reviewer` is
read-only by construction - `Write` and `Edit` sit in its `disallowedTools` and
a `PreToolUse` hook blocks a shell that would write - so it cannot record its
own runs even in principle. The record therefore has to be written by whatever
invoked it. For a run in Claude Code that is the `Stop` hook in the agent's own
definition (`.claude/hooks/record-review-run.sh`), which fires however the agent
was launched; for the GitHub-side agent it would be CI once it has posted.

The ledger is the `runs` table in the hosted brain's D1 database, not a file in
this repository and not an entry in `second-brain/wiki/log.md`. The wiki log is
the append-only record of what happened to the wiki, and reviewing a code diff
does not touch the wiki. The file it used to be, `.claude/runs.tsv`, had one
write path - open a pull request - which made every run either a pull request of
its own or a passenger in an unrelated one, made two concurrent branches
conflict on an append, and kept a run invisible until CI next deployed the site.
`second-brain/site/schema.sql` records the same reasoning beside the table.

The agent name is checked against the roster before the row is written, using
the same id rule the site builds the roster from (`scripts/employees.py`). A
typo in an id used to be caught by the site build, one step later, as a warning
beside a row nobody could see; catching it here means the bad row never exists.
Services are not checked, because nothing calls this on their behalf - a GitHub
app records itself by committing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

from scripts.brain_db import literal, query
from scripts.employees import defined_ids

REPO = pathlib.Path(__file__).resolve().parents[1]


def record(agent: str, target: str, outcome: str, run_at: dt.datetime) -> tuple[str, bool]:
    """Write one run. Returns the timestamp it was filed under, and whether it is new.

    Idempotent on the natural key `(agent, run_at, target)`: the row is looked
    up first so the caller can say which happened, and written with
    `INSERT OR IGNORE` so that two hooks racing still leave one row rather than
    failing the second.
    """
    for name, value in (("agent", agent), ("target", target), ("outcome", outcome)):
        if not value.strip():
            raise SystemExit(f"{name} is empty: a run with no {name} records nothing")

    known = defined_ids(REPO)
    if agent.strip() not in known:
        raise SystemExit(
            f"no employee is defined as {agent.strip()!r}. Defined: {', '.join(sorted(known))}"
        )

    if run_at.tzinfo is None:
        raise SystemExit("run_at has no timezone, so the date it lands on is a guess")
    stamp = run_at.astimezone(dt.UTC).isoformat(timespec="seconds")

    existing = query(
        "SELECT id FROM runs WHERE "
        f"agent = {literal(agent.strip())} AND run_at = {literal(stamp)} "
        f"AND target = {literal(target.strip())}"
    )
    values = ", ".join(
        literal(value) for value in (stamp, agent.strip(), target.strip(), outcome.strip())
    )
    query(f"INSERT OR IGNORE INTO runs (run_at, agent, target, outcome) VALUES ({values})")
    return stamp, not existing


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--agent", required=True, help="employee id, e.g. genesis-reviewer")
    parser.add_argument("--target", required=True, help="what it ran against, e.g. 'PR #12'")
    parser.add_argument("--outcome", required=True, help="what came back, in a few words")
    parser.add_argument(
        "--run-at",
        type=dt.datetime.fromisoformat,
        default=dt.datetime.now(dt.UTC),
        help="when it ran, ISO 8601 with a timezone; defaults to now. Only for "
        "recording a run after the fact, from a transcript that shows when it ran.",
    )
    args = parser.parse_args()

    stamp, new = record(args.agent, args.target, args.outcome, args.run_at)
    verb = "recorded" if new else "already recorded"
    print(f"{verb} {args.agent} run at {stamp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
