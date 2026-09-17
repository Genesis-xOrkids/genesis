"""Score an agent's reports against the eval cases written for it.

Each case in `evals/agents/<agent>/<case>/` holds a diff (`diff.patch`) and what
a correct review of it says (`expect.toml`):

    blocking = [1, 3]        # the Outcome line's blocking count, an inclusive range
    design = [0, 4]          # optional: the same for design findings
    must_cite = ["JSON"]     # optional: text the report must contain

Every case is a patch that belongs to no commit, so a correct report also names
no commit: a `Commit:` line would claim the review saw bytes it did not.

The agent under test does the judging. This only checks its report against what
the case wrote down before the agent ran. Nothing here asks a model whether a
report is good, so rewording the agent's instructions cannot move the target,
and a case fails for a stated reason rather than a judgement.

    python3 -m evals.agents.score evals/agents/genesis-reviewer/jsonb-column report.md
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import tomllib
from dataclasses import dataclass

OUTCOME = re.compile(r"^[*_]*Outcome:[*_]*[ \t]*(.+?)[ \t]*$", re.M)
COMMIT = re.compile(r"^[*_]*Commit:", re.M)
FIELDS = {"blocking", "design", "must_cite"}


@dataclass(frozen=True)
class Expectation:
    """What a correct report on one case says."""

    blocking: tuple[int, int]
    design: tuple[int, int] | None
    must_cite: tuple[str, ...]


@dataclass(frozen=True)
class Counts:
    """The finding counts a report's Outcome line states."""

    blocking: int
    design: int


def _span(value: object, field: str, case: pathlib.Path) -> tuple[int, int]:
    if not (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(number, int) for number in value)
        and value[0] <= value[1]
    ):
        raise ValueError(f"{case}: {field} must be [low, high] with low <= high, not {value!r}")
    return (value[0], value[1])


def load(case: pathlib.Path) -> tuple[str, Expectation]:
    """A case's diff and what a correct review of it says. Raises on an incomplete case."""
    diff = (case / "diff.patch").read_text()
    if not diff.strip():
        raise ValueError(f"{case}: diff.patch is empty")
    written = tomllib.loads((case / "expect.toml").read_text())
    unknown = sorted(set(written) - FIELDS)
    if unknown:
        raise ValueError(f"{case}: expect.toml has fields nothing reads: {unknown}")
    if "blocking" not in written:
        raise ValueError(
            f"{case}: expect.toml must say how many blocking findings a correct review has"
        )
    cites = written.get("must_cite", [])
    if not (isinstance(cites, list) and all(isinstance(cite, str) and cite for cite in cites)):
        raise ValueError(f"{case}: must_cite must be a list of non-empty strings")
    return diff, Expectation(
        blocking=_span(written["blocking"], "blocking", case),
        design=_span(written["design"], "design", case) if "design" in written else None,
        must_cite=tuple(cites),
    )


def outcome(report: str) -> Counts:
    """The counts on a report's last Outcome line. Raises when it has none."""
    lines = OUTCOME.findall(report)
    if not lines:
        raise ValueError("the report has no Outcome line, so it is not a finished review")
    line = lines[-1]
    if line.strip().lower() == "no findings":
        return Counts(blocking=0, design=0)
    blocking = re.search(r"(\d+)\s+blocking", line)
    design = re.search(r"(\d+)\s+design", line)
    if blocking is None or design is None:
        raise ValueError(f"the Outcome line does not state blocking and design counts: {line!r}")
    return Counts(blocking=int(blocking.group(1)), design=int(design.group(1)))


def score(report: str, expectation: Expectation) -> list[str]:
    """Every way a report misses its case's expectation; empty when it meets it."""
    try:
        counts = outcome(report)
    except ValueError as error:
        return [str(error)]
    misses: list[str] = []
    low, high = expectation.blocking
    if not low <= counts.blocking <= high:
        misses.append(f"{counts.blocking} blocking, expected {low} to {high}")
    if expectation.design is not None:
        low, high = expectation.design
        if not low <= counts.design <= high:
            misses.append(f"{counts.design} design, expected {low} to {high}")
    if COMMIT.search(report):
        misses.append("names a commit, but the case is a patch that belongs to no commit")
    lowered = report.lower()
    misses.extend(
        f"does not cite {phrase!r}"
        for phrase in expectation.must_cite
        if phrase.lower() not in lowered
    )
    return misses


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("case", type=pathlib.Path, help="the case directory")
    parser.add_argument("report", type=pathlib.Path, help="the agent's report on that case")
    args = parser.parse_args()

    _, expectation = load(args.case)
    misses = score(args.report.read_text(), expectation)
    if misses:
        print(f"FAIL {args.case.name}: " + "; ".join(misses))
        return 1
    print(f"PASS {args.case.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
