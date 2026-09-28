#!/usr/bin/env bash
# PreToolUse guard for tooling-builder. It denies the commands that change live
# state outside this repository: the brain's hosted D1 database, the deployed
# site and its secrets, and the services running on this machine.
#
# Tooling is the part of the repository wired to things already running. The
# hooks, the watcher and the site all read the hosted D1 schema, so a table
# changed ahead of the pull request that needs it breaks the code running
# against it now. The one exception - a nullable column the new code writes -
# is applied by a person before the merge (docs/agent-network-plan.md §5,
# PR 0.2). Production deploys from main through CI; the dev preview is the only
# deploy a builder makes, and only when its spec asks.
#
# Like the other guards here, this stops accident and drift, not a determined
# agent: it matches command text and is not a shell parser. A script that
# reaches D1 from inside Python - `scripts/brain_db.py` - never shows its
# wrangler call here, and the builder's own instructions are the enforcement
# for that route.
set -euo pipefail

input="$(cat)"
tool_name="$(printf '%s' "$input" | jq -r '.tool_name // empty')"
[[ "$tool_name" == "Bash" ]] || exit 0

command="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"

has() {
  printf '%s' "$command" | grep -qE -- "$1"
}

deny() {
  jq -n --arg reason "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
  exit 0
}

if has 'wrangler' && has '(^|[[:space:]])d1([[:space:]]|$)' && has '--remote'; then
  deny "The brain's hosted D1 database changes after the pull request that needs it merges. Prove the change with --local, and say in your report what a person applies."
fi

if has 'wrangler' && has 'pages[[:space:]]+(deploy|publish)([[:space:]]|$)' \
  && ! has '--branch[= ]dev([[:space:]]|$)'; then
  deny "Production deploys from main through CI. The dev preview is the only deploy that is yours - with --branch dev, and only when the spec asks for it."
fi

if has 'wrangler' && has '(^|[[:space:]])secret([[:space:]]|$)'; then
  deny "The site's secrets are a person's to set. Say in your report which one the change needs."
fi

if has '(^|[[:space:];&|])launchctl([[:space:]]|$)'; then
  deny "The services running on this machine are a person's to install or remove."
fi

if has 'python[0-9.]*[[:space:]]+(-m[[:space:]]+scripts\.dispatch_watch|([^[:space:]]*/)?scripts/dispatch_watch\.py)'; then
  deny "Running the dispatch watcher claims real tasks from the queue. Its behaviour is tested under pytest."
fi

exit 0
