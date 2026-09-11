"""Append one row to the agent run ledger.

An agent that only reads leaves no trace of having run. `genesis-reviewer` is
read-only by construction - `Write` and `Edit` sit in its `disallowedTools` and
a `PreToolUse` hook blocks a shell that would write - so it cannot record its
own runs even in principle. The record therefore has to be written by whatever
invoked it. For a run in Claude Code that is the `Stop` hook in the agent's own
definition (`.claude/hooks/record-review-run.sh`), which fires however the agent
was launched; for the GitHub-side agent it would be CI once it has posted.

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


def append(agent: str, target: str, outcome: str, run_at: dt.datetime) -> tuple[pathlib.Path, bool]:
    """Write one run to the ledger, creating it with a header if absent.

    Returns the ledger path and whether the row is new. Idempotent on
    `(agent, run_at, target)`: a hook that fires twice for one run, a backfill
    re-run, or a union merge that brought the same line in from both branches
    all leave one row. The caller is told which happened, because the `Stop`
    hook posts the review to its pull request only for a run that is new, and a
    comment - unlike a row - cannot be deduplicated after the fact.
    """
    for name, value in (("agent", agent), ("target", target), ("outcome", outcome)):
        if not value.strip():
            raise SystemExit(f"{name} is empty: a run with no {name} records nothing")
        if "\t" in value or "\n" in value:
            raise SystemExit(f"{name} contains a tab or newline, which would split the row")

    if run_at.tzinfo is None:
        raise SystemExit("run_at has no timezone, so the date it lands on is a guess")
    stamp = run_at.astimezone(dt.UTC).isoformat(timespec="seconds")

    # The key is the run, not the whole line: a re-run that reworded its outcome
    # is still the same run, and appending it again would double the count the
    # gallery shows.
    key = (stamp, agent.strip(), target.strip())
    fresh = not LEDGER.exists()
    existing = [] if fresh else LEDGER.read_text(encoding="utf-8").splitlines()[1:]
    if any(tuple(line.split("\t")[:3]) == key for line in existing):
        return LEDGER, False

    with LEDGER.open("a", encoding="utf-8") as handle:
        if fresh:
            handle.write("\t".join(COLUMNS) + "\n")
        handle.write("\t".join([stamp, agent.strip(), target.strip(), outcome.strip()]) + "\n")
    return LEDGER, True


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

    path, new = append(args.agent, args.target, args.outcome, args.run_at)
    verb = "recorded" if new else "already recorded"
    print(f"{verb} {args.agent} run in {path.relative_to(LEDGER.parents[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
