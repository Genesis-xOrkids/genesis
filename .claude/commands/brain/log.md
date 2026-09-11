---
description: Append a timestamped note to the wiki log
argument-hint: the thought or note to capture
---

Capture this into the second brain: **$ARGUMENTS**

Read `second-brain/brain.config.json` for `log.updateLinkedPages` and
`log.createNewPages`.

1. Append one entry to `second-brain/wiki/log.md`, dated with today's real date
   (check it; do not guess). Record the note in the user's own words. Add a
   sentence of context only where the note needs it to be readable in six months.
2. If `log.updateLinkedPages` is true and the note names a project, decision,
   concept or person that already has a page: fold the fact in where it belongs,
   add the `[[link]]` both ways, and bump `last-updated`.
3. If `log.createNewPages` is false (the default), do not create pages. A note
   with no home means a page is missing — say which page you would create and let
   the user decide, or leave it to the next `/brain:ingest`.
4. Never write to `raw/`.

## Notes captured in the UI

With no `$ARGUMENTS`, drain the inboxes instead of capturing something new.
There are two, because the brain has two front ends, and a note can be waiting
in either.

**The hosted site.** Run `uv run scripts/brain_inbox.py`. It prints one note per
line as `id`, capture date, text — reaching D1 through `wrangler`, so it needs
nothing configured beyond the Cloudflare login already on the machine. Append
each note to `wiki/log.md` under its own capture date — not today's — then mark
exactly the ones you filed:

```sh
uv run scripts/brain_inbox.py --mark 3,4,7
```

Mark after writing, never before. The two steps are separate so that a failure
between them leaves the notes queued rather than lost, and re-running simply
reads them again.

**The Claude artifact.** If `ui.artifactUrl` is set, read the `inbox` collection
from that artifact with the Artifact tool (`action: "read_db"`, `db_op: "list"`),
append every note whose `status` is `pending`, then `write_db` each one back with
`status: "logged"`.

Report how many you drained from each. If a source cannot be reached — wrangler
not logged in, or no `ui.artifactUrl` — say so rather than reporting zero, since
"nothing waiting" and "could not look" are different answers.

Confirm in one line what you appended and which pages you touched.
