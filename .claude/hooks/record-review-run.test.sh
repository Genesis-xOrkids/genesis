#!/usr/bin/env bash
# Tests for record-review-run.sh.
#
# The hook's job is to read `Target:` and `Outcome:` out of the review and hand
# them to the ledger writer. What the writer then does with them is the writer's
# test, not this one - and since the ledger became a database, running the real
# writer here would mean a network call and a row in the live ledger for every
# test case. So each case runs against a scratch project whose
# `scripts/log_agent_run.py` is a stub that records the arguments it was called
# with, and asserts on those.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
fails=0

run_case() {
  local name="$1" message="$2" expect_calls="$3" expect_text="$4"
  local scratch; scratch="$(mktemp -d)"
  mkdir -p "$scratch/scripts"

  # Stands in for the writer. `-m scripts.log_agent_run` finds it here because
  # the hook changes into the project directory first, which is the behaviour
  # this stub is also checking.
  cat > "$scratch/scripts/log_agent_run.py" <<'PY'
import sys
with open("called.txt", "a", encoding="utf-8") as handle:
    handle.write("\t".join(sys.argv[1:]) + "\n")
print("recorded")
PY

  local out
  out="$(jq -n --arg m "$message" '{hook_event_name: "SubagentStop", last_assistant_message: $m}' \
    | CLAUDE_PROJECT_DIR="$scratch" "$here/record-review-run.sh" 2>/dev/null)"
  local calls=0
  [[ -f "$scratch/called.txt" ]] && calls=$(wc -l < "$scratch/called.txt" | tr -d ' ')

  if [[ "$calls" == "$expect_calls" ]] \
     && grep -q -- "$expect_text" <<<"$out$(cat "$scratch/called.txt" 2>/dev/null)"; then
    echo "ok   $name"
  else
    echo "FAIL $name: calls=$calls output=$out"; fails=$((fails + 1))
  fi
  rm -rf "$scratch"
}

run_case "a review is recorded" \
  $'## Blocking\n### 1. something\n\nTarget: PR #12\nOutcome: 1 blocking, 0 design, 0 notes' \
  1 $'--target\tPR #12\t--outcome\t1 blocking, 0 design, 0 notes'
run_case "markdown emphasis around the labels is tolerated" \
  $'report body\n**Target:** branch search-precision\n**Outcome:** no findings' \
  1 $'--target\tbranch search-precision\t--outcome\tno findings'
run_case "a diagnostic with no closing lines records nothing" \
  $'Tools available: Read, Glob, Grep, Bash' \
  0 "no run was recorded"
run_case "a target without an outcome records nothing" \
  $'Target: PR #12' \
  0 "no run was recorded"

# The writer failing is not the same as there being nothing to record: the run
# happened, and the hook has to say the recording did not.
scratch="$(mktemp -d)"
mkdir -p "$scratch/scripts"
printf 'import sys\nsys.exit("D1 unreachable")\n' > "$scratch/scripts/log_agent_run.py"
out="$(jq -n '{hook_event_name: "SubagentStop", last_assistant_message: "Target: PR #9\nOutcome: clean"}' \
  | CLAUDE_PROJECT_DIR="$scratch" "$here/record-review-run.sh" 2>/dev/null)"
if grep -q "could not be recorded" <<<"$out" && grep -q "D1 unreachable" <<<"$out"; then
  echo "ok   a writer failure is reported, not swallowed"
else
  echo "FAIL a writer failure is reported, not swallowed: output=$out"; fails=$((fails + 1))
fi
rm -rf "$scratch"

exit "$fails"
