---
title: Activity log
type: entity
sources: []
related: ["[[index]]"]
created: 2026-09-07
last-updated: 2026-09-10
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

## 2026-09-10 — hosted site gains real storage, and the first note drains

The second brain now has a second front end: `genesis-brain.pages.dev`, behind
Cloudflare Access, with Ask, Capture and Settings working rather than dropped.
Capture and Settings had shipped on `localStorage`, which was a workaround for a
static file having nowhere to write — a note lived in one browser and never
reached the vault. Both now go to a D1 database behind the Pages worker, so the
inbox is shared across devices and durable. Ask calls Claude from the edge with a
key held as a Cloudflare secret; every endpoint refuses without an Access
assertion, which makes "the site must not go up without Access" enforced rather
than written down.

**Captured note, filed from the hosted inbox:** ten more registered storefronts
should clear every C2 target — twelve of twenty candidates probed ingestible.
This is the first note to travel the full path: typed on the website, stored in
D1, read by `scripts/brain_inbox.py`, and written here. It restates what
[[catalog-supply]] already records as the C2 shortfall (21,055 of 25,000
products, 34 of 50 brands, measured 2026-09-05) and adds the estimate that ten
more storefronts closes it.

The drain reaches D1 through `wrangler`, not through the site's own HTTPS
endpoint. Going over HTTPS would have meant an Access service token created,
added to the site's policy, and kept in three environment variables; wrangler
uses the Cloudflare login already on the machine and needs none of it.

## 2026-09-12 — the agent network

Recorded as [[agent-network]]: the employees that work on this repository, how a
task reaches them, and where their runs are recorded.

What it covers, built across PRs #31, #35, #37, #38, #40 and #41:
- a site that verifies the Access token itself;
- one set of hooks recording every agent's runs live in D1;
- a dispatch queue that a watcher on the agents' machine turns into dispatcher
  sessions, each in a worktree of its own.

#38 merged before its review fixes. #41 carries them, plus a defect in the
worktree base that only a live run showed: a worktree made from `origin/main`
lacked the dispatcher that the unmerged change added.

The roster's last three agents are new: `brain-librarian`, `catalog-steward` and
`eval-runner`. The reviewer now has eight eval cases scored by a script, not by a
model.

Still open: whether scheduled agents run as cloud routines or through the queue
on the agents' machine. Routines need credentials configured in a cloud
environment; the queue needs the machine awake.

## 2026-09-13 — the agent network, after review

A correction to the entry above: scheduled agents run as cloud routines, decided
on 2026-09-12, because they must run while the agents' machine is asleep.
[[agent-network]] records it.

PRs #40, #41 and #42 merged. The dispatch watcher is installed on the agents'
machine, and a test task went from the queue to finished in 47 seconds.

Reviewing #42 after it merged found that the librarian marked notes and runs done
in D1 before pushing them, so a failed push in a cloud session would have lost
them for good. Writing the ledger is now a separate step from marking it, the
librarian marks only after its pull request is pushed, and in a cloud session the
marking commands refuse to run until the files are pushed.

The same review found three agents without eval suites, and an eval target
widened after a run. A seeded regression now shows the reviewer's suite fails a
reviewer that ignores the Data rules ([[evals-as-gates]]).

## 2026-09-16 — a plan for the agent network, and a smaller roster

`docs/agent-network-plan.md` (#46) measures the network and plans its next
shape: a lead that plans a task and sees it through, a verifier that
demonstrates acceptance criteria, and cost recorded per run. [[agent-network]]
records the network as each step lands.

Removed before either ever ran: `brain-librarian` and `catalog-steward`, with
their scripts `catalog_health.py` and `app_sql.py`. The librarian's inbox had
received one note since it opened, and ten runs were waiting for the ledger. The
steward reported the freshness of an ingestion nothing schedules, and measured
none of C2's targets.

Checked live, correcting what the repository said: a subagent can start agents
of its own, and `isolation: worktree` gives an agent a checkout made from
`origin/main` that Claude Code keeps out of the main checkout. The build loop
stays with its caller, now for independence alone.

Of the ten reviewer runs recorded since 2026-09-11, four were cut off by the
subscription's session limit, and a fifth failed on a billing error on
2026-09-13. Nothing had recorded that fifth run's end, so it was closed by hand
at the moment it failed.

## 2026-09-28 — the eval-runner removed, the suite capped and priced

`eval-runner` never ran in the fifteen days after it was added. It chose a
suite, ran one command and relayed the table that command prints, and every
eval on record - the reviewer's first run, the seeded regression, #48's 8/8 -
ran the command directly. Nothing started it: the trigger on pull requests was
only planned. The suites stay; the builder's eval step now picks them.

The suite's own cost was the real exposure: eight Opus sessions at once, with
nothing recording what they spent. `evals/agents/run.py` now runs three at a
time and prices each case from its transcript ([[evals-as-gates]]). The price
table has no entry for `claude-opus-5-5`, the model the reviewer runs on, so
those cases show tokens with "no price" until one is added.

## 2026-09-28 — search fills its page, and a browse stops leading with free items

PR #63 closes both retrieval defects [[hybrid-catalog-search]] had listed as
live since 2026-09-05:

- **Short pages.** Colourway folding now runs over every candidate, so a folded
  colourway is replaced by the next distinct style instead of leaving a gap.
- **The filters-only fallback.** It no longer orders by price. It puts known in
  stock first, then lets brands take turns, then shows newest to the catalog
  first.

The same PR shows a product's best-stocked offer before its cheapest.
[[catalog-supply]] no longer calls the colourway defect open.

Review found that newest-first alone meant "most recently onboarded storefront
first", because a storefront is ingested in one transaction. That finding is
where the brand turns come from. Category precision has not been re-measured on
the hosted catalog since the change.

## 2026-09-28 — colourway counts come from the catalog

A second review of PR #63 found that brand turns spread one style's colourways
across the candidate window. A 12-colourway style reported 4 in a broad browse
and 11 when filtered to its brand. `other_colourways` is now counted in the
catalog under the search's filters, with one query per page, rather than among
the candidates ([[hybrid-catalog-search]]). A search now costs one query more.
The index hook for that page also stopped saying "BM25" (the lexical ranker is
Postgres `ts_rank`) and "eight distinct styles" (two colourways of a style can
share a page).

## 2026-09-28 — C2's size gap, measured rather than read

[[catalog-supply]] had called the cause of C2's size gap a reading, not a
measurement: one-size items shipping as `Default Title`. A label-by-label pass
over every registered storefront's feed (PR #64) found it was mostly labels the
parser could not read, and that `Default Title` states no size at all. The page
now carries the measured shapes and what is left: sizes in systems the enum
does not have.

## 2026-09-29 — only apparel enters the catalog, and C2's category gap closes

The user decided on 2026-09-27 that records which are not fashion items are
rejected at the connector boundary, conservatively: a title must name a
non-apparel item, and anything naming a garment keeps the record. PR #66
implements the rule for every connector. The ingest run that rejects a record
also removes the products earlier runs wrote for it, so no separate cleanup is
needed. The same PR completes the category vocabulary against the existing
enum. Recorded on [[catalog-sources]], with the measured effect on
[[catalog-supply]]: 85.4% to 98.0% of products categorised on a 27-storefront
sample ingested end to end, ~98.5% estimated for the hosted catalog after a
re-ingest. Hair accessories and Rothy's model-name titles are left null and
listed on [[open-decisions]].

## 2026-09-29 — bath and towel wraps are garments; removal guards corrected

Bath and towel wraps are worn, so under the 2026-09-27 rule they are kept, as
sleepwear ([[catalog-sources]]). Review of PR #66 also found the page overstated
what in-run removal protects: it guarded offers from other writers but not
long-tail attributes a person or a model added, which cascade with the product.
The guard now covers both, and the page says what `_retire_sizes` actually rests
on: only the size rows of offers the same run has just written, since size rows
record no provenance.
