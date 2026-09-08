"""Pre-ship check: every definition is reachable from something that runs.

A function built and tested in isolation but never wired to the thing that runs
in production is invisible to boot checks and unit tests alike. It only surfaces
by tracing the call graph, which is what this does.

This walks the graph rather than counting mentions. Counting was the first
version and it had two false negatives that matter: a name spoken in a docstring
counted as a caller, and two dead functions that call each other each looked
referenced by the other. Neither is a call, and a cycle nobody enters is still
dead. Reachability answers the question the pre-ship checklist actually asks -
"trace from the real front door" - rather than "is this word written anywhere".

The front doors are declared, not guessed:

- module-level code, which runs on import (a ``__main__`` block, a registration
  call, a decorator applied at import time);
- pytest tests and fixtures;
- functions a framework calls for us, by decorator;
- ``Protocol`` classes, which are satisfied structurally and so are never named
  by the code that satisfies them;
- ``Base`` subclasses, which Alembic autogenerate and the GraphQL type builder
  reach through ``Base.metadata`` rather than by name.

Reachability is by bare name, so two definitions sharing a name are treated as
one. That direction is deliberate: it can only hide a dead definition behind a
live namesake, never invent a dead one. An import is not a call and does not
make anything reachable - if it did, ``models/__init__.py`` would keep every
model alive forever, which is the exact hiding place this check exists to close.
"""

from __future__ import annotations

import ast
import pathlib
import sys

EXCLUDED_DIRS = {".venv", "node_modules", "versions", "__pycache__", ".git"}

# Decorators that hand a function to a framework to call.
FRAMEWORK_DECORATORS = {
    "fixture",
    "mutation",
    "field",
    "subscription",
    "strawberry.mutation",
    "strawberry.field",
}

# Base classes whose subclasses a framework reaches without naming them.
FRAMEWORK_BASES = {"Protocol", "Base"}

Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def source_files() -> list[pathlib.Path]:
    return [path for path in pathlib.Path(".").rglob("*.py") if not EXCLUDED_DIRS & set(path.parts)]


def _decorator_names(node: Definition) -> set[str]:
    names: set[str] = set()
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute):
            names.add(target.attr)
        elif isinstance(target, ast.Name):
            names.add(target.id)
    return names


def _base_names(node: Definition) -> set[str]:
    if not isinstance(node, ast.ClassDef):
        return set()
    names: set[str] = set()
    for base in node.bases:
        if isinstance(base, ast.Attribute):
            names.add(base.attr)
        elif isinstance(base, ast.Name):
            names.add(base.id)
    return names


def _referenced(node: ast.AST) -> set[str]:
    """Every bare name and attribute this subtree mentions.

    Attributes are included unqualified because a method reached as
    ``self._one(...)`` or ``connector.normalize(...)`` is a real call, and
    resolving the receiver's type is a type-checker's job, not this script's.
    """
    names: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name):
            names.add(inner.id)
        elif isinstance(inner, ast.Attribute):
            names.add(inner.attr)
    return names


def _is_entrypoint(node: Definition) -> bool:
    if node.name.startswith("__"):
        return True
    if node.name.startswith("test_"):
        return True
    if _decorator_names(node) & FRAMEWORK_DECORATORS:
        return True
    return bool(_base_names(node) & FRAMEWORK_BASES)


def call_graph(
    files: list[pathlib.Path],
) -> tuple[dict[str, set[pathlib.Path]], dict[str, set[str]], set[str]]:
    """Definitions by name, the names each one mentions, and the front doors."""
    definitions: dict[str, set[pathlib.Path]] = {}
    edges: dict[str, set[str]] = {}
    roots: set[str] = set()

    for path in files:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, Definition):
                continue
            definitions.setdefault(node.name, set()).add(path)
            edges.setdefault(node.name, set()).update(_referenced(node) - {node.name})
            if _is_entrypoint(node):
                roots.add(node.name)
        # Module-level code runs on import, so whatever it mentions is entered.
        # A definition nested inside another definition is that one's business,
        # not the module's, and is skipped here.
        for statement in tree.body:
            if isinstance(statement, Definition):
                roots.update(_decorator_names(statement) | _base_names(statement))
                continue
            roots.update(_referenced(statement))

    return definitions, edges, roots


def reachable(
    definitions: dict[str, set[pathlib.Path]], edges: dict[str, set[str]], roots: set[str]
) -> set[str]:
    live: set[str] = set()
    pending = [name for name in roots if name in definitions]
    while pending:
        name = pending.pop()
        if name in live:
            continue
        live.add(name)
        pending.extend(
            edge for edge in edges.get(name, ()) if edge in definitions and edge not in live
        )
    return live


def main() -> int:
    files = source_files()
    definitions, edges, roots = call_graph(files)
    live = reachable(definitions, edges, roots)
    orphans = sorted(set(definitions) - live)

    print(f"scanned {len(definitions)} definitions across {len(files)} files")
    if orphans:
        print("unreachable from any entrypoint:")
        for name in orphans:
            where = ", ".join(str(path) for path in sorted(definitions[name]))
            print(f"  {name}  ({where})")
        return 1
    print(f"every definition is reachable ({len(live)} live)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
