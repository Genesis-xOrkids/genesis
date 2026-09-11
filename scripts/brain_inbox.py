"""Read and clear the hosted second brain's note inbox.

A note captured on the website lands in D1 behind the Pages worker, not in the
vault - nothing served as static files can write to a git repository.
`/brain:log` uses this script to pull those notes, and marks them filed once
they are in `wiki/log.md`, so the queue drains exactly once.

This talks to D1 through `wrangler`, which reaches the Cloudflare API with the
login already on the machine. The obvious alternative was to call the site's own
`/api/notes` over HTTPS, but that path runs through Cloudflare Access, and a
command line has no browser session - it would need an Access service token
created, added to the site's policy, and kept in three environment variables.
Going straight to the database needs none of that. The HTTPS version is in git
history if this ever has to run somewhere without wrangler.

Nothing here writes to the wiki. The command that called it does that, then
calls `--mark` with the ids it filed; splitting the two means a crash between
reading and writing loses nothing, because unmarked notes are simply read again.
"""

import argparse
import json
import subprocess
import sys

DATABASE = "genesis-brain"
TIMEOUT_SECONDS = 60


def query(sql: str) -> list[dict]:
    """Run one statement against the remote database and return its rows."""
    command = [
        "npx",
        "--yes",
        "wrangler",
        "d1",
        "execute",
        DATABASE,
        "--remote",
        "-y",
        "--json",
        "--command",
        sql,
    ]
    try:
        finished = subprocess.run(
            command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False
        )
    except FileNotFoundError as error:
        raise SystemExit("npx is not on PATH; install Node to reach the database") from error
    except subprocess.TimeoutExpired as error:
        raise SystemExit(f"wrangler did not answer within {TIMEOUT_SECONDS}s") from error

    if finished.returncode != 0:
        detail = (finished.stderr or finished.stdout).strip()[:400]
        if "credential" in detail.lower() or "authent" in detail.lower():
            raise SystemExit(f"wrangler is not authenticated - run `npx wrangler login`.\n{detail}")
        raise SystemExit(f"wrangler failed:\n{detail}")

    # `--json` prints a list with one entry per statement. Anything else means
    # the output shape changed, and guessing at it would be worse than stopping.
    try:
        payload = json.loads(finished.stdout)
    except json.JSONDecodeError as error:
        raise SystemExit(f"could not parse wrangler output:\n{finished.stdout[:400]}") from error
    if not isinstance(payload, list) or not payload:
        raise SystemExit(f"unexpected wrangler output: {finished.stdout[:200]}")
    first = payload[0]
    if not first.get("success", False):
        raise SystemExit(f"the query failed: {first}")
    return first.get("results") or []


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
