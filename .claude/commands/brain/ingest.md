---
description: Compile new and changed sources in second-brain/raw into the wiki
argument-hint: "[max sources to process, overrides ingest.batchSize]"
---

Compile sources from `second-brain/raw/` into `second-brain/wiki/`.

Read two files before writing anything:

1. `second-brain/CLAUDE.md` — the schema every page is written against.
2. `second-brain/brain.config.json` — the settings below. Honor them; do not
   substitute your own defaults.

| Setting | Effect |
|---|---|
| `ingest.batchSize` | How many sources to process this run. $ARGUMENTS overrides it. |
| `ingest.sources` | Which `raw/` subfolders are in scope. Ignore folders not listed. |
| `ingest.reingestChangedDocs` | When true, a source whose content hash moved is re-processed, not just new ones. |
| `ingest.createPagesFor` | Which page types this ingest may create. Never create a type absent from this list. |
| `schema.requiredFrontmatter`, `schema.allowedTypes` | The frontmatter contract for every page you write. |
| `style.citationStrictness` | `strict`: every non-obvious claim carries an inline `(DOC §N)` citation. `normal`: section-level. `loose`: page-level. |
| `style.recordContradictions` | When true, disagreeing sources are written into the page with both named, never resolved silently. |
| `style.maxPageWords` | Split a page that exceeds this rather than letting it sprawl. |

## Select the work

1. Run `second-brain/sync-raw.sh` to refresh the repo-doc pointers. It prints
   which documents changed since the last ingest.
2. Build the queue: every source under an `ingest.sources` folder with no
   source-summary page in `wiki/sources/`, plus — if `reingestChangedDocs` — every
   repo doc whose `content-hash` moved.
3. Take `ingest.batchSize` sources ($ARGUMENTS wins if given). Thoroughly, not
   quickly: a shallow pass over twenty sources is worth less than a real pass over
   five. If the queue is empty, say so and stop; do not invent work.

## For each source

- Read it in full. Repo docs are read at their live path in the repository root
  (`PLAN.md`, `ROADMAP.md`, ...), not from `raw/` — `raw/repo-docs/` holds pointers
  only, and writing into `raw/` is never permitted.
- Write or update its page in `wiki/sources/`: what the document is, what it
  decides, its section map, and what it is silent on.
- Extract the concepts, projects, decisions and people it carries into their own
  atomic pages, subject to `ingest.createPagesFor`. Update an existing page rather
  than creating a near-duplicate; check `wiki/index.md` before creating anything.
- Cross-link with `[[wiki-links]]` on first mention, both directions.

## Before finishing

- Never let a page imply the plan is the state of the repository. `PLAN.md`
  describes intent; `ROADMAP.md` §2 and Appendix A describe what exists.
- Update `wiki/index.md` so every page appears exactly once with a one-line hook.
- Append one dated entry to `wiki/log.md`: sources processed, pages created, pages
  updated, anything you deliberately did not do.
- If `ui.artifactUrl` is set, the UI's queued actions live in that artifact's
  database. Read `queue` with the Artifact tool (`action: "read_db"`, `db_op:
  "list"`) and mark any ingest request you just satisfied as `done` with
  `write_db`.
- Report the counts. If you skipped a source, say which and why.
