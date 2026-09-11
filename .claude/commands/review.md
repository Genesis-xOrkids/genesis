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

## The run records itself

The reviewer ends its report with `Target:` and `Outcome:` lines, and a `Stop`
hook in its definition writes them to `.claude/runs.tsv` when it finishes,
however it was launched. Do not also run `scripts/log_agent_run.py` here: that
would record every review launched through this command twice.
