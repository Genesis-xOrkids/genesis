"""Whether a file's latest state has left this checkout.

A cloud session's checkout does not outlive the session, so a file written there
is only durable once it is committed and pushed. Commands that mark work done in
the brain's database - notes filed, runs ledgered - call `require_pushed` first,
so a push that fails leaves the work unmarked for the next run, not lost.

On a machine the checkout survives the session, and `/brain:log` files notes
without committing, so marking goes ahead there as it always has.
"""

from __future__ import annotations

import os
import pathlib
import subprocess


def _git(repo: pathlib.Path, *args: str) -> str:
    finished = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if finished.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {finished.stderr.strip()[:200]}")
    return finished.stdout.strip()


def require_pushed(path: pathlib.Path) -> None:
    """In a cloud session, refuse unless `path` is committed and that commit is pushed."""
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return
    repo = path.parent
    if _git(repo, "status", "--porcelain", "--", str(path)):
        raise SystemExit(
            f"{path.name} has changes that are not committed; commit and push it before marking"
        )
    if not _git(repo, "branch", "-r", "--contains", "HEAD"):
        raise SystemExit(
            f"the commit holding {path.name} is on no remote branch; push it before marking"
        )
