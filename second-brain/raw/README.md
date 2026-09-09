# raw/ — the memory of record

Your sources. Claude reads from here and never writes here. Everything in `wiki/`
is an interpretation of what is in this folder, and the separation is what makes
the interpretation trustworthy: you can always re-ingest from clean sources, roll
back a bad session, or change models without losing ground truth.

## repo-docs/

One pointer per narrative document in the repository root — `PLAN.md`,
`ROADMAP.md`, `CLAUDE.md`, `README.md`. Each pointer records the document's path,
a content hash, the commit it was synced at, and its section outline.

The documents are **not** copied here. Copying them would create a second store of
the same facts that silently diverges from the real file, which is what the
codebase's single-source-of-truth rule exists to prevent. The ingest reads the live
document at its repo path and uses the hash here to know whether it has changed
since the wiki was last compiled.

```sh
./sync-raw.sh            # refresh pointers, report what changed
./sync-raw.sh --check    # report only; exit 1 if the wiki is behind the docs
```

Note for anyone editing `sync-raw.sh`: pointer filenames are the lowercased
document name, so a file called `README.md` in this folder would collide with the
`readme.md` pointer on a case-insensitive filesystem. That is why this explanation
lives one level up.

## Adding a source

Anything that is not already in the repository gets a real file here, in its own
subfolder (`claude-exports/`, `meeting-notes/`, `articles/`, whatever fits). Give
each file YAML frontmatter with `source`, `date` and `topic`, then run
`/brain:ingest`.
