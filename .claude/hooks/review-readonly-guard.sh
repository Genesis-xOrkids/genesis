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
# exception. It is allowed by its path from the repository root, and by the
# absolute path of this checkout's own copy, with or without `bash` - never by
# an absolute path anywhere else, which could name any script.
cwd="$(printf '%s' "$input" | jq -r '.cwd // empty')"
toplevel=""
if [[ -n "$cwd" ]]; then
  toplevel="$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null || true)"
fi
sync_checks=("second-brain/sync-raw.sh --check" "bash second-brain/sync-raw.sh --check" "./sync-raw.sh --check")
if [[ -n "$toplevel" ]]; then
  sync_checks+=("$toplevel/second-brain/sync-raw.sh --check" "bash $toplevel/second-brain/sync-raw.sh --check")
fi
for sync_check in "${sync_checks[@]}"; do
  if [[ "$trimmed" == "$sync_check" ]]; then
    exit 0
  fi
done

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
      read -ra words <<<"$rest"
      sub="${words[0]:-}"
      case "$sub" in
        diff|log|show|status|merge-base|rev-parse|rev-list|blame|ls-files|ls-tree|cat-file|for-each-ref)
          ;;
        grep)
          # -O and --open-files-in-pager run a program on the matches.
          for word in "${words[@]:1}"; do
            if [[ "$word" == --open-files-in-pager* || "$word" =~ ^-[^-]*O ]]; then
              deny "git grep -O/--open-files-in-pager runs a program: $segment"
            fi
          done
          ;;
        branch)
          # Listing only. A name creates a branch, and these flags change one,
          # alone or combined (-dr).
          for word in "${words[@]:1}"; do
            if [[ "$word" =~ ^-[^-]*[dDmMcCftu] ]]; then
              deny "git branch $word changes a branch: $segment"
            fi
            case "$word" in
              --delete|--move|--copy|--force|--track*|--no-track|--set-upstream-to*|--unset-upstream|--edit-description|--create-reflog)
                deny "git branch $word changes a branch: $segment"
                ;;
            esac
          done
          if [[ ${#words[@]} -gt 1 && "${words[1]}" != -* ]]; then
            deny "git branch with a name creates a branch: $segment"
          fi
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
            view|diff|list|checks) ;;
            *) deny "gh pr $action is not in the read-only allowlist: $segment" ;;
          esac
          ;;
        issue|run)
          case "$action" in
            view|list) ;;
            *) deny "gh $area $action is not in the read-only allowlist: $segment" ;;
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
