# Review instructions

`CLAUDE.md` is this repository's engineering constitution and you already read
it. This file does not restate it. It says what to flag here, at what severity,
and what to leave alone.

## Do not report what CI already enforces

Every pull request has already passed `ruff` (21 rule families), `ruff format`,
`mypy --strict`, a single-migration-head check, a from-empty migration apply, a
model/migration drift probe, a reachability check for unreachable definitions, a
duplicate-block check, `gitleaks`, and the full test suite. Reporting any of
those wastes the author's time and trains them to skim your comments.

Formatting, import order, type-annotation completeness, unused imports, dead
functions and copied blocks are all out of scope for the same reason.

## What Important means here

Reserve it for a diff that breaks a stated rule in `CLAUDE.md` or contradicts a
decision recorded in `second-brain/wiki/decisions/`. Name the section or page.
The recurring ones, in rough order of how often they nearly happen:

- A fact stored in a second place, with nothing enforcing that the copies agree.
  Search the other models for the fact before accepting that a new column is
  needed.
- An interpretive derivation stored on a domain row — `is_on_sale`,
  `is_in_capsule`, a trend label, a latest-price — rather than computed where it
  is used.
- A second write path for a fact that already has one. Everything goes through
  `write_specs` into the domain writer.
- `null` standing in for false, zero, or empty. Null is unknown, and
  `in_stock = null` is not `in_stock = false`.
- A vendor's facet, dropdown or label modeled as if it were an atomic fact.
- A JSON or JSONB column. Structured typed columns, or typed attribute rows.
- A vendor SDK imported directly instead of through `ModelGateway`,
  `ImageProvider` or `MemoryStore`; `budget_tokens` set explicitly; an assistant
  turn prefilled.
- A migration that is not backward-compatible, without the multi-step rollout.
- A write tool that spends money, exports, posts, or changes tenant data without
  a confirmation-token gate.
- A hand-written resolver or dataloader where the model graph should generate
  one; args on a subscription child field; ORM access during GraphQL
  serialization instead of resolving inside the session first.

Two more that pass every literal rule and still matter:

- A shared mechanism — a writer, matcher, linker, sanity check — patched so it
  stops corrupting adjacent data for this one new use. The patch is the signal
  the mechanism is wrong for the use, not that the work was thorough.
- A bounds check that is silently wrong at the field's real range. A sanity
  check built for open-ended values accepting 487% on a 0–100 field; a price
  check that assumes USD accepting JPY 12,000 as $12,000; a size normalizer that
  assumes numerics dropping "XS".

## Everything else is a nit at most

Naming preferences, structure, refactoring suggestions, and anything you would
phrase as "consider" are nits. Report at most three per review; if you found
more, give a count in the summary instead of posting them.

`main` requires conversation resolution, so every inline comment you leave has
to be dismissed by hand before the author can merge. A nit that costs a click to
dismiss is a nit that should have been a line in the summary.

## Verification bar

A behavior claim needs a `path:line` citation in the source, not an inference
from a name. If you cannot point at the line that makes the claim true, put it
in the summary as a question rather than as a finding.

Do not report a defect the wiki already records as known — check
`second-brain/wiki/projects/` before flagging a gap, and name it as known if it
is there.

## Skip

- `api/alembic/versions/**` — Alembic writes these; review the models instead.
- `uv.lock`, `package-lock.json`, `skills-lock.json`.
- `second-brain/wiki/**` — compiled output, not hand-written source.
- Test code that deliberately violates production rules to build a bad input.

## Summary shape

Open with a one-line tally — `2 important, 1 nit` — and lead with "no
constitutional issues" when that is the case. The author wants the shape of the
review before the detail.
