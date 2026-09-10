---
title: The pre-ship checklist
type: concept
sources: [CLAUDE.md, ROADMAP.md, README.md]
related: ["[[engineering-constitution]]", "[[evals-as-gates]]", "[[database-is-the-api]]", "[[current-state]]"]
created: 2026-09-07
last-updated: 2026-09-07
---

## What it is

A list run before calling a branch done — not only when someone asks for an audit
— built around one observation: *"does it boot" and "do the units pass" catch none
of these; each requires checking who else touches the code* (CLAUDE.md, Pre-ship
checklist).

- **Exactly one migration head.** A long-lived branch grows a second head every
  time main ships a migration off the same fork point. Resolve with
  `alembic merge heads`, never by editing `down_revision`.
- **The full chain applies from empty, with no model drift.** Fresh scratch DB,
  `alembic upgrade head`, then `alembic revision --autogenerate` produces an empty
  diff. Drop the scratch DB after.
- **Every new function has a real caller.** Grep the repo for each added function
  or class outside its own definition and trace from the real front door — job
  runner, GraphQL entry point, agent tool registry, API route. Code built and
  tested in isolation but never wired in is invisible to boot checks and unit
  tests alike.
- **Every *other* caller of a shared function or table still gets correct
  behaviour.** Grep for every existing caller and check each by name, not just the
  one you added.
- **Evals ran** for any prompt, tool-schema or model change, and generated
  artifacts (GraphQL SDL, graphql-codegen types) are regenerated and committed.
  See [[evals-as-gates]].
- **Verify the fix live.** Reproduce before, confirm after, for the new case *and*
  every pre-existing case the same code path serves.

## The executable half

README.md, Checks:

```sh
uv run ruff check api/ ; uv run mypy api/genesis_api ; uv run pytest api/tests -q
cd api && uv run alembic heads            # must print exactly one line
uv run alembic upgrade head
uv run alembic revision --autogenerate    # diff must be empty
```

CI enforces eight gates including migration drift and dead-code detection
(ROADMAP.md App. A).

## The half CI cannot enforce

The grep items. Nothing mechanical catches a new function with no caller reachable
from a front door, or an existing caller of a changed shared function. They are on
the list precisely because the test suite is written from inside the same
assumptions as the change.

## The delivery-level version

ROADMAP.md §9 extends the checklist to every milestone: acceptance criteria
demonstrated against a running system rather than argued from a diff; tests
covering failure modes, not only the happy path; every new definition reachable
from something that runs; and **any claim of the form "this is fast" or "this is
correct" backed by a measurement recorded in the pull request**.

## The mindset behind it

CLAUDE.md's design-review section names the failure it is defending against: a
design can pass every test written for it and still be wrong, because the tests
were written from inside the same assumptions as the design. Its sharpest single
rule — if a shared mechanism needs a patch to stop it corrupting adjacent data
when you route new data through it, the mechanism is misapplied, not the patch
done.
