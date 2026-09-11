#!/usr/bin/env bash
# Stop hook for the genesis-reviewer agent. Claude Code runs a Stop hook in agent
# frontmatter as SubagentStop, only while that agent is running.
#
# The reviewer is read-only, so a run of it leaves no trace unless something
# outside it writes one, and this hook is the one writer. Before it, the record
# depended on the reviewer being launched through /review, and every launch that
# went straight through the Agent tool was never recorded - which is how a
# reviewer that had run showed as "Never run".
#
# It records only what the review itself states: the `Target:` and `Outcome:`
# lines the agent ends every review with (its Step 4). A final message carrying
# neither - a diagnostic, a failure, a run cut short - is not a review, and
# writes nothing.
set -euo pipefail

input="$(cat)"
message="$(printf '%s' "$input" | jq -r '.last_assistant_message // empty')"
field() {
  printf '%s\n' "$message" | sed -n "s/^[*_]*$1:[*_]*[[:space:]]*//p" | tail -n 1
}
target="$(field Target)"
outcome="$(field Outcome)"

if [[ -z "$target" || -z "$outcome" ]]; then
  jq -n '{systemMessage: "genesis-reviewer finished without Target/Outcome lines, so no run was recorded."}'
  exit 0
fi

# Run as a module, from the project directory, so that `scripts` is a package on
# sys.path - the writer imports its D1 adapter and the roster's id rule from
# beside it, and a plain path invocation would put only `scripts/` on the path
# and fail those imports.
cd "${CLAUDE_PROJECT_DIR}"
if ! result="$(python3 -m scripts.log_agent_run \
  --agent genesis-reviewer --target "$target" --outcome "$outcome" 2>&1)"; then
  # The ledger is a database now, so recording can fail in ways appending to a
  # file could not: no network, no Cloudflare login. Say so. Losing the run
  # quietly would put the reviewer back to reading "Never run" after a real
  # review, which is the bug this hook exists to fix.
  jq -n --arg detail "$result" \
    '{systemMessage: ("genesis-reviewer ran, but the run could not be recorded: " + $detail)}'
  exit 0
fi

# The report itself, posted where the diff is.
#
# The reviewer cannot post it: it is read-only by construction and the guard
# denies `gh pr comment` along with everything else that writes. So this hook
# does it, which keeps the agent's read-only property intact and still works
# however the agent was launched. Before this, a review existed only in the
# transcript of the session that ran it - the findings were gone the moment the
# window closed, while the one-line outcome survived in the ledger.
#
# Only a `PR #<n>` target gets a comment. A branch, a path, or a range on main
# has nothing to attach to, and the ledger row is the whole record for those.
pr="$(printf '%s' "$target" | sed -n 's/.*PR #\([0-9][0-9]*\).*/\1/p')"
posted=""
if [[ -n "$pr" ]]; then
  # Gated on the run being new. The ledger insert is idempotent on
  # `(agent, run_at, target)`, but a comment is not - a hook that fired twice
  # would post the review twice. Reusing the writer's own answer keeps one
  # source of truth for "is this run new" rather than inventing a second.
  if [[ "$result" == already* ]]; then
    posted="; the review was already posted to PR #${pr}"
  elif body="$(printf '%s\n' "🤖 **genesis-reviewer** — ${outcome}" "" "$message" \
       | gh pr comment "$pr" --body-file - 2>&1)"; then
    posted="; review posted to PR #${pr}"
  else
    # The run is recorded either way. Say the comment failed rather than
    # implying the review reached the pull request.
    posted="; the review could NOT be posted to PR #${pr}: ${body}"
  fi
fi

jq -n --arg result "$result" --arg posted "$posted" '{systemMessage: ($result + $posted)}'
