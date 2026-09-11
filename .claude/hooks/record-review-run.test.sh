#!/usr/bin/env bash
# Tests for record-review-run.sh. Each case runs the hook against a scratch copy
# of the ledger writer, so the real .claude/runs.tsv is never touched.
#
# `gh` is stubbed for the same reason: the hook posts the review to the pull
# request named in `Target:`, and a test reaching the real `gh` would comment on
# a real pull request every time it ran.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
fails=0

# Stands in for `gh`, writing its arguments and the body it was piped to a file.
# Nothing in this suite may reach GitHub.
stub_gh() {
  local scratch="$1"
  mkdir -p "$scratch/bin"
  cat > "$scratch/bin/gh" <<'GH'
#!/usr/bin/env bash
{ printf '%s\n' "$*"; cat; } > "$(dirname "$0")/../gh-call.txt"
GH
  chmod +x "$scratch/bin/gh"
}

run_case() {
  local name="$1" message="$2" expect_rows="$3" expect_text="$4"
  local scratch; scratch="$(mktemp -d)"
  mkdir -p "$scratch/scripts" "$scratch/.claude"
  cp "$repo/scripts/log_agent_run.py" "$scratch/scripts/"
  stub_gh "$scratch"
  local out
  out="$(jq -n --arg m "$message" '{hook_event_name: "SubagentStop", last_assistant_message: $m}' \
    | PATH="$scratch/bin:$PATH" CLAUDE_PROJECT_DIR="$scratch" "$here/record-review-run.sh" 2>/dev/null)"
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

# --- posting the review to the pull request ---
#
# These run the real writer against a scratch ledger, so they also cover the
# idempotency the posting gate depends on.

posting_case() {
  local name="$1" message="$2" expect_gh="$3" expect_text="$4"
  local scratch; scratch="$(mktemp -d)"
  mkdir -p "$scratch/scripts" "$scratch/.claude"
  cp "$repo/scripts/log_agent_run.py" "$scratch/scripts/"
  stub_gh "$scratch"

  local out
  out="$(jq -n --arg m "$message" '{hook_event_name: "SubagentStop", last_assistant_message: $m}' \
    | PATH="$scratch/bin:$PATH" CLAUDE_PROJECT_DIR="$scratch" "$here/record-review-run.sh" 2>/dev/null)"

  local called=no
  [[ -f "$scratch/gh-call.txt" ]] && called=yes
  if [[ "$called" == "$expect_gh" ]] \
     && grep -q -- "$expect_text" <<<"$out$(cat "$scratch/gh-call.txt" 2>/dev/null)"; then
    echo "ok   $name"
  else
    echo "FAIL $name: gh_called=$called output=$out"; fails=$((fails + 1))
  fi
  rm -rf "$scratch"
}

posting_case "a PR review is posted as a comment on that PR" \
  $'## Blocking\n### 1. a real finding\n\nTarget: PR #12\nOutcome: 1 blocking, 0 design, 0 notes' \
  yes "pr comment 12 --body-file -"
posting_case "the comment carries the findings, not just the outcome" \
  $'## Blocking\n### 1. a real finding\n\nTarget: PR #12\nOutcome: 1 blocking, 0 design, 0 notes' \
  yes "a real finding"
posting_case "a branch review posts nothing, having no PR to attach to" \
  $'report\nTarget: branch search-precision\nOutcome: no findings' \
  no "recorded"
posting_case "a review of main over a range posts nothing" \
  $'report\nTarget: main (c0e8ec4..HEAD, 3 commits)\nOutcome: no findings' \
  no "recorded"

# The same review recorded twice is one row and one comment. This drives the
# real writer twice against one scratch ledger, so it covers the idempotency and
# the posting gate together.
scratch="$(mktemp -d)"
mkdir -p "$scratch/scripts" "$scratch/.claude"
cp "$repo/scripts/log_agent_run.py" "$scratch/scripts/"
stub_gh "$scratch"
event="$(jq -n '{hook_event_name: "SubagentStop", last_assistant_message: "Target: PR #12\nOutcome: clean"}')"
first="$(printf '%s' "$event" | PATH="$scratch/bin:$PATH" CLAUDE_PROJECT_DIR="$scratch" "$here/record-review-run.sh" 2>/dev/null)"
rm -f "$scratch/gh-call.txt"
second="$(printf '%s' "$event" | PATH="$scratch/bin:$PATH" CLAUDE_PROJECT_DIR="$scratch" "$here/record-review-run.sh" 2>/dev/null)"
rows=$(( $(wc -l < "$scratch/.claude/runs.tsv") - 1 ))
if grep -q "review posted" <<<"$first" && grep -q "already posted" <<<"$second" \
   && [[ ! -f "$scratch/gh-call.txt" ]] && [[ "$rows" == 1 ]]; then
  echo "ok   a repeated run is one row and is not posted twice"
else
  echo "FAIL a repeated run is one row and is not posted twice: rows=$rows first=$first second=$second"
  fails=$((fails + 1))
fi
rm -rf "$scratch"

# The writer failing is not the same as there being nothing to record: the run
# happened, and the hook has to say the recording did not.
scratch="$(mktemp -d)"
mkdir -p "$scratch/scripts" "$scratch/bin"
printf 'import sys\nsys.exit("ledger is not writable")\n' > "$scratch/scripts/log_agent_run.py"
stub_gh "$scratch"
out="$(jq -n '{hook_event_name: "SubagentStop", last_assistant_message: "Target: PR #9\nOutcome: clean"}' \
  | PATH="$scratch/bin:$PATH" CLAUDE_PROJECT_DIR="$scratch" "$here/record-review-run.sh" 2>/dev/null)"
if grep -q "could not be recorded" <<<"$out" && grep -q "not writable" <<<"$out" \
   && [[ ! -f "$scratch/gh-call.txt" ]]; then
  echo "ok   a writer failure is reported, and nothing is posted"
else
  echo "FAIL a writer failure is reported, and nothing is posted: output=$out"; fails=$((fails + 1))
fi
rm -rf "$scratch"

# A failed post must not be reported as a success, and must not lose the run.
scratch="$(mktemp -d)"
mkdir -p "$scratch/scripts" "$scratch/.claude" "$scratch/bin"
cp "$repo/scripts/log_agent_run.py" "$scratch/scripts/"
printf '#!/usr/bin/env bash\necho "gh: not authenticated" >&2\nexit 1\n' > "$scratch/bin/gh"
chmod +x "$scratch/bin/gh"
out="$(jq -n '{hook_event_name: "SubagentStop", last_assistant_message: "Target: PR #12\nOutcome: clean"}' \
  | PATH="$scratch/bin:$PATH" CLAUDE_PROJECT_DIR="$scratch" "$here/record-review-run.sh" 2>/dev/null)"
if grep -q "could NOT be posted" <<<"$out" && [[ -f "$scratch/.claude/runs.tsv" ]]; then
  echo "ok   a failed post is reported, and the run is still recorded"
else
  echo "FAIL a failed post is reported, and the run is still recorded: output=$out"; fails=$((fails + 1))
fi
rm -rf "$scratch"

exit "$fails"
