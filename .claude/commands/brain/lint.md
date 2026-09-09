---
description: Health-check the wiki — broken links, orphans, missing frontmatter, staleness
---

Health-check `second-brain/wiki/`. Read `second-brain/CLAUDE.md` for the rules and
`second-brain/brain.config.json` for which checks are on. **Run only the checks
whose flag under `lint.checks` is true**, and say at the end which were skipped.

This command reads and reports; it does not fix.

| Check (`lint.checks` key) | What it finds |
|---|---|
| `brokenLinks` | A `[[wiki-link]]` with no matching page. Report the target and every page pointing at it. Say whether it is a dead link or a deliberate forward reference. |
| `orphans` | A page no other page links to, or a page missing from `index.md`. |
| `indexDrift` | An `index.md` entry with no page; a page on disk missing from the index; a page listed twice. |
| `frontmatter` | Any field in `schema.requiredFrontmatter` missing or empty; a `type` outside `schema.allowedTypes`. |
| `uncitedClaims` | Specific numbers, dates or targets with no inline citation, at the level `style.citationStrictness` demands. Report page and claim. |
| `sourceDrift` | Run `second-brain/sync-raw.sh --check`. Any changed document means the pages built from it are stale; list them. |
| `staleness` | Pages whose `last-updated` is older than `lint.staleAfterDays` days. |
| `contradictions` | Two pages asserting incompatible facts. Quote both. |

Also flag any page exceeding `style.maxPageWords`.

Report as a structured list grouped by check, most severe first, with a file path
and line for each finding. End with a count per category and the list of skipped
checks.

Then stop and ask which findings to fix. Do not edit anything without an answer.
