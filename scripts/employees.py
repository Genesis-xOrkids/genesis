"""What an employee is called, derived from the file that defines it.

An employee id appears in three places that must agree: the roster the site
builds, the ledger row recording that it ran, and the gem the Employees page
draws. Two of those are written by different programs, so the rule turning a
definition file into an id lives here and is imported, rather than being
written out once per program and trusted to stay the same.

Only defined employees are here. The roster also carries services - GitHub apps
that sign commits - and those are discovered from the history rather than from a
file, so they have no id rule to share. Nothing calls `log_agent_run.py` on
their behalf either: a service records itself by committing.
"""

from __future__ import annotations

import pathlib

from scripts.agent_definitions import split_frontmatter

CLAUDE_AGENTS = ".claude/agents"
CLAUDE_COMMANDS = ".claude/commands"


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
