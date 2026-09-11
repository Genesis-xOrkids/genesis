"""The hosted brain's database, reached the way a command line can reach it.

D1 sits behind the Pages worker, and the worker sits behind Cloudflare Access.
A browser has an Access session; a command line does not, so calling the site's
own `/api/...` endpoints from a script would mean an Access service token
created, added to the site's policy, and kept in three environment variables.
`wrangler` reaches the database directly with the Cloudflare login already on
the machine and needs none of that.

This is the one place that knows how to run a statement, so that the scripts
which read and write the brain's tables - the note inbox, the agent run ledger -
share the adapter rather than each carrying a copy of it.
"""

from __future__ import annotations

import json
import subprocess

DATABASE = "genesis-brain"
TIMEOUT_SECONDS = 60


def literal(value: str) -> str:
    """One SQLite string literal, quoted so its content cannot become syntax.

    `wrangler d1 execute` takes a statement and no parameters, so values are
    written into the SQL rather than bound beside it. Doubling the quote is
    SQLite's own escape and is what makes that safe; a NUL would end the string
    early whatever the quoting, so it is refused rather than escaped.
    """
    if "\x00" in value:
        raise SystemExit("a value contains a NUL byte, which cannot be stored")
    return "'" + value.replace("'", "''") + "'"


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

    # `--json` prints a list with one entry per statement, and prints its banner
    # to stderr, so stdout is the payload and nothing else. Anything else means
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
    results = first.get("results") or []
    return list(results)
