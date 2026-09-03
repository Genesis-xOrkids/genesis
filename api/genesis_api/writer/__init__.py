"""The one write door.

Every source - feed sync, agent tool, user edit, stylist annotation, document
extraction - writes facts through this module, into the same canonical rows.
There is no per-source column and no parallel writer, because divergent write
paths are how one concept ends up smeared across three representations.

Writes are idempotent: each entity's natural key is derived from its unique
constraint, and a write upserts on that key. Re-running a sync updates rather
than duplicates, and the latest write wins.

Event logs are the exception, and declare themselves: a model with
``__append_only__ = True`` records history rather than current state, so every
write is an insert. Consent is the case in point - granting, withdrawing, and
re-granting are three facts, not one fact changing its mind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy import Table, UniqueConstraint, func, literal_column
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapper, Session

from api.genesis_api.graphql.registry import all_mappers


class WriteError(RuntimeError):
    """Raised when a write cannot be performed as specified.

    Always raised, never swallowed: a write that silently does nothing is worse
    than one that fails loudly, because the caller goes on believing the fact was
    recorded.
    """


@dataclass(frozen=True)
class WriteSpec:
    """One fact to record.

    ``entity`` names the model, ``natural_key`` identifies the row in the terms
    the source knows it by, and ``values`` carries the fields to set. The writer
    resolves which row that is; callers never pass primary keys they invented.
    """

    entity: str
    natural_key: dict[str, Any] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class WriteResult:
    entity: str
    id: int
    created: bool


def _mappers_by_name() -> dict[str, Mapper[Any]]:
    return {mapper.class_.__name__: mapper for mapper in all_mappers()}


def is_append_only(mapper: Mapper[Any]) -> bool:
    """Whether this entity records events rather than current state."""
    return bool(getattr(mapper.class_, "__append_only__", False))


def natural_key_columns(mapper: Mapper[Any]) -> list[str]:
    """The columns that identify a row independently of its surrogate id.

    Derived from the table's unique constraint rather than declared separately,
    so the key the writer upserts on and the key the database enforces cannot
    drift apart.
    """
    table = cast(Table, mapper.local_table)
    unique_constraints = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    if len(unique_constraints) == 1:
        return [column.name for column in unique_constraints[0].columns]
    if not unique_constraints:
        raise WriteError(
            f"{mapper.class_.__name__} has no unique constraint, so the writer cannot "
            "identify a row to upsert. Add one, or write through a parent entity."
        )
    raise WriteError(
        f"{mapper.class_.__name__} has {len(unique_constraints)} unique constraints; "
        "the natural key is ambiguous. Narrow the model or designate one explicitly."
    )


def write(session: Session, specs: list[WriteSpec]) -> list[WriteResult]:
    """Apply every spec in order, in the caller's transaction.

    Ordering matters and is the caller's responsibility: a spec that references a
    row created by an earlier spec must come after it. The writer does not
    reorder, because guessing at intent is how a write path acquires behavior
    nobody asked for.
    """
    mappers = _mappers_by_name()
    results: list[WriteResult] = []

    for spec in specs:
        mapper = mappers.get(spec.entity)
        if mapper is None:
            raise WriteError(f"unknown entity {spec.entity!r}; known entities: {sorted(mappers)}")

        table = cast(Table, mapper.local_table)

        if is_append_only(mapper):
            results.append(_append(session, spec, table))
            continue

        key_columns = natural_key_columns(mapper)

        missing = [name for name in key_columns if name not in spec.natural_key]
        if missing:
            raise WriteError(
                f"{spec.entity}: natural key requires {key_columns}, missing {missing}"
            )

        payload: dict[str, Any] = {**spec.natural_key, **spec.values}
        unknown = [name for name in payload if name not in table.columns]
        if unknown:
            raise WriteError(f"{spec.entity}: no such columns {unknown}")

        statement = insert(table).values(**payload)
        updatable: dict[str, Any] = {
            name: statement.excluded[name] for name in spec.values if name not in key_columns
        }
        if not updatable:
            # Nothing to change on conflict, but we still need the row's id back.
            updatable = {key_columns[0]: statement.excluded[key_columns[0]]}
        # SQLAlchemy's onupdate default does not fire for a raw ON CONFLICT DO
        # UPDATE, so the timestamp is bumped explicitly. Without this an upserted
        # row keeps its original updated_at and looks like it was never touched.
        if "updated_at" in table.columns:
            updatable["updated_at"] = func.now()
        statement = statement.on_conflict_do_update(index_elements=key_columns, set_=updatable)

        # xmax is 0 on a freshly inserted tuple and non-zero on one updated by
        # this statement. That is exact, where comparing created_at to updated_at
        # only infers it and gets the equal-timestamp case wrong.
        returning = statement.returning(
            table.c.id, literal_column("(xmax = 0)").label("was_inserted")
        )
        row = session.execute(returning).one()
        results.append(WriteResult(entity=spec.entity, id=row.id, created=bool(row.was_inserted)))

    return results


def _append(session: Session, spec: WriteSpec, table: Table) -> WriteResult:
    """Insert an event row. No upsert: history is never rewritten in place."""
    payload: dict[str, Any] = {**spec.natural_key, **spec.values}
    unknown = [name for name in payload if name not in table.columns]
    if unknown:
        raise WriteError(f"{spec.entity}: no such columns {unknown}")
    row = session.execute(insert(table).values(**payload).returning(table.c.id)).one()
    return WriteResult(entity=spec.entity, id=row.id, created=True)
