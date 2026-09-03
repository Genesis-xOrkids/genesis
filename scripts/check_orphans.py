"""Pre-ship check: every definition has a caller.

A function built and tested in isolation but never wired to the thing that runs
in production is invisible to boot checks and unit tests alike. It only surfaces
by tracing the call graph, which is what this does.

Names that frameworks call for us are excluded by convention, not by guessing:
pytest tests and fixtures, and GraphQL resolvers reached through the schema.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

EXCLUDED_DIRS = {".venv", "node_modules", "versions", "__pycache__"}
# Called by a framework rather than by our code.
FRAMEWORK_CALLED = re.compile(r"^test_")
RESOLVER_NAMES = {"write_data"}
# Decorators that hand a function to a framework to call.
FRAMEWORK_DECORATORS = {"fixture", "mutation", "field", "strawberry.mutation", "strawberry.field"}


def _decorator_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for decorator in getattr(node, "decorator_list", []):
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute):
            names.add(target.attr)
        elif isinstance(target, ast.Name):
            names.add(target.id)
    return names


def source_files() -> list[pathlib.Path]:
    return [
        path
        for path in pathlib.Path(".").rglob("*.py")
        if not EXCLUDED_DIRS & set(path.parts)
    ]


def main() -> int:
    files = source_files()
    definitions: dict[str, pathlib.Path] = {}
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                if node.name.startswith("__"):
                    continue
                if FRAMEWORK_CALLED.match(node.name) or node.name in RESOLVER_NAMES:
                    continue
                if _decorator_names(node) & FRAMEWORK_DECORATORS:
                    continue
                definitions.setdefault(node.name, path)

    texts = {path: path.read_text() for path in files}
    orphans: list[tuple[str, pathlib.Path]] = []
    for name, defined_in in sorted(definitions.items()):
        references = 0
        for path, text in texts.items():
            found = len(re.findall(rf"\b{re.escape(name)}\b", text))
            if path == defined_in:
                found -= 1  # the definition itself is not a reference
            references += found
        if references == 0:
            orphans.append((name, defined_in))

    print(f"scanned {len(definitions)} definitions across {len(files)} files")
    if orphans:
        print("no caller found:")
        for name, path in orphans:
            print(f"  {name}  ({path})")
        return 1
    print("every definition is referenced outside its own definition")
    return 0


if __name__ == "__main__":
    sys.exit(main())
