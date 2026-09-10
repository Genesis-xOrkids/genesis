"""Read and clear the hosted second brain's note inbox.

A note captured on the website lands in D1 behind the Pages worker, not in the
vault - nothing served as static files can write to a git repository. `/brain:log`
uses this script to pull those notes, and marks them filed once they are in
`wiki/log.md`, so the queue drains exactly once.

Cloudflare Access authenticates the site, and a browser SSO session is not
something a command-line run has. Access issues **service tokens** for exactly
this: a client id and secret sent as headers, which Access validates and then
admits like any other request. Create one in Zero Trust -> Access -> Service
Auth, add it to the site's Access policy as an `Include -> Service Auth` rule,
and put both halves in `.env`:

    BRAIN_SITE_URL=https://genesis-brain.pages.dev
    BRAIN_ACCESS_CLIENT_ID=....access
    BRAIN_ACCESS_CLIENT_SECRET=....

Nothing here writes to the wiki. The command that called it does that, then
calls `--mark` with the ids it filed; splitting the two means a crash between
reading and writing loses nothing, because unmarked notes are simply read again.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

TIMEOUT_SECONDS = 20


def settings() -> tuple[str, dict[str, str]]:
    """The site URL and the Access service-token headers, or a usable error."""
    url = os.environ.get("BRAIN_SITE_URL", "").rstrip("/")
    client_id = os.environ.get("BRAIN_ACCESS_CLIENT_ID", "")
    client_secret = os.environ.get("BRAIN_ACCESS_CLIENT_SECRET", "")
    missing = [
        name
        for name, value in (
            ("BRAIN_SITE_URL", url),
            ("BRAIN_ACCESS_CLIENT_ID", client_id),
            ("BRAIN_ACCESS_CLIENT_SECRET", client_secret),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            f"missing {', '.join(missing)} - see the docstring in {__file__} for how to "
            "create an Access service token and where to put it"
        )
    return url, {
        "CF-Access-Client-Id": client_id,
        "CF-Access-Client-Secret": client_secret,
        "content-type": "application/json",
    }


def call(path: str, payload: dict | None = None) -> dict:
    url, headers = settings()
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url + path, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:300]
        if error.code == 403:
            raise SystemExit(
                "Access refused the service token. Check it is listed in the site's Access "
                f"policy as an Include -> Service Auth rule. ({detail})"
            ) from error
        raise SystemExit(f"{path} returned {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"could not reach {url}{path}: {error.reason}") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--mark", metavar="IDS", help="comma-separated note ids that were filed")
    args = parser.parse_args()

    if args.mark:
        ids = [int(part) for part in args.mark.split(",") if part.strip()]
        if not ids:
            raise SystemExit("--mark needs at least one id")
        print(f"marked {call('/api/notes/filed', {'ids': ids})['filed']} note(s) as filed")
        return 0

    notes = call("/api/notes")["notes"]
    if not notes:
        print("inbox is empty")
        return 0
    for note in notes:
        print(f"{note['id']}\t{note['created_at'][:10]}\t{note['text']}")
    print(
        f"\n{len(notes)} waiting. File them, then: --mark {','.join(str(n['id']) for n in notes)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
