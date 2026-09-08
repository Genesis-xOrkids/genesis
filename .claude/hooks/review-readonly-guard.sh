#!/usr/bin/env bash
# PreToolUse guard for the genesis-reviewer agent. Scoped to that agent's
# Bash matcher only (see .claude/agents/genesis-reviewer.md) — this script
# is the enforcement of "read-only", not the tools: allowlist, because
# tool names in agent frontmatter cannot be scoped to specific commands
# (Bash is all-or-nothing) and this session's permission mode is `auto`,
# under which a subagent's own permissionMode is ignored.
#
# This stops accident and drift, not a determined adversary: it is a
# substring/first-token filter, not a shell parser. Quoting, globbing and
# command substitution inside an already-allowed argument are not defended
# against beyond the checks below.
#
# Deny-by-default: any base command not explicitly recognized is denied.
set -euo pipefail

input="$(cat)"
tool_name="$(printf '%s' "$input" | jq -r '.tool_name // empty')"

deny() {
  local reason="$1"
  jq -n --arg reason "genesis-reviewer read-only guard: $reason" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
  exit 0
}

# Only Bash is guarded here; the matcher already restricts this hook to
# Bash, but stay defensive if it is ever reattached to a broader matcher.
[[ "$tool_name" == "Bash" ]] || exit 0

command="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"
[[ -n "$command" ]] || deny "empty or unreadable command"

trimmed="$(printf '%s' "$command" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

# The one documented, exact-match exception: the vault's own read-only
# staleness check (second-brain/sync-raw.sh --check never writes — see
# the script's own $check_only guard). Nothing else gets a name-based
# exception.
if [[ "$trimmed" == "second-brain/sync-raw.sh --check" || "$trimmed" == "./sync-raw.sh --check" ]]; then
  exit 0
fi

# Structural bans: anything that writes, backgrounds, chains past a
# command boundary, or substitutes a subshell. A single `|` (pipe) is
# allowed and checked per-segment below; every other composition operator
# is denied outright.
banned_tokens=('>' ';' '&&' '||' '&' '`' '$(')
for token in "${banned_tokens[@]}"; do
  if printf '%s' "$command" | grep -qF -- "$token"; then
    deny "forbidden token '$token' in: $command"
  fi
done

check_segment() {
  local segment="$1"
  local base rest

  read -r base rest <<<"$segment"
  [[ -n "$base" ]] || deny "empty command segment"

  case "$base" in
    rg|grep|cat|head|tail|wc|ls|jq|awk|sort|uniq|comm|diff|cut|tr|basename|dirname|realpath|stat|nl)
      ;;
    sed)
      if printf '%s' "$rest" | grep -qE '(^| )-[a-zA-Z]*i[a-zA-Z]*( |$)'; then
        deny "sed -i (in-place edit) is not permitted: $segment"
      fi
      ;;
    find)
      if printf '%s' "$rest" | grep -qE -- '-(exec|execdir|delete|ok)\b'; then
        deny "find -exec/-execdir/-delete/-ok is not permitted: $segment"
      fi
      ;;
    git)
      if printf '%s' "$rest" | grep -qE -- '(^| )(-c|--exec-path)( |=|$)'; then
        deny "git -c/--exec-path can run arbitrary config-driven commands: $segment"
      fi
      sub="$(printf '%s' "$rest" | awk '{print $1}')"
      case "$sub" in
        diff|log|show|status|merge-base|rev-parse|rev-list|branch|blame|ls-files|cat-file|for-each-ref)
          ;;
        *)
          deny "git subcommand '$sub' is not in the read-only allowlist: $segment"
          ;;
      esac
      ;;
    gh)
      area="$(printf '%s' "$rest" | awk '{print $1}')"
      action="$(printf '%s' "$rest" | awk '{print $2}')"
      case "$area" in
        pr)
          case "$action" in
            view|diff|list) ;;
            *) deny "gh pr $action is not in the read-only allowlist: $segment" ;;
          esac
          ;;
        repo)
          case "$action" in
            view) ;;
            *) deny "gh repo $action is not in the read-only allowlist: $segment" ;;
          esac
          ;;
        *)
          deny "gh $area is not in the read-only allowlist (gh api is never permitted): $segment"
          ;;
      esac
      ;;
    *)
      deny "'$base' is not in the read-only allowlist: $segment"
      ;;
  esac
}

IFS='|' read -ra segments <<<"$command"
for segment in "${segments[@]}"; do
  seg_trimmed="$(printf '%s' "$segment" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [[ -n "$seg_trimmed" ]] || deny "empty pipe segment in: $command"
  check_segment "$seg_trimmed"
done

exit 0
