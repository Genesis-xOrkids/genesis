"""Run an agent over its eval cases and score each report.

    python3 -m evals.agents.run genesis-reviewer
    python3 -m evals.agents.run genesis-reviewer jsonb-column clean-test-case

Each case runs as its own headless session with the agent under test as that
session's main agent, so the agent sees nothing but the case. A main agent is
not recorded as a run, so an eval does not add eight reviews to the Employees
tab; the eval-runner's own run is the record.

Cases run at the same time, so the whole suite fits in one tool call. A session
that has not answered within the time limit fails its case, saying so.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from evals.agents import score

SUITES = pathlib.Path(__file__).resolve().parent
REPO = SUITES.parents[1]
CASE_SECONDS = 540

PROMPT = """This is an eval case, not a real pull request. Review the diff below as if
it had been proposed against this repository at its current commit. Do not fetch
a pull request, and do not run gh. End your report with `Target: eval {case}` and
your Outcome line.

```diff
{diff}```
"""


@dataclass(frozen=True)
class Result:
    """One case's report, where it was saved, and how it scored."""

    case: str
    expectation: score.Expectation
    report_path: pathlib.Path
    outcome: str
    misses: list[str]


def review(agent: str, case: str, diff: str) -> str:
    """The agent's final message on one case. Raises when the session fails."""
    completed = subprocess.run(
        [
            "claude",
            "-p",
            "--agent",
            agent,
            "--permission-mode",
            "dontAsk",
            "--no-session-persistence",
            PROMPT.format(case=case, diff=diff),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=CASE_SECONDS,
        check=True,
    )
    return completed.stdout


def run_case(agent: str, case: pathlib.Path, reports: pathlib.Path) -> Result:
    diff, expectation = score.load(case)
    report_path = reports / f"{case.name}.md"
    try:
        report = review(agent, case.name, diff)
    except subprocess.TimeoutExpired:
        report = ""
        misses = [f"no report within {CASE_SECONDS} seconds"]
    except subprocess.CalledProcessError as error:
        report = error.stdout or ""
        # A usage limit is reported on stdout, with nothing on stderr.
        reason = (error.stderr or error.stdout or "").strip()[:200]
        misses = [f"the session exited {error.returncode}: {reason}"]
    else:
        misses = score.score(report, expectation)
    report_path.write_text(report)
    try:
        counts = score.outcome(report)
        outcome = f"{counts.blocking} blocking, {counts.design} design"
    except ValueError:
        outcome = "no Outcome line"
    return Result(case.name, expectation, report_path, outcome, misses)


def table(results: list[Result]) -> str:
    lines = [
        "| Case | Expected blocking | Report said | Result |",
        "|---|---|---|---|",
    ]
    for result in results:
        low, high = result.expectation.blocking
        expected = str(low) if low == high else f"{low} to {high}"
        verdict = "PASS" if not result.misses else "FAIL: " + "; ".join(result.misses)
        lines.append(f"| {result.case} | {expected} | {result.outcome} | {verdict} |")
    passed = sum(1 for result in results if not result.misses)
    lines += ["", f"{passed}/{len(results)} passed"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("agent", help="the agent under test; its suite is evals/agents/<agent>")
    parser.add_argument("cases", nargs="*", help="case names to run; all of them when omitted")
    args = parser.parse_args()

    suite = SUITES / args.agent
    if not suite.is_dir():
        parser.error(f"{args.agent} has no eval suite: {suite} does not exist")
    every = sorted(folder for folder in suite.iterdir() if folder.is_dir())
    unknown = sorted(set(args.cases) - {folder.name for folder in every})
    if unknown:
        parser.error(f"{suite} has no cases named {unknown}")
    cases = [folder for folder in every if not args.cases or folder.name in args.cases]
    if not cases:
        parser.error(f"{suite} has no cases")

    reports = pathlib.Path(tempfile.mkdtemp(prefix=f"eval-{args.agent}-"))
    with ThreadPoolExecutor(max_workers=len(cases)) as pool:
        results = list(pool.map(lambda case: run_case(args.agent, case, reports), cases))
    print(f"Reports are in {reports}\n")
    print(table(results))
    return 0 if all(not result.misses for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
