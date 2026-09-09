---
description: Answer a question from the compiled wiki, with citations
argument-hint: the question to answer
---

Answer this question from the second brain: **$ARGUMENTS**

Read `second-brain/brain.config.json` first:

- `query.maxPagesRead` — the cap on how many wiki pages to open for one question.
  Choose the most relevant ones rather than reading broadly up to the cap.
- `query.citeEveryClaim` — when true, every claim carries its `[[page-name]]`.
  A claim you cannot attribute does not belong in the answer; say the wiki does
  not cover it instead.
- `query.proposeUpdates` — when true, a connection the wiki does not record is
  proposed in one or two lines and **asked about**, never written. When false,
  answer and stop.

Then:

1. Read `second-brain/wiki/index.md`, then the pages it points to that bear on the
   question. Read the pages, not just their titles.
2. Answer from the wiki, within the citation policy above.
3. If pages disagree, present both and name them. Do not average them into a
   single confident answer.
4. If the wiki is stale relative to its sources — a page cites `ROADMAP.md` §2 but
   the roadmap has moved — say so and suggest `/brain:ingest` rather than
   answering from the stale page. `sync-raw.sh --check` settles it.

Never write during a query. Answer in prose; length follows the question.
