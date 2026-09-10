#!/usr/bin/env python3
"""Build the second brain into a single self-contained page.

Two targets from one set of templates, so the hosted site and the Claude
artifact cannot drift apart:

    ./build.py --target static     dist/index.html, for Cloudflare Pages
    ./build.py --target artifact   dist/artifact.html, to publish as an Artifact

Both targets carry every panel. What differs is only where a setting, a note
or a question goes: the Claude viewer supplies db, sample and downloads at
runtime, and the hosted site has localStorage, a real file download, and an
Ask endpoint in _worker.js that calls Claude with a key held at the edge. The
panels call five adapter functions and never learn which build they are in.

The static target also applies exclude.txt, which decides what leaves this
machine, and emits _worker.js and _headers alongside the page.
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
VAULT = ROOT.parent
REPO = VAULT.parent
TPL = ROOT / "template"
DIST = ROOT / "dist"

# The roster reads the same agent frontmatter the GitHub generator translates,
# and a second copy of that parser here would be the duplication the roster is
# built to expose. This runs from a hyphenated directory, so the repository root
# goes on the path before the import rather than through a package name.
sys.path.insert(0, str(REPO))

from scripts.agent_definitions import split_frontmatter  # noqa: E402, I001


SECURITY_HEADERS = {
    "X-Robots-Tag": "noindex, nofollow, noarchive, nosnippet",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), interest-cohort=()",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'unsafe-inline'; "
        "style-src 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src data:; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
}


def render_worker() -> str:
    """The static site's worker: security headers, and the Ask endpoint.

    Ask needs a model call, and the browser cannot make one without holding a
    key. On the artifact the Claude viewer supplies `sample()`; here the call
    happens at the edge with a key stored as a Cloudflare secret, which is the
    only place on this path a key can live without shipping to the reader.

    This is a second place that calls a model, which the engineering
    constitution otherwise routes through `ModelGateway`. That rule cannot
    reach here - the gateway is Python and this is edge JavaScript - and the
    reasons behind it (per-tenant routing, cost attribution, guardrails) are
    about the product, not about a reader asking a question of a wiki. The
    exception is deliberate and stops at this file.
    """
    headers = json.dumps(SECURITY_HEADERS, indent=2)
    return (TPL / "worker.js").read_text().replace("__SECURITY_HEADERS__", headers)


def read_pages() -> list[dict]:
    pages = []
    for path in sorted((VAULT / "wiki").rglob("*.md")):
        if path.name == "README.md":
            continue
        text = path.read_text()
        match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
        if not match:
            raise SystemExit(f"{path}: no frontmatter")
        fm = dict(line.split(": ", 1) for line in match.group(1).split("\n") if ": " in line)
        body = match.group(2).strip()
        pages.append(
            {
                "slug": path.stem,
                "title": fm.get("title", path.stem).strip(),
                "type": fm.get("type", "concept").strip(),
                "folder": path.parent.name if path.parent.name != "wiki" else "root",
                "path": str(path.relative_to(VAULT.parent)),
                "sources": [
                    s.strip() for s in fm.get("sources", "").strip("[]").split(",") if s.strip()
                ],
                "created": fm.get("created", "").strip(),
                "updated": fm.get("last-updated", "").strip(),
                "links": sorted(set(re.findall(r"\[\[([^\]|]+)", body))),
                "words": len(body.split()),
                "body": body,
            }
        )
    return pages


def read_excludes() -> set[str]:
    excluded = set()
    for line in (ROOT / "exclude.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            excluded.add(line)
    return excluded


def redact(body: str, excluded: set[str]) -> str:
    """Drop catalog lines that summarise a held-back page.

    An index entry like `- [[unit-economics]] - margins and the cost levers`
    describes the page it points at, so dropping the page and keeping the line
    publishes the summary. Prose mentions are left alone: they render as plain
    text and reading around them is the point of a cross-linked wiki.
    """
    kept = []
    for line in body.split("\n"):
        m = re.match(r"^\s*[-*]\s+\[\[([^\]|]+)", line)
        if m and m.group(1) in excluded:
            continue
        kept.append(line)
    return "\n".join(kept)


def residual(pages: list[dict], excluded: set[str]) -> list[tuple[str, str]]:
    """Mentions of held-back pages that survive redaction, for the build report."""
    out = []
    for p in pages:
        held = {link for link in re.findall(r"\[\[([^\]|]+)", p["body"]) if link in excluded}
        out.extend((p["slug"], slug) for slug in sorted(held))
    return out


def strip_blocks(text: str, keep: str, open_fmt: str, close: str) -> str:
    """Keep blocks labelled `keep`, drop the rest, remove the markers."""
    pattern = re.compile(
        re.escape(open_fmt).replace(r"\{\}", r"(\w+)") + r"(.*?)" + re.escape(close),
        re.S,
    )
    return pattern.sub(lambda m: m.group(2) if m.group(1) == keep else "", text)


# ---------- employees ----------
#
# An employee is anything that does work in this repository under its own name.
# Two kinds are defined here and read from the definition file Claude Code
# itself reads, so a role in the gallery cannot drift from the role the employee
# actually has. The third is not defined in this repo at all, and is derived
# from the commits it signed, because that is the only record of it a build
# running offline can see.

KIND_ORDER = {"agent": 0, "command": 1, "service": 2}
KIND_ICON = {"agent": "\N{ROBOT FACE}", "command": "\N{GEAR}", "service": "\N{ELECTRIC PLUG}"}
COMMIT_SEP, FIELD_SEP = "\x1e", "\x1f"


def role_line(description: str) -> str:
    """The one-line role: the description up to its first sentence break."""
    return re.split(r"(?<=[.!?])\s", description.strip(), maxsplit=1)[0] if description else ""


def pointer_field(text: str, key: str) -> str:
    """One `key: value` line from a synced document's header, "" if absent."""
    found = re.search(rf"^{key}: (.*)$", text, re.M)
    return found.group(1) if found else ""


def git_log(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), "log", *args], capture_output=True, text=True
    ).stdout


def read_commits(revs: str) -> list[dict]:
    """Commits over `revs`, each attributed to the actor that made it.

    Attribution follows what git actually records rather than what we wish it
    did: a bot commits under its own author name, and Claude's work is signed
    with a `Co-Authored-By` trailer on a commit authored by the human who ran
    the session. A commit with neither is the human working alone, and is not
    an employee's.
    """
    fmt = COMMIT_SEP + FIELD_SEP.join(["%h", "%an", "%ad", "%s", "%b"])
    commits = []
    for record in git_log("--date=short", f"--format={fmt}", revs).split(COMMIT_SEP):
        if not record.strip():
            continue
        sha, author, date, subject, body = (record.split(FIELD_SEP) + [""] * 5)[:5]
        trailer = re.search(r"^co-authored-by:[ \t]*([^<]+)", body, re.M | re.I)
        commits.append(
            {
                "sha": sha,
                "actor": author
                if author.endswith("[bot]")
                else trailer.group(1).strip()
                if trailer
                else author,
                "human": author,
                "date": date,
                "subject": subject.strip(),
            }
        )
    return commits


def read_log_entries() -> list[dict]:
    """Dated entries from the vault's append-only activity log.

    `log.md` is already the ledger for everything the brain commands do, so the
    gallery reads it rather than starting a second one — the same reason
    `raw/repo-docs` holds pointers instead of copies.
    """
    text = (VAULT / "wiki/log.md").read_text()
    entries = []
    parts = re.split(r"^## (.+)$", text, flags=re.M)[1:]
    for heading, body in zip(parts[::2], parts[1::2], strict=True):
        date = re.search(r"\d{4}-\d{2}-\d{2}", heading)
        if not date:
            continue
        title = heading.split("—", 1)[-1].strip() if "—" in heading else heading.strip()
        entries.append({"date": date.group(0), "title": title, "body": body})
    return entries


def read_runs() -> list[dict]:
    """The agent run ledger: runs that leave no commit behind.

    A read-only agent cannot commit and cannot write, so nothing in git or the
    wiki records that it ran. `scripts/log_agent_run.py` is the one writer of
    this file; see its docstring for why the record lives here and not in the
    wiki's activity log.
    """
    path = REPO / ".claude/runs.tsv"
    if not path.exists():
        return []
    runs = []
    for number, line in enumerate(path.read_text().splitlines()[1:], start=2):
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != 4:
            raise SystemExit(f"{path}:{number}: expected 4 tab-separated fields, got {len(fields)}")
        run_at, agent, target, outcome = fields
        runs.append(
            {
                "date": run_at[:10],
                "agent": agent,
                "what": f"{target} — {outcome}",
                "ref": "",
                "via": "run",
            }
        )
    return runs


def read_employees(excluded: set[str]) -> list[dict]:
    """The roster, generated from the files that define each employee.

    Definitions are the single source of truth for who exists and what they do;
    git and `log.md` are the single source of truth for what they have done.
    Nothing about an employee is written down twice, so nothing can disagree.

    `excluded` is honoured here for the same reason `redact` honours it: an
    entry title describes the log entry it came from, so shipping the titles of
    a held-back `log` would publish the page a line at a time.
    """
    commits = read_commits("main")
    ahead = read_commits("main..HEAD")
    entries = [] if "log" in excluded else read_log_entries()
    ledger = read_runs()
    humans = {
        c["human"] for c in commits if c["actor"] == c["human"] and not c["human"].endswith("[bot]")
    }

    staff: list[dict] = []
    for path in sorted((REPO / ".claude/agents").glob("*.md")):
        fm = split_frontmatter(path.read_text())
        staff.append(
            {
                "id": fm.get("name", path.stem),
                "kind": "agent",
                "invoke": fm.get("name", path.stem),
                "role": role_line(fm.get("description", "")),
                "detail": fm.get("description", ""),
                "icon": fm.get("icon", ""),
                "model": fm.get("model", ""),
                "effort": fm.get("effort", ""),
                "can": [t.strip() for t in fm.get("tools", "").split(",") if t.strip()],
                "cannot": [
                    t.strip() for t in fm.get("disallowedTools", "").split(",") if t.strip()
                ],
                "defined": path.relative_to(REPO).as_posix(),
            }
        )

    commands = REPO / ".claude/commands"
    for path in sorted(commands.rglob("*.md")):
        fm = split_frontmatter(path.read_text())
        slug = path.relative_to(commands).with_suffix("").as_posix()
        staff.append(
            {
                "id": slug,
                "kind": "command",
                "invoke": "/" + slug.replace("/", ":"),
                "role": role_line(fm.get("description", "")),
                "detail": fm.get("description", ""),
                "icon": fm.get("icon", ""),
                "model": "",
                "effort": "",
                "can": [],
                "cannot": [],
                "defined": path.relative_to(REPO).as_posix(),
            }
        )

    # Services are not defined in this repo — GitHub owns them. Every actor in
    # the history that is neither a definition above nor the human is one, so
    # the roster picks up a new bot the first time it signs a commit and never
    # needs a hardcoded list to maintain.
    named = {e["id"] for e in staff}
    staff.extend(
        {
            "id": actor,
            "kind": "service",
            "invoke": actor,
            "role": "",
            "detail": "",
            "icon": "",
            "model": "",
            "effort": "",
            "can": [],
            "cannot": [],
            "defined": "",
        }
        for actor in sorted({c["actor"] for c in commits} - humans - named)
    )

    for member in staff:
        member["icon"] = member["icon"] or KIND_ICON[member["kind"]]
        token = member["invoke"]
        done = (
            [
                {"date": c["date"], "what": c["subject"], "ref": c["sha"], "via": "commit"}
                for c in commits
                if c["actor"] == member["id"]
            ]
            + [run for run in ledger if run["agent"] == member["id"]]
            + [
                {"date": e["date"], "what": e["title"], "ref": "", "via": "log"}
                for e in entries
                if token in e["body"] or member["id"] in e["body"]
            ]
        )
        member["done"] = sorted(done, key=lambda r: r["date"], reverse=True)
        member["doing"] = [
            {"date": c["date"], "what": c["subject"], "ref": c["sha"], "via": "commit"}
            for c in ahead
            if c["actor"] == member["id"]
        ]
        member["last"] = member["done"][0]["date"] if member["done"] else ""

    # The ledger names an employee by id but cannot check the name, because the
    # rule that derives an id from a definition file lives here. A row naming
    # nobody is a typo or a deleted definition, and either way its runs are
    # invisible on the page - so the build says so rather than dropping them
    # quietly.
    unknown = sorted({run["agent"] for run in ledger} - {m["id"] for m in staff})
    if unknown:
        print(f"  warning: .claude/runs.tsv names employees that do not exist: {unknown}")

    staff.sort(key=lambda m: (KIND_ORDER[m["kind"]], -len(m["done"]), m["id"]))
    return staff


REPORT = ROOT / "publication-report.txt"
REPORT_HEADER = """\
# Generated by `./build.py --target static`. Do not edit by hand.
#
# Each line is a page this site publishes that still names a page exclude.txt
# holds back. Excluding a page does not redact the facts it concentrates: the
# link renders as plain text, and the sentence around it stays.
#
# CI regenerates this file and fails if it changed, so a new leak has to be
# looked at by a person before the site deploys. What it cannot catch is a
# published page carrying a held-back fact without linking to it - nothing
# mechanical can. This narrows the surface; it does not make publishing safe.
"""


def write_report(leftover: list[tuple[str, str]]) -> bool:
    """Record which published pages still name held-back ones.

    Returns whether the file changed, which is the only reason the caller says
    anything: an unchanged report is the normal case and does not need a line.
    """
    body = "".join(f"{page} -> {held}\n" for page, held in sorted(leftover))
    text = REPORT_HEADER + "\n" + (body or "# (nothing published names a held-back page)\n")
    changed = not REPORT.exists() or REPORT.read_text() != text
    REPORT.write_text(text)
    return changed


def build(target: str) -> None:
    pages = read_pages()
    excluded = read_excludes() if target == "static" else set()
    if target == "static":
        missing = excluded - {p["slug"] for p in pages}
        if missing:
            print(f"  warning: exclude.txt names pages that do not exist: {sorted(missing)}")
        pages = [p for p in pages if p["slug"] not in excluded]
        for p in pages:
            p["body"] = redact(p["body"], excluded)
            p["links"] = sorted(set(re.findall(r"\[\[([^\]|]+)", p["body"])))
            p["words"] = len(p["body"].split())

    kept = {p["slug"] for p in pages}
    dangling = sum(1 for p in pages for link in p["links"] if link not in kept)
    leftover = residual(pages, excluded)

    commit = (
        subprocess.run(
            ["git", "-C", str(VAULT.parent), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        or "unknown"
    )

    pointers = []
    for f in sorted((VAULT / "raw/repo-docs").glob("*.md")):
        t = f.read_text()
        pointers.append(
            {
                "doc": pointer_field(t, "source-path"),
                "hash": pointer_field(t, "content-hash"),
                "synced": pointer_field(t, "synced"),
            }
        )

    employees = read_employees(excluded)

    data = {
        "pages": pages,
        "config": json.loads((VAULT / "brain.config.json").read_text()),
        "commit": commit,
        "pointers": pointers,
        "employees": employees,
        "logHeld": "log" in excluded,
        "target": target,
    }
    keep = "caps" if target == "artifact" else "static"
    shell = strip_blocks(
        TPL.joinpath("shell.html").read_text(), keep, "<!--IF:{}-->", "<!--ENDIF-->"
    )
    app = strip_blocks(TPL.joinpath("app.js").read_text(), keep, "/*IF:{}*/", "/*ENDIF*/")

    html = "".join(
        [
            TPL.joinpath("head.html").read_text(),
            "<style>\n",
            # Brand tokens first: styles.css is written against the roles they
            # define, so a missing brand.css is a broken page, not a fallback.
            TPL.joinpath("brand.css").read_text(),
            TPL.joinpath("styles.css").read_text(),
            "</style>\n",
            shell,
            "<script>\nconst BRAIN = ",
            json.dumps(data, separators=(",", ":")),
            ";\n",
            app,
            "</script>\n",
        ]
    )

    DIST.mkdir(exist_ok=True)
    out = DIST / ("index.html" if target == "static" else "artifact.html")
    out.write_text(html)

    if target == "static":
        # Declared once, emitted twice. `_headers` is what Pages applies when
        # the site is plain files; `_worker.js` sets the same headers itself
        # because Pages ignores `_headers` for responses a worker returns, and
        # the worker is what serves the site once Ask needs an endpoint.
        #
        # `connect-src 'self'` is what lets the page reach /api/ask. The
        # previous policy had no connect-src and inherited `default-src 'none'`,
        # which would have blocked the request with nothing in the UI to
        # explain why.
        (DIST / "_headers").write_text(
            "/*\n" + "".join(f"  {name}: {value}\n" for name, value in SECURITY_HEADERS.items())
        )
        (DIST / "_worker.js").write_text(render_worker())
        (DIST / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
        (DIST / "404.html").write_text(
            '<title>Not here</title><meta http-equiv="refresh" content="0; url=/">\n'
        )

    print(f"  {out.relative_to(ROOT)}  {out.stat().st_size // 1024} KB")
    print(
        f"  {len(pages)} pages, {sum(len(p['links']) for p in pages)} links, compiled at {commit}"
    )
    idle = [e["id"] for e in employees if not e["done"]]
    print(f"  {len(employees)} employees, {sum(len(e['done']) for e in employees)} recorded runs")
    if idle:
        print(f"  no recorded runs for: {', '.join(idle)}")
    if excluded:
        print(f"  {len(excluded)} pages held back: {', '.join(sorted(excluded))}")
    if dangling:
        print(f"  {dangling} links point at held-back pages; they render as plain text")
    if leftover:
        pages_touched = sorted({src for src, _ in leftover})
        print(
            f"  NOTE: {len(leftover)} prose mentions of held-back pages remain, across "
            f"{len(pages_touched)} pages: {', '.join(pages_touched)}"
        )
        print(
            "  Excluding a page does not redact facts quoted elsewhere. Read those pages "
            "before treating this build as safe for an audience that should not see them."
        )
    if target == "static" and write_report(leftover):
        print(f"  {REPORT.name} changed - review the diff before this deploys")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--target", choices=["static", "artifact"], default="static")
    args = ap.parse_args()
    print(f"building {args.target}")
    build(args.target)
