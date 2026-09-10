# Genesis Second Brain — wiki schema

This file governs the `second-brain/` vault only. The engineering constitution for
the codebase is `../CLAUDE.md`; this file does not override it, and nothing here
applies to code outside this directory.

Read this file before writing any page in `wiki/`.

---

## 1. Project structure

```
second-brain/
├── CLAUDE.md              this file — the rules the wiki is written against
├── sync-raw.sh            refreshes raw/repo-docs pointers from the live repo docs
├── raw/                   MY sources. Claude reads, never writes.
│   └── repo-docs/         pointers to the four narrative docs in the repo root
├── wiki/                  CLAUDE's domain. Claude creates and maintains these.
│   ├── index.md           master catalog of every page
│   ├── log.md             append-only activity log
│   ├── sources/           one source-summary page per raw source
│   ├── concepts/          ideas, principles, mechanisms
│   ├── projects/          workstreams and milestones
│   ├── decisions/         choices made, alternatives considered, still-open questions
│   └── people/            dossiers on collaborators
├── journal/               daily notes (unused)
└── content/               content pipeline (unused)
```

**The load-bearing rule.** `raw/` is the memory of record and Claude never writes
into it. `wiki/` is Claude's interpretation of that record and the human reads it.
If the two are ever blurred, neither can be trusted: you lose the ability to
re-ingest from clean sources, roll back a bad session, or swap the model out.

**Repo docs are referenced, not copied.** `PLAN.md`, `ROADMAP.md`, `CLAUDE.md` and
`README.md` live in the repo root and stay canonical there. `raw/repo-docs/`
holds a pointer per document — path, the commit it was last ingested at, and its
section outline — rather than a duplicate copy. This follows the codebase's
single-source-of-truth rule: a snapshot in `raw/` would be a second copy that
silently diverges from the real document. `./sync-raw.sh` refreshes the pointers
and reports which documents changed since the last ingest.

Non-repo sources (chat exports, meeting notes, clipped articles) get their own
`raw/` subfolder and are stored as real files there, because nothing else holds them.

**`index.md`** is the catalog: every wiki page appears in it exactly once, grouped
by folder, with a one-line hook. A page missing from the index is unreachable.

**`log.md`** is append-only. Every ingest, every `/brain:log` capture, every
correction gets a dated entry. Nothing in it is ever edited or deleted.

---

## 2. Page conventions

Every page in `wiki/` opens with YAML frontmatter:

```yaml
---
title: Human-readable page title
type: concept | entity | source-summary | comparison | project | person | decision
sources: [list of raw/ files or repo paths this page is built from]
related: ["[[other-page]]", "[[another-page]]"]
created: YYYY-MM-DD
last-updated: YYYY-MM-DD
---
```

`type` extends the standard six with `decision`, because a large share of this
project's knowledge is choices with recorded alternatives, and filing those as
`concept` would lose the distinction between "how this works" and "why we picked it".

Rules for the body:

- **Atomic.** One idea per page. If a page needs the word "and" in its title to be
  accurate, it is two pages.
- **Densely linked.** Use `[[wiki-links]]` on first mention of any concept that has
  its own page. A link to a page that does not exist yet is fine — it marks work
  to do, not an error.
- **Cited.** Every non-obvious claim names its source inline, by document and
  section: `(PLAN.md §4.2)`, `(ROADMAP.md §5.1)`. A reader must be able to get from
  a sentence on a wiki page to the paragraph it came from in one hop.
- **Synthesized, not pasted.** A page that is a quote of its source adds nothing.
  Compress, connect to adjacent pages, and say what the source implies but does
  not state.
- **Reachable.** Every page is listed in `index.md` and linked from at least one
  other page.
- **Numbers stay attached to their date and source.** "21,055 products" is only
  useful next to "measured 2026-09-05, `ROADMAP.md` §2".

Heading structure inside a page: `## What it is`, then whatever the page needs,
ending with `## Open questions` where any exist.

File naming: kebab-case, no dates in filenames.

---

## 3. Style guide

- Clear, concise prose. Short sentences. No throat-clearing, no "it is important
  to note", no summary paragraph that repeats the page.
- Bullets for lists of facts; prose for reasoning. Do not bullet an argument.
- Attribute every claim. An unattributed claim on a wiki page is indistinguishable
  from a hallucination three months later.
- **Note contradictions explicitly.** When two sources disagree, say so in the
  page, name both, and do not pick a winner. Example: `ROADMAP.md` §5.1 C3 carries
  a dated correction reversing its own original acceptance metric — the page
  records both the original and the correction, not just the current answer.
- Mark uncertainty. The plan's own `[verify]` markers survive into the wiki; do
  not launder an unverified fact into a stated one.
- Distinguish built from planned. `PLAN.md` describes an intended system;
  `ROADMAP.md` §2 and Appendix A describe what actually exists. Never let a page
  imply the plan is the state of the repository.
- Present tense for what is true now; past tense with a date for what was measured.

---

## 4. Domain context

Genesis is an AI fashion platform with two halves on one shared core: a consumer
AI stylist that assembles outfits from real, purchasable items, and a deferred
enterprise trend and design studio that turns brand DNA plus market trend data
into trend reports and design mockups.

The work is done by one engineer with an AI pair, which is why the written record
matters more than usual: there is no colleague holding the context, and
`ROADMAP.md` §7 names solo-developer concentration as risk R7. The project runs on
an unusually strict engineering constitution (`../CLAUDE.md`) covering schema
design, the generated GraphQL API, agent and model rules, and a pre-ship
checklist; most day-to-day decisions are applications of it rather than fresh
choices.

As of 2026-09-05 the shared core is built and verified — schema, generated API,
one write door, model gateway, catalog boundary, hybrid search, CI, hosted
database — and the binding constraint has moved from infrastructure to two gaps:
the catalog needs breadth, and there is no user-facing surface at all. The
critical path is `C1 → C2 → C3 → S3 → A3 → A5`.

What this vault is for: keeping the reasoning behind the architecture reachable
without re-reading a 70KB plan, tracking which decisions are settled versus still
open, and making the gap between what is planned and what is built impossible to
lose track of.
