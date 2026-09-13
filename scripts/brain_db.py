"""The hosted brain's database, reached the way a command line can reach it.

D1 sits behind the Pages worker, and the worker sits behind Cloudflare Access.
A browser has an Access session; a command line does not, so calling the site's
own `/api/...` endpoints from a script would mean an Access service token
created, added to the site's policy, and kept in three environment variables.
`wrangler` reaches the database directly with the Cloudflare login already on
the machine, or with `CLOUDFLARE_API_TOKEN` where there is no login, and needs
none of that.

A cloud session has no login to use, and no machine to keep one on. There the
statement goes straight to D1's HTTP API with no key of its own: Claude Code's
agent proxy attaches the Cloudflare token stored as the cloud environment's API
credential for `api.cloudflare.com`, so the token never reaches the session.
The environment sets `CLOUDFLARE_ACCOUNT_ID`; the database id is the site's.

This is the one place that knows how to run a statement, so the scripts that
read and write the brain's tables - the note inbox and live agent activity -
share the adapter rather than each carrying a copy of it.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import tomllib
import urllib.error
import urllib.request
from typing import Any

DATABASE = "genesis-brain"
TIMEOUT_SECONDS = 60
WRANGLER_TOML = pathlib.Path(__file__).resolve().parents[1] / "second-brain/site/wrangler.toml"


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


def stamp(moment: dt.datetime) -> str:
    """A timestamp as everything writing to the brain writes one: UTC, to the second, ISO 8601.

    The worker writes the same shape, so a time written from the page and one
    written from here sort and compare as text.
    """
    return moment.astimezone(dt.UTC).isoformat(timespec="seconds")


def query(sql: str) -> list[dict[str, Any]]:
    """Run one statement against the remote database and return its rows."""
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        return _query_over_https(sql)
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
    return list(first.get("results") or [])


def _query_over_https(sql: str) -> list[dict[str, Any]]:
    """Run one statement through D1's HTTP API, as a cloud session must."""
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not account:
        raise SystemExit("CLOUDFLARE_ACCOUNT_ID is not set on this cloud environment")
    database_id = tomllib.loads(WRANGLER_TOML.read_text())["d1_databases"][0]["database_id"]
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{database_id}/query",
        data=json.dumps({"sql": sql}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read()[:400].decode(errors="replace")
        raise SystemExit(f"D1 refused the query ({error.code}): {detail}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise SystemExit(f"could not reach D1: {error}") from error

    results = payload.get("result") if isinstance(payload, dict) else None
    if not payload.get("success") or not isinstance(results, list) or not results:
        raise SystemExit(f"the query failed: {str(payload)[:400]}")
    first = results[0]
    if not first.get("success", False):
        raise SystemExit(f"the query failed: {first}")
    return list(first.get("results") or [])
