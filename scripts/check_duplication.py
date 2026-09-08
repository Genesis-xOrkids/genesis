"""Pre-ship check: no block of code is written twice.

Ruff, mypy and the orphan check all read one definition at a time, so a block
copied into a second file passes every one of them. That is how the same nine
lines of attribute derivation ended up in three connectors: each file was
individually correct, and adding a tenth attribute would have needed three
edits in lockstep or the sources would have silently disagreed about what a
garment is. The constitution's rule is that a derivation used by more than one
component is imported, never copied; this is what enforces it.

Comparison is on normalized physical lines - comments stripped, whitespace
collapsed - which is what catches a copied block inside a single call
expression. A statement-level comparison would not: the derivation block was
nine keyword arguments inside one ``NormalizedProduct(...)`` call, one
statement.

Three kinds of line are excluded because repeating them is not duplication:

- imports, since three connectors translating into the same canonical types
  necessarily name those types;
- string-only lines, so two functions with similar docstrings are not a finding;
- structural punctuation on its own line, which otherwise pads a run of three
  real duplicated lines out past the threshold.

Two whole trees are out of scope. ``versions/`` because Alembic writes those
and they repeat by construction. Tests because they are *supposed* to repeat:
a test that stands alone, arranging its own world and asserting on it, is worth
more than a test that shares a helper with the one below it, and flagging that
would train the reader to ignore this check. The one test duplication that did
matter here - a rollback fixture copied into three files - is a fixture, and
fixtures belong in ``conftest.py`` by convention rather than by scanner.
"""

from __future__ import annotations

import ast
import io
import pathlib
import sys
import tokenize

EXCLUDED_DIRS = {".venv", "node_modules", "versions", "__pycache__", ".git", "tests"}

# Below this, matches are punctuation and boilerplate rather than a copied idea.
# Tuned against the three real duplications this repository had: the shortest
# was nine lines. Lowering it to find something new is how a check becomes noise.
MIN_LINES = 6

STRUCTURAL = {"", ")", "]", "}", "):", "],", "),", "},", "else:", "try:", "pass", "return"}

# A run of `field=local,` lines is plumbing, not a copied idea. Two connectors
# building the same canonical type necessarily pass the same field names, and
# "extracting" that into a helper that forwards six already-computed values adds
# a layer without removing a decision. So a block has to carry some actual work:
# a call, or control flow. Two is where the real findings in this repository sat
# and the constructor tails did not, established by reading both.
MIN_SUBSTANTIVE = 2
CONTROL_FLOW = ("if ", "for ", "while ", "try:", "except", "with ", "raise ", "elif ", "assert ")

# (file, first line, last line) of one occurrence.
Block = tuple[pathlib.Path, int, int]


def source_files() -> list[pathlib.Path]:
    return [
        path
        for path in pathlib.Path(".").rglob("*.py")
        if not EXCLUDED_DIRS & set(path.parts)
        and not path.name.startswith("test_")
        and path.name != "conftest.py"
    ]


def significant_lines(path: pathlib.Path) -> list[tuple[int, str]]:
    """Normalized code lines, each with the line number it came from.

    Tokenizing rather than regex-stripping is what makes ``#`` inside a string
    literal stay part of the code and a trailing comment disappear.
    """
    text = path.read_text()
    comment_rows: set[int] = set()
    string_rows: set[int] = set()
    code_rows: set[int] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            row = token.start[0]
            if token.type == tokenize.COMMENT:
                comment_rows.add(row)
            elif token.type == tokenize.STRING:
                string_rows.update(range(token.start[0], token.end[0] + 1))
            elif token.type not in (
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.INDENT,
                tokenize.DEDENT,
            ):
                code_rows.add(row)
        tree = ast.parse(text)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []

    # Whole logical statement, not the first physical line: a parenthesized
    # ``from x import (\n A,\n B,\n)`` is mostly continuation lines, and leaving
    # those in made every module that imports the same enums look duplicated.
    import_rows: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            import_rows.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))

    lines: list[tuple[int, str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or number in import_rows:
            continue
        if number in comment_rows and number not in code_rows:
            continue
        if number in string_rows and number not in code_rows:
            continue
        normalized = " ".join(stripped.split())
        if normalized in STRUCTURAL:
            continue
        lines.append((number, normalized))
    return lines


def _does_work(line: str) -> bool:
    """Whether this line decides something, rather than passing a value along."""
    return "(" in line or line.startswith(CONTROL_FLOW)


def duplicate_blocks(files: list[pathlib.Path]) -> list[list[Block]]:
    """Groups of two or more places holding the same run of lines."""
    windows: dict[tuple[str, ...], list[tuple[pathlib.Path, int]]] = {}
    normalized = {path: significant_lines(path) for path in files}

    for path, lines in normalized.items():
        texts = [text for _, text in lines]
        for start in range(len(texts) - MIN_LINES + 1):
            key = tuple(texts[start : start + MIN_LINES])
            windows.setdefault(key, []).append((path, start))

    groups: list[list[Block]] = []
    claimed: set[tuple[pathlib.Path, int]] = set()
    for occurrences in windows.values():
        if len(occurrences) < 2 or any(spot in claimed for spot in occurrences):
            continue
        # Extend every occurrence together for as long as they all still agree,
        # so one copied block is reported once at its real length rather than
        # once per overlapping window inside it.
        length = MIN_LINES
        while True:
            nexts = set()
            for path, start in occurrences:
                texts = normalized[path]
                if start + length >= len(texts):
                    nexts.add(None)
                    break
                nexts.add(texts[start + length][1])
            if len(nexts) != 1 or None in nexts:
                break
            length += 1

        first_path, first_start = occurrences[0]
        body = [text for _, text in normalized[first_path][first_start : first_start + length]]
        if sum(1 for line in body if _does_work(line)) < MIN_SUBSTANTIVE:
            continue

        for path, start in occurrences:
            claimed.update((path, start + offset) for offset in range(length - MIN_LINES + 1))
        groups.append(
            [
                (path, normalized[path][start][0], normalized[path][start + length - 1][0])
                for path, start in occurrences
            ]
        )

    return sorted(groups, key=lambda group: (-(group[0][2] - group[0][1]), str(group[0][0])))


def main() -> int:
    files = source_files()
    groups = duplicate_blocks(files)

    print(f"scanned {len(files)} files for blocks of {MIN_LINES}+ repeated lines")
    if groups:
        for group in groups:
            first = group[0]
            print(f"\n{first[2] - first[1] + 1} lines repeated in {len(group)} places:")
            for path, start, end in group:
                print(f"  {path}:{start}-{end}")
        print(f"\n{len(groups)} duplicated blocks; extract the shared one and import it")
        return 1
    print("no duplicated blocks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
