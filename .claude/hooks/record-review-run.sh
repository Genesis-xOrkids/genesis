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

python3 "${CLAUDE_PROJECT_DIR}/scripts/log_agent_run.py" \
  --agent genesis-reviewer --target "$target" --outcome "$outcome" >&2
jq -n --arg target "$target" --arg outcome "$outcome" \
  '{systemMessage: ("Recorded genesis-reviewer run: " + $target + " - " + $outcome)}'
