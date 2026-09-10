"""Generate `.github/agents/*.agent.md` frontmatter from `.claude/agents/*.md`.

    uv run python -m scripts.generate_github_agents            # write
    uv run python -m scripts.generate_github_agents --check    # CI gate

Same shape as the model/migration drift gate: the check runs the generator and
fails if it would have changed anything, so "regenerate and commit" is the only
way to change a GitHub agent's frontmatter and the two definitions cannot drift
between reviews. `scripts.agent_definitions` explains what crosses and why.

Run as a module, not as a path, so that the repository root is on `sys.path`
and `scripts.agent_definitions` resolves.
"""

from __future__ import annotations

import argparse
import difflib
import pathlib
import sys

from scripts.agent_definitions import definition_pairs, regenerate


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check", action="store_true", help="report drift and change nothing (for CI)"
    )
    args = parser.parse_args()

    root = pathlib.Path(__file__).resolve().parent.parent
    pairs = definition_pairs(root)
    stale: list[pathlib.Path] = []

    for source, target in pairs:
        wanted = regenerate(source, target)
        current = target.read_text()
        if wanted == current:
            continue
        stale.append(target)
        if args.check:
            print(f"\n{target.relative_to(root)} is not what {source.relative_to(root)} generates:")
            print(
                "".join(
                    difflib.unified_diff(
                        current.splitlines(keepends=True),
                        wanted.splitlines(keepends=True),
                        fromfile="committed",
                        tofile="generated",
                    )
                ),
                end="",
            )
        else:
            target.write_text(wanted)

    print(f"\nchecked {len(pairs)} agent {'definition' if len(pairs) == 1 else 'definitions'}")
    if not stale:
        print("GitHub frontmatter matches the Claude definitions")
        return 0
    if args.check:
        print(f"{len(stale)} stale; run `uv run python -m scripts.generate_github_agents`")
        return 1
    print(f"regenerated {len(stale)}: {', '.join(str(p.relative_to(root)) for p in stale)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
