#!/usr/bin/env bash
# PreToolUse guard for the agents that create: the three builders and
# storefront-scout. It denies the three scripts that write to the hosted
# catalog, whatever `GENESIS_DATABASE_URL` points at.
#
# Their frontmatter already withholds the Neon MCP tools, but that is not the
# route any of them would actually take: each holds Bash, and the writers are
# ordinary scripts in this repository. `seed_storefronts.py` and
# `ingest_catalog.py` write through the one write door, and
# `backfill_embeddings.py` rewrites vectors over the whole catalog. Registering
# storefronts and ingesting them is a person's call, made after a pull request
# merges, per the constitution's rule that write tools are gated.
#
# Like `.claude/hooks/review-readonly-guard.sh`, this stops accident and drift,
# not a determined agent: it matches script names in the command text and is
# not a shell parser. The agents' own instructions remain the enforcement for
# everything it does not name.
set -euo pipefail

input="$(cat)"
tool_name="$(printf '%s' "$input" | jq -r '.tool_name // empty')"
[[ "$tool_name" == "Bash" ]] || exit 0

command="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"

for script in seed_storefronts ingest_catalog backfill_embeddings; do
  if printf '%s' "$command" | grep -qF -- "$script"; then
    jq -n --arg script "$script" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: ("\($script) writes to the hosted catalog. A person runs it after the pull request merges - say in your report that it is waiting, and do not work around this.")
      }
    }'
    exit 0
  fi
done

exit 0
