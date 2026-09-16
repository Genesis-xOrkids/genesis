"""Append one run to the agent run ledger, `.claude/runs.tsv`.

The ledger is the git record of what agents did: one row per finished run that
reported a target and an outcome. `scripts/agent_activity.py` records runs live
in the brain's database as they start and finish, wherever they run, and its
`ledger` writes the finished ones here through `append`. Nothing else writes this
file, so there is one answer to what a row looks like and when two runs are the
same run.

The ledger stays in git rather than the database (PR #27) because it is
history: it has to be reproducible from a clone, and it cannot depend on a
network or a login to exist. `.gitattributes` merges it with the union driver,
so branches that each bring rows in never conflict.

It is kept apart from `second-brain/wiki/log.md`. That log is the append-only
record of what happened to the wiki, and reviewing a code diff does not touch
the wiki.
"""

import datetime as dt
import pathlib

LEDGER = pathlib.Path(__file__).resolve().parents[1] / ".claude/runs.tsv"
COLUMNS = ("run_at", "agent", "target", "outcome")


def append(agent: str, target: str, outcome: str, run_at: dt.datetime) -> tuple[pathlib.Path, bool]:
    """Write one run to the ledger, creating it with a header if absent.

    Returns the ledger path and whether the row is new. Idempotent on
    `(agent, run_at, target)`: a drain re-run after failing part-way, or a union
    merge that brought the same line in from both branches, leaves one row.
    """
    for name, value in (("agent", agent), ("target", target), ("outcome", outcome)):
        if not value.strip():
            raise SystemExit(f"{name} is empty: a run with no {name} records nothing")
        if "\t" in value or "\n" in value:
            raise SystemExit(f"{name} contains a tab or newline, which would split the row")

    run = key(agent, target, run_at)
    if run in recorded():
        return LEDGER, False

    fresh = not LEDGER.exists()
    with LEDGER.open("a", encoding="utf-8") as handle:
        if fresh:
            handle.write("\t".join(COLUMNS) + "\n")
        handle.write("\t".join([*run, outcome.strip()]) + "\n")
    return LEDGER, True


def key(agent: str, target: str, run_at: dt.datetime) -> tuple[str, str, str]:
    """What makes two rows the same run: when it finished, who ran, and against what.

    The key is the run, not the whole line: a re-run that reworded its outcome
    is still the same run, and appending it again would double the count the
    gallery shows.
    """
    if run_at.tzinfo is None:
        raise SystemExit("run_at has no timezone, so the date it lands on is a guess")
    return (run_at.astimezone(dt.UTC).isoformat(timespec="seconds"), agent.strip(), target.strip())


def recorded() -> set[tuple[str, str, str]]:
    """The key of every run the ledger holds."""
    if not LEDGER.exists():
        return set()
    lines = LEDGER.read_text(encoding="utf-8").splitlines()[1:]
    return {(fields[0], fields[1], fields[2]) for fields in (line.split("\t") for line in lines)}
