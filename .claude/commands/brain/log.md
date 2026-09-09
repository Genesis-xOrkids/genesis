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

If `ui.artifactUrl` is set and no `$ARGUMENTS` were given, drain the UI inbox
instead: read the `inbox` collection from that artifact with the Artifact tool
(`action: "read_db"`, `db_op: "list"`), append every note whose `status` is
`pending` to `wiki/log.md` under its own capture date, then `write_db` each one
back with `status: "logged"`. Report how many you drained.

Confirm in one line what you appended and which pages you touched.
