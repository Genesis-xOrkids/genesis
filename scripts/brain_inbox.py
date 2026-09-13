"""Read and clear the hosted second brain's note inbox.

A note captured on the website lands in D1 behind the Pages worker, not in the
vault - nothing served as static files can write to a git repository.
`/brain:log` uses this script to pull those notes, and marks them filed once
they are in `wiki/log.md`, so the queue drains exactly once.

This talks to D1 through `scripts/brain_db.py`, which holds the wrangler adapter
and the reasoning for reaching the database directly rather than through the
site's own HTTPS endpoints. Run it as a module from the repository root, so that
import resolves: `python3 -m scripts.brain_inbox`.

Nothing here writes to the wiki. The command that called it does that, then
calls `--mark` with the ids it filed; splitting the two means a crash between
reading and writing loses nothing, because unmarked notes are simply read again.
"""

import argparse
import pathlib
import sys

from scripts.brain_db import query
from scripts.pushed import require_pushed

LOG = pathlib.Path(__file__).resolve().parents[1] / "second-brain/wiki/log.md"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--mark", metavar="IDS", help="comma-separated note ids that were filed")
    args = parser.parse_args()

    if args.mark:
        # Parsed as integers before they reach the statement, so a note id is
        # never a way to send SQL.
        try:
            ids = [int(part) for part in args.mark.split(",") if part.strip()]
        except ValueError as error:
            raise SystemExit(f"--mark takes note ids, not {args.mark!r}") from error
        if not ids:
            raise SystemExit("--mark needs at least one id")
        # In a cloud session the log is only kept once it is pushed; a note marked
        # before then would be lost with the checkout.
        require_pushed(LOG)
        listed = ",".join(str(number) for number in ids)
        query(
            "UPDATE notes SET filed_at = datetime('now') "
            f"WHERE id IN ({listed}) AND filed_at IS NULL"
        )
        remaining = query("SELECT count(*) AS n FROM notes WHERE filed_at IS NULL")
        print(f"marked {len(ids)} note(s) filed; {remaining[0]['n']} still waiting")
        return 0

    notes = query(
        "SELECT id, text, created_at FROM notes WHERE filed_at IS NULL ORDER BY created_at"
    )
    if not notes:
        print("inbox is empty")
        return 0
    for note in notes:
        # Tabs and newlines would break one note across lines; the reader needs
        # one row per note to match ids to text.
        text = note["text"].replace("\t", " ").replace("\n", " ⏎ ")
        print(f"{note['id']}\t{note['created_at'][:10]}\t{text}")
    listed = ",".join(str(note["id"]) for note in notes)
    print(f"\n{len(notes)} waiting. File them, then: --mark {listed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
