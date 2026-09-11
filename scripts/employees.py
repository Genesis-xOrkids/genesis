"""Who the employees are, read from the files that define them.

An employee id appears in three places that must agree: the roster the site
builds, the activity row a hook writes when an agent starts or finishes, and the
run ledger that activity drains into. Those are written by different programs, so
the rule that turns a definition file into an id lives here and is imported,
rather than written out once per program and trusted to stay the same.

Only defined employees are here. The roster also carries services - GitHub apps
that sign commits - and those are discovered from the history rather than from a
file, so they have no id rule to share.
"""

from __future__ import annotations

import pathlib
import re

CLAUDE_AGENTS = ".claude/agents"
CLAUDE_COMMANDS = ".claude/commands"

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)


def split_frontmatter(text: str) -> dict[str, str]:
    """Flatten a definition file's frontmatter into string values.

    Agent frontmatter folds long values across indented continuation lines -
    `description:` in genesis-reviewer.md runs to seven - and nests a block
    under `hooks:`. A one-line-per-key split mangles both: continuations fold
    into their key and nested blocks are dropped. Nothing that reads this needs
    a hook, and a half-parsed one would be worse than none.
    """
    match = FRONTMATTER.match(text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    key = None
    for line in match.group(1).split("\n"):
        if re.match(r"^\s+\S", line):
            if key and fields[key]:
                fields[key] += " " + line.strip()
            continue
        found = re.match(r"^([\w-]+):\s*(.*)$", line)
        if found:
            key = found.group(1)
            fields[key] = found.group(2).strip()
    return fields


def agent_id(path: pathlib.Path) -> str:
    """An agent is named by its frontmatter, falling back to its filename.

    The fallback is the same one Claude Code makes: an agent definition with no
    `name` is still launchable, under its file's stem.
    """
    return split_frontmatter(path.read_text()).get("name", path.stem)


def command_id(path: pathlib.Path, commands: pathlib.Path) -> str:
    """A command is named by its path below `.claude/commands`, without suffix.

    Nested directories become part of the id, so `brain/log.md` is `brain/log` -
    which is what makes it `/brain:log` when invoked.
    """
    return path.relative_to(commands).with_suffix("").as_posix()


def defined_ids(repo: pathlib.Path) -> set[str]:
    """Every employee that a definition file in this repository creates."""
    commands = repo / CLAUDE_COMMANDS
    return {agent_id(path) for path in (repo / CLAUDE_AGENTS).glob("*.md")} | {
        command_id(path, commands) for path in commands.rglob("*.md")
    }
