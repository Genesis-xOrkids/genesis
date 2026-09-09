"""Append one row to the agent run ledger.

An agent that only reads leaves no trace of having run. `genesis-reviewer` is
read-only by construction - `Write` and `Edit` sit in its `disallowedTools` and
a `PreToolUse` hook blocks a shell that would write - so it cannot record its
own runs even in principle. The record therefore has to be written by whatever
invoked it: `/review` once it has relayed the report, or CI once the
GitHub-side agent has posted its comment.

The ledger is `.claude/runs.tsv`, beside the definitions whose runs it records,
rather than an entry in `second-brain/wiki/log.md`. That log is the append-only
record of what happened to the wiki; reviewing a code diff does not touch the
wiki, and the static site build holds the log back, which would make every
recorded review vanish from the published gallery.

This script deliberately does not check the agent name against the roster. The
rule that turns a definition file into an employee id lives in exactly one
place - `read_employees` in `second-brain/site/build.py` - and a copy here
would be a second home for it that could disagree. The build reports any ledger
row whose agent matches no employee instead, which is the same check one step
later and with one owner.
"""

import argparse
import datetime as dt
import pathlib
import sys

LEDGER = pathlib.Path(__file__).resolve().parents[1] / ".claude/runs.tsv"
COLUMNS = ("run_at", "agent", "target", "outcome")


def append(agent: str, target: str, outcome: str) -> pathlib.Path:
    """Write one run to the ledger, creating it with a header if absent."""
    for name, value in (("agent", agent), ("target", target), ("outcome", outcome)):
        if not value.strip():
            raise SystemExit(f"{name} is empty: a run with no {name} records nothing")
        if "\t" in value or "\n" in value:
            raise SystemExit(f"{name} contains a tab or newline, which would split the row")

    run_at = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    new = not LEDGER.exists()
    with LEDGER.open("a", encoding="utf-8") as handle:
        if new:
            handle.write("\t".join(COLUMNS) + "\n")
        handle.write("\t".join([run_at, agent.strip(), target.strip(), outcome.strip()]) + "\n")
    return LEDGER


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--agent", required=True, help="employee id, e.g. genesis-reviewer")
    parser.add_argument("--target", required=True, help="what it ran against, e.g. 'PR #12'")
    parser.add_argument("--outcome", required=True, help="what came back, in a few words")
    args = parser.parse_args()

    path = append(args.agent, args.target, args.outcome)
    print(f"recorded {args.agent} run in {path.relative_to(pathlib.Path.cwd())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
