"""Translate a Claude Code agent definition into its GitHub counterpart.

`.claude/agents/*.md` and `.github/agents/*.agent.md` describe one reviewer to
two runtimes. The bodies already delegate — the GitHub file tells its agent to
read the Claude file and follow it, and says so out loud — but frontmatter
cannot delegate, because the two runtimes read different keys. So it was being
written twice, and it had already drifted: two descriptions with different
wording, and a GitHub tool list whose relationship to the Claude one was a
matter of memory rather than a rule.

This module holds the translation, which makes the Claude file the source and
the GitHub frontmatter output. What it deliberately does not hold is the GitHub
*body*: "no guard hook runs here", "you post the report yourself", "do not open
a pull request" are true of that runtime and of nothing else, and inventing
them from the Claude file would be writing prose, not translating a field. The
body is written by hand and preserved verbatim across a regeneration, so a new
Claude agent with no GitHub counterpart is an error rather than an invitation
to generate one.

The tool translation is a capability mapping, not a rename. GitHub's `tools` is
an allowlist of aliases; Claude Code's pairs an allowlist with a
`disallowedTools` denylist. `github/*` maps from `Bash` because reading a pull
request and posting the report is what `gh` does on the Claude side — that is
the same capability reached through a different door, which is exactly what
this table is for.

`check_read_only` is the assertion that matters. This agent's entire point is
that it cannot write, and an allowlist that quietly handed it `edit` while the
Claude definition denied it would be a real read-only hole reached through a
translation nobody re-reads. Denial survives the crossing or the build fails.
"""

from __future__ import annotations

import pathlib
import re

CLAUDE_AGENTS = ".claude/agents"
GITHUB_AGENTS = ".github/agents"

# Claude Code tool -> the GitHub aliases carrying the same capability. Every
# tool either side names must appear here: an unmapped one is a silent hole in
# the translation, so it raises rather than defaulting to "grant nothing".
TOOL_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "Read": ("read",),
    "Glob": ("search",),
    "Grep": ("search",),
    "Bash": ("execute", "github/*"),
    "Write": ("edit",),
    "Edit": ("edit",),
    "NotebookEdit": ("edit",),
    # Named in `disallowedTools` and mapping to nothing on purpose: that runtime
    # has no artifact publisher and no database, so there is no alias to deny.
    "Artifact": (),
    "mcp__Neon": (),
}

# Emitted, in this order. GitHub reads `name`, `description` and `tools` from a
# .agent.md. `model`, `effort`, `maxTurns`, `color` and `hooks` are Claude
# Code's own — `opus` is not a GitHub model id and no hook runs in that sandbox
# — so they are dropped rather than mistranslated into fields GitHub ignores.
EMITTED = ("name", "description", "tools")

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)

# A plain YAML scalar cannot open with an indicator character, and cannot carry
# ": " or " #" anywhere, because both would reparse as structure. Everything
# else — the quotes and em-dashes inside these descriptions included — is safe
# unquoted, so the generated file stays readable.
UNSAFE_START = "-?:,[]{}#&*!|>'\"%@`"


def split_frontmatter(text: str) -> dict[str, str]:
    """Flatten a definition file's frontmatter into string values.

    Agent frontmatter folds long values across indented continuation lines —
    `description:` in genesis-reviewer.md runs to seven — and nests a block
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


def split_list(value: str) -> list[str]:
    """A frontmatter comma list as its items, in the order they were written."""
    return [item.strip() for item in value.split(",") if item.strip()]


def equivalents(tool: str) -> tuple[str, ...]:
    """The GitHub aliases for one Claude Code tool."""
    if tool not in TOOL_EQUIVALENTS:
        raise SystemExit(
            f"no GitHub equivalent declared for {tool!r}. Add it to TOOL_EQUIVALENTS, "
            f"mapping to () if that runtime has nothing corresponding."
        )
    return TOOL_EQUIVALENTS[tool]


def yaml_scalar(value: str) -> str:
    """`value` as a YAML scalar, quoted only where a plain one would not parse."""
    if value and value[0] not in UNSAFE_START and ": " not in value and " #" not in value:
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def github_tools(fields: dict[str, str]) -> list[str]:
    """The GitHub allowlist for a Claude agent, in the order its tools declare."""
    tools: list[str] = []
    for tool in split_list(fields.get("tools", "")):
        for alias in equivalents(tool):
            if alias not in tools:
                tools.append(alias)
    return tools


def check_read_only(fields: dict[str, str], tools: list[str]) -> None:
    """Fail if a tool the Claude definition denies is back in the GitHub list.

    The two runtimes express denial differently — a denylist there, absence
    from an allowlist here — so nothing but this comparison notices when a
    mapping grants back what the source refused.
    """
    denied = {
        alias
        for tool in split_list(fields.get("disallowedTools", ""))
        for alias in equivalents(tool)
    }
    granted = sorted(denied.intersection(tools))
    if granted:
        raise SystemExit(
            f"{fields.get('name', '?')}: {', '.join(granted)} is denied by disallowedTools "
            f"but granted by the generated GitHub tool list"
        )


def render_frontmatter(fields: dict[str, str]) -> str:
    """The GitHub frontmatter block for a parsed Claude definition."""
    tools = github_tools(fields)
    check_read_only(fields, tools)

    lines = ["---"]
    for key in EMITTED:
        if key == "tools":
            lines.append("tools: [" + ", ".join(f'"{tool}"' for tool in tools) + "]")
            continue
        value = fields.get(key, "")
        if not value:
            raise SystemExit(f"{fields.get('name', '?')}: {key} is missing from the source")
        lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def regenerate(source: pathlib.Path, target: pathlib.Path) -> str:
    """`target` as it should be: generated frontmatter, body kept as written."""
    if not target.exists():
        raise SystemExit(
            f"{source} has no counterpart at {target}. The GitHub body describes that "
            f"runtime and cannot be generated from the Claude file; write it, then re-run."
        )
    fields = split_frontmatter(source.read_text())
    if not fields:
        raise SystemExit(f"{source}: no frontmatter")

    existing = target.read_text()
    match = FRONTMATTER.match(existing)
    if not match:
        raise SystemExit(f"{target}: no frontmatter to replace")
    return render_frontmatter(fields) + existing[match.end() :]


def definition_pairs(root: pathlib.Path) -> list[tuple[pathlib.Path, pathlib.Path]]:
    """Every Claude agent definition, paired with the GitHub file it generates."""
    return [
        (source, root / GITHUB_AGENTS / f"{source.stem}.agent.md")
        for source in sorted((root / CLAUDE_AGENTS).glob("*.md"))
    ]
