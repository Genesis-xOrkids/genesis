#!/usr/bin/env bash
# Unit tests for no-live-changes.sh. Run directly:
#   .claude/hooks/no-live-changes.test.sh
# Exits 1 if any case behaves unexpectedly.
set -uo pipefail

guard="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/no-live-changes.sh"
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

# The hosted D1 database, written or read: over-matching is the safe direction,
# and --local proves the same statement without touching what is running.
expect_deny "npx wrangler d1 execute genesis-brain --remote --command \"ALTER TABLE tasks ADD COLUMN merge_allowed INTEGER\""
expect_deny "npx --yes wrangler d1 migrations apply genesis-brain --remote"
expect_deny "cd second-brain/site && npx wrangler d1 execute genesis-brain --remote -y --json --command \"SELECT 1\""

# Every deploy but the dev preview.
expect_deny "npx wrangler pages deploy"
expect_deny "cd second-brain/site && npx --yes wrangler pages deploy --branch main --commit-dirty=true"
expect_deny "npx wrangler pages deploy --branch=main"
expect_deny "npx wrangler pages deploy --branch development"
expect_deny "npx wrangler pages publish"

# Secrets, and this machine's services, including the watcher itself.
expect_deny "npx wrangler pages secret put ANTHROPIC_API_KEY --env preview"
expect_deny "launchctl unload ~/Library/LaunchAgents/com.genesis.dispatch-watch.plist"
expect_deny "launchctl list | grep genesis"
expect_deny "python3 -m scripts.dispatch_watch install"
expect_deny "uv run python -m scripts.dispatch_watch run --host test-host"
expect_deny "python3 /Users/ty/genesis-dispatch/scripts/dispatch_watch.py run --host test-host"

# The tooling builder's own work stays open: the local database, the dev
# preview, reading and testing the watcher's code, and the site's own gates.
expect_allow "npx wrangler d1 execute genesis-brain --local --command \"SELECT 1\""
expect_allow "cd second-brain/site && ./build.py --target static && npx wrangler pages deploy --branch dev --commit-dirty=true"
expect_allow "npx wrangler pages deploy --branch=dev"
expect_allow "npx wrangler pages dev"
expect_allow "npx wrangler pages deployment list --project-name genesis-brain"
expect_allow "uv run pytest -q scripts/tests/test_dispatch_watch.py"
expect_allow "git diff origin/main -- scripts/dispatch_watch.py"
expect_allow "uv run ruff check scripts/dispatch_watch.py"
expect_allow "python3 second-brain/site/build.py --target static"
expect_allow "node --test second-brain/site/worker.test.mjs"

# Anything that is not a Bash call is none of this hook's business.
out="$(jq -n '{tool_name: "Edit", tool_input: {file_path: "second-brain/site/schema.sql"}}' | "$guard")"
if [[ -n "$out" ]]; then
  echo "FAIL (expected allow for a non-Bash tool)"
  fail=1
else
  echo "ok  allow: non-Bash tool call"
fi

exit "$fail"
