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
jq -n --arg result "$result" '{systemMessage: $result}'
