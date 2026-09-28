#!/usr/bin/env bash
# Unit tests for no-catalog-writes.sh. Run directly:
#   .claude/hooks/no-catalog-writes.test.sh
# Exits 1 if any case behaves unexpectedly.
set -uo pipefail

guard="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/no-catalog-writes.sh"
fail=0

run_guard() {
  local cmd="$1"
  jq -n --arg cmd "$cmd" '{tool_name: "Bash", tool_input: {command: $cmd}}' | "$guard"
}

expect_allow() {
  local cmd="$1"
  local out
  out="$(run_guard "$cmd")"
  if [[ -n "$out" ]]; then
    echo "FAIL (expected allow, got deny): $cmd"
    fail=1
  else
    echo "ok  allow: $cmd"
  fi
}

expect_deny() {
  local cmd="$1"
  local out
  out="$(run_guard "$cmd")"
  if [[ "$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision // empty')" == "deny" ]]; then
    echo "ok  deny:  $cmd"
  else
    echo "FAIL (expected deny): $cmd"
    fail=1
  fi
}

# The three writers, in every form an agent would reach for them.
expect_deny "PYTHONPATH=. uv run python scripts/seed_storefronts.py --file storefronts.txt"
expect_deny "uv run python scripts/ingest_catalog.py"
expect_deny "python3 -m scripts.ingest_catalog --domain www.everlane.com"
expect_deny "python3 scripts/backfill_embeddings.py"
expect_deny "cd /tmp && ./scripts/seed_storefronts.py"

# Over-matching is the safe direction: this filter reads the command as text,
# so a command that merely names a writer is denied too. An agent that wanted
# to read one asks for the file by another route rather than working around it.
expect_deny "rg seed_storefronts scripts/"

# The work these agents actually do stays open, including the probe, which is
# the scout's whole job and the nearest neighbour of the scripts denied above.
expect_allow "PYTHONPATH=. uv run python scripts/probe_storefronts.py www.example.com"
expect_allow "git status --short"
expect_allow "gh pr create --draft --title 'Add ten storefronts to the registry'"
expect_allow "uv run pytest -q scripts/tests"
expect_allow "python3 second-brain/site/build.py --target static"

# Anything that is not a Bash call is none of this hook's business.
out="$(jq -n '{tool_name: "Read", tool_input: {file_path: "storefronts.txt"}}' | "$guard")"
if [[ -n "$out" ]]; then
  echo "FAIL (expected allow for a non-Bash tool)"
  fail=1
else
  echo "ok  allow: non-Bash tool call"
fi

exit "$fail"
