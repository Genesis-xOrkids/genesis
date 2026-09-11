#!/usr/bin/env python3
"""Pre-ship check: a pull request says what it changed, and carries its labels.

Two facts about a pull request that nothing else records. The title is the only
description most of the history ever gets - `git log --oneline` is titles - and
the labels are how a list of thirty is filtered down to the three that touch a
plane.

Both are derived here rather than typed, because the mess they exist to stop is
a typing mess: half this repository's titles were the branch slug that
`gh pr create` offers when a branch holds more than one commit. "Gems life" from
`gems-life`, "Agents panel" from `agents-panel`. Those are branch names, not
descriptions, and the only reliable way to tell one from the other is to compare
them - which is a check, not a convention anyone remembers.

The type lives on the branch (`feat/`, `fix/`, `chore/`, `docs/`) rather than in
the title. A `feat:` prefix pays for itself where a tool reads it - semantic
release, changelog generation - and this repository has neither, so in a title
it would cost characters the description needs and return nothing. On a branch
it is what you type and what `git branch` shows, and it is where the type label
is read from.

What is deliberately not checked is mood. A backtest over every title this
repository has merged flagged "Embed the catalog, and collapse colourways in
results" as non-imperative, on the same `-ed` ending that correctly flagged
"Hosted brain storage". Two of the best titles here are noun phrases anyway
("3D employee gems that float, spin and shimmer"), so a rule demanding the
imperative would be enforcing a house style this house does not write in.

Bots are exempt, by account type rather than by name: the API reports
Dependabot's login as `app/dependabot`, with no `[bot]` suffix to match on.
Its titles are generated from the dependency it moved and are not ours to style.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

# Branch prefix -> the label a pull request from it carries. One axis: what kind
# of change this is. Where it lands is the area labels below, and a branch that
# changes the vault is still a `docs` or a `feat` change to it.
TYPES = {
    "feat": "new capability",
    "fix": "corrects behaviour that was wrong",
    "chore": "dependencies, CI, tooling, configuration",
    "docs": "prose only",
}

# Path prefix -> area label. First match wins per file, so the more specific
# prefix is listed first. A file matching nothing contributes no label; that is
# a repository root file (README, pyproject) and the type label already says
# what it was.
AREAS = [
    (".github/workflows/", "ci"),
    (".github/agents/", "agents"),
    (".claude/", "agents"),
    ("second-brain/", "brain"),
    ("api/", "api"),
    ("intelligence/", "intelligence"),
    ("services/", "intelligence"),
    ("apps/", "web"),
    ("packages/", "web"),
    ("infra/", "infra"),
]

MAX_TITLE = 80
MIN_WORDS = 3


def slug_of(branch: str) -> str:
    """The branch's own words, for comparing a title against them.

    Everything before the first `/` is the type prefix and never appears in a
    title, so it is dropped: `feat/gems-life` and `gems-life` both reduce to
    "gems life".
    """
    return re.sub(r"[-_]+", " ", branch.split("/", 1)[-1]).strip().lower()


def title_violations(title: str, branch: str) -> list[str]:
    """Every way this title fails to describe the change, in one pass.

    Returned together rather than raised one at a time: an author who has to
    push three times to learn three rules stops reading the check.
    """
    found = []
    words = title.split()

    if title.strip().lower() == slug_of(branch):
        found.append(
            f"the title is the branch name ({branch!r}). `gh pr create` offers that "
            "when a branch holds more than one commit; it describes nothing. Say what "
            "the change does."
        )
    if len(words) < MIN_WORDS:
        found.append(f"{len(words)} word(s); a description takes at least {MIN_WORDS}.")
    if len(title) > MAX_TITLE:
        found.append(f"{len(title)} characters; the limit is {MAX_TITLE}.")
    if title.endswith("."):
        found.append("trailing period; a title is not a sentence in a paragraph.")
    if title[:1].islower():
        found.append("starts lowercase; the type prefix lives on the branch, not here.")
    return found


def labels_for(branch: str, files: list[str], draft: bool) -> list[str]:
    """The labels this pull request should carry, from what it is and what it touches."""
    labels = set()

    prefix = branch.split("/", 1)[0]
    if prefix in TYPES:
        labels.add(prefix)

    for path in files:
        for start, area in AREAS:
            if path.startswith(start):
                labels.add(area)
                break

    if draft:
        labels.add("wip")

    return sorted(labels)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument(
        "--bot",
        action="store_true",
        help="the pull request's author is a Bot account, per the GitHub API's user.type",
    )
    parser.add_argument("--draft", action="store_true")
    parser.add_argument(
        "--files",
        type=pathlib.Path,
        required=True,
        help="file holding the pull request's changed paths, one per line",
    )
    args = parser.parse_args()

    files = [line.strip() for line in args.files.read_text().splitlines() if line.strip()]

    # Labels first, and unconditionally: a title that breaks a rule is still a
    # pull request someone needs to find in a list, and withholding its labels
    # to punish the title helps nobody.
    print("\n".join(labels_for(args.branch, files, args.draft)))

    if args.bot:
        return 0

    violations = title_violations(args.title, args.branch)
    prefix = args.branch.split("/", 1)[0]
    if prefix not in TYPES:
        violations.append(
            f"branch {args.branch!r} has no type prefix. Name branches "
            f"`<type>/<slug>`, where type is one of: "
            + ", ".join(f"{name} ({why})" for name, why in TYPES.items())
            + "."
        )

    if violations:
        print(f"Pull request title: {args.title!r}", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        print(
            "\nRename the branch, or edit the title with `gh pr edit --title`, "
            "and this check reruns.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
