---
description: Review a diff against the Genesis engineering constitution and the second brain's recorded decisions (read-only)
argument-hint: "[PR# | branch | path] — defaults to the current diff against its merge-base with main"
---

Determine the review target from **$ARGUMENTS**:

- A number (e.g. `7`) — the GitHub PR with that number.
- A branch name — that branch, diffed from `git merge-base <branch> main`
  (or from the base branch's merge-base if the branch is based on another
  in-progress branch, not `main`).
- A path — the working-tree diff scoped to that path.
- Empty — the current working-tree diff (staged + unstaged) against its
  merge-base with `main`.

## Show the diff yourself, first

Before spawning anything, run the resolved diff **in this session** (`git
diff <merge-base>..<target>`, or `gh pr diff <N>`) and show it to the user —
`--stat` plus the full patch, or just the full patch if it's short. Do this
directly, in your own turn; don't wait on or depend on the subagent for it.
This is the user's own view of what's being reviewed, independent of
whatever the reviewer subagent does internally — reviewer-subagent tooling
in this environment has shown itself unreliable (see the note in
`genesis-reviewer.md`), so the diff must not be something only the subagent
sees.

If the diff is large, still show `--stat` in full and the patch itself
(truncate only if it would blow the context budget, and say you truncated
it and by how much).

## Then review it

Invoke the Agent tool with `subagent_type: "genesis-reviewer"`. Give it the
resolved target *and* paste the exact diff text you just captured, so it
reviews the same bytes the user just saw rather than recomputing the diff a
moment later against a target that may have moved. Tell it to follow its own
instructions for orienting in the second brain and reporting.

This agent's report is not shown to the user automatically — when it
finishes, relay its findings to the user verbatim (severity, file:line,
citations, "checked and clean" list, and any proposed wiki follow-ups),
rather than summarizing them away. Do not act on any finding yourself
(no edits) unless the user asks you to after seeing the report.

## Then record the run

The reviewer cannot do this itself: `Write` and `Edit` are in its
`disallowedTools` and the read-only hook blocks a shell that would write, so
a run of it leaves no trace unless the caller leaves one. Once you have
relayed the report, run:

```sh
uv run scripts/log_agent_run.py --agent genesis-reviewer \
  --target "<the resolved target: PR #12, a branch, or a path>" \
  --outcome "<counts by severity, e.g. 2 blocking, 1 design, 0 notes>"
```

Record what the reviewer actually returned, including a clean review (`no
findings`) — a ledger that only holds runs that found something misreports
how often the reviewer is right. Record it even when the user then asks you
to fix a finding; the fix is a separate event and the review still happened.

If the reviewer failed or you could not reach it, do not write a row. The
ledger records runs, and a run that did not produce a review is not one.
