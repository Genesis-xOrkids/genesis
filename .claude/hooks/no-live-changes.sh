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
# Each rule allows what the builder's own work needs and denies the rest of its
# family, rather than naming dangerous commands one at a time: a list of those
# misses the next one. `d1 delete` and `d1 time-travel restore` take no
# `--remote` and act only on the hosted database, and `pages project delete`
# deploys nothing.
#
# Like the other guards here, this stops accident and drift, not a determined
# agent: it matches command text and is not a shell parser, so a command that
# chains an allowed form with a denied one can pass, and code that imports
# `scripts/brain_db.py` some other way never shows its wrangler call here.
# `tooling-builder.md` names that route.
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

pages="Production deploys from main through CI, and the site's project settings are a person's. Yours are \`pages dev\`, \`pages deployment list\`, and the dev preview - \`pages deploy --branch dev\`, only when the spec asks for it."

if has 'wrangler'; then
  # D1: the local database is the builder's, and nothing else is.
  if has '(^|[[:space:]])d1([[:space:]]|$)' && { has '--remote' || ! has '--local([[:space:]=]|$)'; }; then
    deny "The brain's hosted D1 database changes after the pull request that needs it merges. Prove the change with --local, and say in your report what a person applies."
  fi

  # Secrets before Pages: a Pages secret is a secret first.
  if has '(^|[[:space:]])secret([[:space:]]|$)'; then
    deny "The site's secrets are a person's to set. Say in your report which one the change needs."
  fi

  # Pages: every subcommand the command names is checked, not just the first.
  while read -r _ subcommand next; do
    case "$subcommand" in
      dev) ;;
      deployment) [[ "$next" == list ]] || deny "$pages" ;;
      deploy | publish) has '--branch[= ]dev([[:space:]]|$)' || deny "$pages" ;;
      *) deny "$pages" ;;
    esac
  done < <(printf '%s' "$command" | grep -oE '(^|[[:space:]])pages[[:space:]]+[a-z-]+([[:space:]]+[a-z-]+)?' || true)
fi

if has '(^|[[:space:];&|/])launchctl([[:space:]]|$)'; then
  deny "The services running on this machine are a person's to install or remove."
fi

# The scripts built on scripts/brain_db.py reach the hosted database whenever
# they run from the command line.
if has 'python[0-9.]*[[:space:]]+(-m[[:space:]]+scripts\.|([^[:space:]]*/)?scripts/)(agent_activity|agent_report|brain_inbox|dispatch_watch|task_queue)(\.py)?([[:space:]]|$)'; then
  deny "This script runs against the brain's hosted D1 database: \`task_queue finish\` closes a real task, \`agent_activity record\` puts a run on the Employees tab, and the watcher claims real tasks. Prove it under pytest."
fi

exit 0
