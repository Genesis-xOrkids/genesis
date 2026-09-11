#!/usr/bin/env bash
# Tests for record-review-run.sh. Each case runs the hook against a scratch copy
# of the ledger writer, so the real .claude/runs.tsv is never touched.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
fails=0

run_case() {
  local name="$1" message="$2" expect_rows="$3" expect_text="$4"
  local scratch; scratch="$(mktemp -d)"
  mkdir -p "$scratch/scripts" "$scratch/.claude"
  cp "$repo/scripts/log_agent_run.py" "$scratch/scripts/"
  local out
  out="$(jq -n --arg m "$message" '{hook_event_name: "SubagentStop", last_assistant_message: $m}' \
    | CLAUDE_PROJECT_DIR="$scratch" "$here/record-review-run.sh" 2>/dev/null)"
  local rows=0
  [[ -f "$scratch/.claude/runs.tsv" ]] && rows=$(( $(wc -l < "$scratch/.claude/runs.tsv") - 1 ))
  if [[ "$rows" == "$expect_rows" ]] && grep -q -- "$expect_text" <<<"$out$(cat "$scratch/.claude/runs.tsv" 2>/dev/null)"; then
    echo "ok   $name"
  else
    echo "FAIL $name: rows=$rows output=$out"; fails=$((fails + 1))
  fi
  rm -rf "$scratch"
}

run_case "a review is recorded" \
  $'## Blocking\n### 1. something\n\nTarget: PR #12\nOutcome: 1 blocking, 0 design, 0 notes' \
  1 $'PR #12\t1 blocking, 0 design, 0 notes'
run_case "markdown emphasis around the labels is tolerated" \
  $'report body\n**Target:** branch search-precision\n**Outcome:** no findings' \
  1 $'branch search-precision\tno findings'
run_case "a diagnostic with no closing lines records nothing" \
  $'Tools available: Read, Glob, Grep, Bash' \
  0 "no run was recorded"
run_case "a target without an outcome records nothing" \
  $'Target: PR #12' \
  0 "no run was recorded"

exit "$fails"
