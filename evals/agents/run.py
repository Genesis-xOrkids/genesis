"""Run an agent over its eval cases and score each report.

    python3 -m evals.agents.run genesis-reviewer
    python3 -m evals.agents.run genesis-reviewer jsonb-column clean-test-case

Each case runs as its own headless session with the agent under test as that
session's main agent, so the agent sees nothing but the case. A main agent is
not recorded as a run, so an eval does not add eight reviews to the Employees
tab; the table this prints, pasted into the pull request, is the record.

Three cases run at a time. Each is a full session of the agent under test, and
eight Opus sessions at once is the burst that has cut runs off at the
subscription's session limit; three keeps a limit hit mid-suite to three lost
sessions. The whole suite can outlast a ten-minute tool call, so an agent runs
it in the background. A session that has not answered within the time limit
fails its case, saying so.

Every case's session is measured from its transcript the way the watcher
measures agent runs (`scripts/transcript_usage.py`) and priced at list price
(`scripts/agent_report.py`), so a suite's spend is in its table. Tokens that
cannot be read stay unknown, never zero.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from decimal import Decimal

from evals.agents import score
from intelligence.model_gateway.pricing import UnknownModelError
from scripts import agent_report, transcript_usage

SUITES = pathlib.Path(__file__).resolve().parent
REPO = SUITES.parents[1]
CASE_SECONDS = 540
CASES_AT_ONCE = 3

PROMPT = """This is an eval case, not a real pull request. Review the diff below as if
it had been proposed against this repository. It is a patch and belongs to no
commit. Do not fetch a pull request, and do not run gh. End your report with
`Target: eval {case}` and your Outcome line.

```diff
{diff}```
"""


@dataclass(frozen=True)
class Result:
    """One case's report, where it was saved, how it scored, and what its session spent.

    `usage` is None when the session's tokens could not be read, and
    `unmeasured` then says why.
    """

    case: str
    expectation: score.Expectation
    report_path: pathlib.Path
    outcome: str
    misses: list[str]
    usage: transcript_usage.Usage | None
    unmeasured: str | None


def review(agent: str, case: str, diff: str, session_id: str) -> str:
    """The agent's final message on one case. Raises when the session fails."""
    completed = subprocess.run(
        [
            "claude",
            "-p",
            "--agent",
            agent,
            "--permission-mode",
            "dontAsk",
            "--session-id",
            session_id,
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
    session_id = str(uuid.uuid4())
    try:
        report = review(agent, case.name, diff, session_id)
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
    # A session cut off part-way still spent, so every case is measured.
    try:
        usage = transcript_usage.spent(f"*/{session_id}.jsonl", f"session {session_id}")
    except transcript_usage.UnmeasuredError as reason:
        return Result(case.name, expectation, report_path, outcome, misses, None, str(reason))
    return Result(case.name, expectation, report_path, outcome, misses, usage, None)


def spent(result: Result) -> str:
    """A case's cost at list price, or its tokens and why they have no cost."""
    usage = result.usage
    if usage is None:
        return f"unknown: {result.unmeasured}"
    try:
        return f"${agent_report.price(asdict(usage)):,.2f}"
    except UnknownModelError:
        return (
            f"{usage.output_tokens:,} out, {usage.cache_read_input_tokens:,} cache read; "
            f"no price for {usage.model}"
        )


def spend(results: list[Result]) -> list[str]:
    """The suite's cost at list price, and which cases that total leaves out."""
    total = Decimal(0)
    left_out: list[str] = []
    partial = 0
    for result in results:
        if result.usage is None:
            left_out.append(f"{result.case} (tokens unknown)")
            continue
        partial += result.usage.partial_responses
        try:
            total += agent_report.price(asdict(result.usage))
        except UnknownModelError:
            left_out.append(f"{result.case} (no price for {result.usage.model})")
    lines = [f"Spent at list prices: ${total:,.2f}."]
    if left_out:
        lines.append(f"Not in the total: {', '.join(left_out)}.")
    if partial:
        lines.append(
            f"Output is a lower bound: {partial:,} response{'' if partial == 1 else 's'} "
            "never got a final count in their transcript."
        )
    return lines


def table(results: list[Result]) -> str:
    lines = [
        "| Case | Expected blocking | Report said | Result | Spent |",
        "|---|---|---|---|---|",
    ]
    for result in results:
        low, high = result.expectation.blocking
        expected = str(low) if low == high else f"{low} to {high}"
        verdict = "PASS" if not result.misses else "FAIL: " + "; ".join(result.misses)
        lines.append(
            f"| {result.case} | {expected} | {result.outcome} | {verdict} | {spent(result)} |"
        )
    passed = sum(1 for result in results if not result.misses)
    lines += ["", f"{passed}/{len(results)} passed", *spend(results)]
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
    with ThreadPoolExecutor(max_workers=CASES_AT_ONCE) as pool:
        results = list(pool.map(lambda case: run_case(args.agent, case, reports), cases))
    print(f"Reports are in {reports}\n")
    print(table(results))
    return 0 if all(not result.misses for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
