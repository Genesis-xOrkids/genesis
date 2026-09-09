---
title: Activity log
type: entity
sources: []
related: ["[[index]]"]
created: 2026-09-07
last-updated: 2026-09-08
---

Append-only. Nothing here is edited or deleted.

---

## 2026-09-07 — vault created

Built `second-brain/` at the repository root: `raw/`, `wiki/`, the schema in
`second-brain/CLAUDE.md`, and four slash commands under
`.claude/commands/brain/` (`/brain:ingest`, `/brain:query`, `/brain:lint`,
`/brain:log`).

Two adaptations from the standard pattern, both recorded in the schema:

- **Repo docs are referenced, not copied.** `raw/repo-docs/` holds a pointer per
  document — path, content hash, commit, section outline — rather than a snapshot,
  because a snapshot would be a second copy of the same facts that silently
  diverges from the canonical file. `sync-raw.sh` refreshes the pointers and
  `--check` reports staleness.
- **Commands are namespaced under `brain/`** and live at the repo root rather than
  in the vault, so they are available from the working directory the project is
  actually used from, and so `/lint` does not collide with the code linting this
  repo already means by that word.

## 2026-09-07 → 2026-09-08 — first ingest, 4 sources

Sources processed: `PLAN.md`, `ROADMAP.md`, `CLAUDE.md`, `README.md` — all four
repo docs, read live at their repository paths.

**38 pages created**, 0 updated:

- 4 source summaries
- 7 projects — one per roadmap workstream, plus `current-state` and `risk-register`
- 8 decisions
- 19 concepts

**Contradictions recorded rather than resolved**, per the style guide:

- *Default model platform.* PLAN.md §1 names Claude Platform on AWS; README.md
  names `anthropic_api`. Both current. Recorded on [[model-platform]].
- *Database.* PLAN.md §3.2 specifies Aurora Serverless v2 and lists Neon as a
  rejected alternative; README.md documents Neon as the hosted database in use.
  Recorded on [[database-choice]].
- *C3 acceptance metric.* ROADMAP.md §5.1 carries a dated in-place correction
  (2026-09-06) reversing its own original metric. Both the original and the
  correction are on [[hybrid-catalog-search]] and [[evals-as-gates]], because the
  reason the first metric was wrong is the more useful half.
- *Embeddings status.* ROADMAP.md §2 lists embeddings as not built; commits
  `ff2b5fa` and `367058a` shipped them. Noted on [[current-state]].

**Folded in from existing project memory** (two findings measured 2026-09-05 that
post-date ROADMAP.md and appear in no source document): the C2 breadth shortfall
against its four targets, on [[catalog-supply]]; and the colourway duplication and
free-items-first fallback ordering in search, on [[hybrid-catalog-search]].

**Not done:** `people/` is empty by design — no source names an individual.
`journal/` and `content/` are scaffolded and unused; no command writes to them.

## 2026-09-08 — UI, and settings that are actually read

Published a console over the wiki:
`https://claude.ai/code/artifact/300f6188-199b-426c-be42-4adf58c57296`

It reads the 40 compiled pages, draws the 212 cross-links as a force-directed
graph, and renders any page with its links live. Three things in it are real
rather than displays:

- **Settings** edit `brain.config.json`, and all four commands were rewritten to
  read that file — batch size, which `raw/` folders are in scope, the lint checks,
  the staleness threshold, citation strictness, the frontmatter contract, query
  breadth. A setting nothing reads was not added.
- **Captured notes** land in the artifact's store; `/brain:log` with no arguments
  drains the inbox into this file and marks each note logged.
- **Queued runs** record the request and hand over the command. They cannot
  execute locally, and the panel says so rather than implying otherwise.

`ui.artifactUrl` in `brain.config.json` is how the commands find the inbox.
