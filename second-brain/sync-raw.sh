#!/usr/bin/env bash
# Refresh raw/repo-docs pointers from the live documents in the repo root.
#
# The repo docs stay canonical where they are. This writes one pointer per
# document recording its path, current content hash, and section outline, so
# /brain:ingest can tell which documents changed since the last ingest without
# a second copy of the text existing anywhere.
#
# Usage: ./sync-raw.sh            report changes and update pointers
#        ./sync-raw.sh --check    report changes only, write nothing (exit 1 if stale)
set -euo pipefail

vault_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$vault_dir/.." && pwd)"
out_dir="$vault_dir/raw/repo-docs"
check_only=false
[[ "${1:-}" == "--check" ]] && check_only=true

docs=(PLAN.md ROADMAP.md CLAUDE.md README.md)
today="$(date +%F)"
stale=0

for doc in "${docs[@]}"; do
  src="$repo_dir/$doc"
  [[ -f "$src" ]] || { echo "missing: $doc"; exit 1; }

  slug="$(echo "${doc%.md}" | tr '[:upper:]' '[:lower:]')"
  pointer="$out_dir/$slug.md"
  hash="$(shasum -a 256 "$src" | cut -c1-16)"
  previous="none"
  [[ -f "$pointer" ]] && previous="$(sed -n 's/^content-hash: //p' "$pointer" | head -1)"

  if [[ "$hash" == "$previous" ]]; then
    echo "unchanged: $doc"
    continue
  fi

  stale=1
  echo "CHANGED:   $doc  ($previous -> $hash)"
  $check_only && continue

  {
    echo "---"
    echo "title: $doc (source pointer)"
    echo "type: source-pointer"
    echo "source-path: $doc"
    echo "content-hash: $hash"
    echo "commit: $(git -C "$repo_dir" rev-parse --short HEAD)"
    echo "bytes: $(wc -c < "$src" | tr -d ' ')"
    echo "synced: $today"
    echo "---"
    echo
    echo "Read the document at \`$doc\` in the repository root. It is not copied here."
    echo
    echo "## Section outline"
    echo
    awk '/^```/ {fence = !fence; next} !fence && /^#{1,3} / {printf "- L%d  %s\n", NR, $0}' "$src"
  } > "$pointer"
done

if $check_only && [[ $stale -eq 1 ]]; then
  echo
  echo "Repo docs have changed since the last sync. Run ./sync-raw.sh, then /brain:ingest."
  exit 1
fi
