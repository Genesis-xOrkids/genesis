"""The one write door.

Every source - feed sync, agent tool, user edit, stylist annotation, document
extraction - writes facts through this module, into the same canonical rows.
There is no per-source column and no parallel writer, because divergent write
paths are how one concept ends up smeared across three representations.

Writes are idempotent: each entity's natural key is derived from its unique
constraint, and a write upserts on that key. Re-running a sync updates rather
than duplicating, and the latest write wins.

Event logs are the exception, and declare themselves: a model with
``__append_only__ = True`` records history rather than current state, so every
write is an insert. Consent is the case in point - granting, withdrawing, and
re-granting are three facts, not one fact changing its mind.

Writes are batched. Adjacent specs targeting the same entity with the same
columns become one multi-row statement. That matters more than it sounds: a
catalog ingest writes tens of thousands of rows, and one network round trip each
turns a six-second job into a five-minute one against a hosted database. The
semantics are unchanged - same upsert, same natural key, same latest-write-wins -
so this stays one write path rather than acquiring a second, faster one that
behaves subtly differently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy import Table, UniqueConstraint, func, literal_column
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapper, Session

from api.genesis_api.graphql.registry import all_mappers

# Postgres accepts at most 65535 bind parameters in one statement. A batch is
# rows times columns, so a wide table hits the ceiling far sooner than a narrow
# one and the cap has to be computed rather than guessed. The margin leaves room
# for the parameters the ON CONFLICT clause adds.
_MAX_BIND_PARAMETERS = 60000


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


@dataclass(frozen=True)
class _Prepared:
    """One validated spec, with everything the statement needs resolved."""

    entity: str
    table: Table
    payload: dict[str, Any]
    key_columns: tuple[str, ...]
    append_only: bool

    @property
    def shape(self) -> tuple[Any, ...]:
        """What makes two specs safe to send in one statement."""
        return (self.entity, tuple(sorted(self.payload)), self.key_columns, self.append_only)

    @property
    def identity(self) -> tuple[Any, ...]:
        return tuple(self.payload.get(name) for name in self.key_columns)


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
        constraint for constraint in table.constraints if isinstance(constraint, UniqueConstraint)
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


def _prepare(mappers: dict[str, Mapper[Any]], spec: WriteSpec) -> _Prepared:
    mapper = mappers.get(spec.entity)
    if mapper is None:
        raise WriteError(f"unknown entity {spec.entity!r}; known entities: {sorted(mappers)}")

    table = cast(Table, mapper.local_table)
    append_only = is_append_only(mapper)
    key_columns = () if append_only else tuple(natural_key_columns(mapper))

    missing = [name for name in key_columns if name not in spec.natural_key]
    if missing:
        raise WriteError(
            f"{spec.entity}: natural key requires {list(key_columns)}, missing {missing}"
        )

    payload: dict[str, Any] = {**spec.natural_key, **spec.values}
    unknown = [name for name in payload if name not in table.columns]
    if unknown:
        raise WriteError(f"{spec.entity}: no such columns {unknown}")

    return _Prepared(
        entity=spec.entity,
        table=table,
        payload=payload,
        key_columns=key_columns,
        append_only=append_only,
    )


def _execute(session: Session, batch: list[_Prepared]) -> list[WriteResult]:
    """Run one batch, split into as few statements as the parameter cap allows."""
    columns = max(len(batch[0].payload), 1)
    chunk_size = max(1, _MAX_BIND_PARAMETERS // columns)
    results: list[WriteResult] = []
    for start in range(0, len(batch), chunk_size):
        results.extend(_execute_chunk(session, batch[start : start + chunk_size]))
    return results


def _execute_chunk(session: Session, batch: list[_Prepared]) -> list[WriteResult]:
    """Run one chunk as a single statement."""
    first = batch[0]
    table = first.table
    rows = [item.payload for item in batch]

    statement = insert(table).values(rows)

    if first.append_only:
        returning = statement.returning(table.c.id)
        return [
            WriteResult(entity=first.entity, id=row.id, created=True)
            for row in session.execute(returning)
        ]

    value_columns = [name for name in first.payload if name not in first.key_columns]
    updatable: dict[str, Any] = {name: statement.excluded[name] for name in value_columns}
    if not updatable:
        # Nothing to change on conflict, but the row's id still has to come back.
        updatable = {first.key_columns[0]: statement.excluded[first.key_columns[0]]}
    # SQLAlchemy's onupdate default does not fire for a raw ON CONFLICT DO
    # UPDATE, so the timestamp is bumped explicitly. Without this an upserted row
    # keeps its original updated_at and looks like it was never touched.
    if "updated_at" in table.columns:
        updatable["updated_at"] = func.now()

    statement = statement.on_conflict_do_update(
        index_elements=list(first.key_columns), set_=updatable
    )
    # xmax is 0 on a freshly inserted tuple and non-zero on one this statement
    # updated. That is exact, where comparing created_at to updated_at only
    # infers it and gets the equal-timestamp case wrong.
    returning = statement.returning(table.c.id, literal_column("(xmax = 0)").label("was_inserted"))
    return [
        WriteResult(entity=first.entity, id=row.id, created=bool(row.was_inserted))
        for row in session.execute(returning)
    ]


def write(session: Session, specs: list[WriteSpec]) -> list[WriteResult]:
    """Apply every spec in order, in the caller's transaction.

    Ordering matters and is the caller's responsibility: a spec that references a
    row created by an earlier spec must come after it. The writer does not
    reorder, because guessing at intent is how a write path acquires behavior
    nobody asked for. Batching preserves that order - only adjacent specs of the
    same shape are combined, and results come back positionally.
    """
    if not specs:
        return []

    mappers = _mappers_by_name()
    prepared = [_prepare(mappers, spec) for spec in specs]

    results: list[WriteResult] = []
    batch: list[_Prepared] = []
    seen: set[tuple[Any, ...]] = set()

    for item in prepared:
        # Postgres refuses to update the same row twice in one statement, and two
        # specs for one key mean the second supersedes the first anyway, so the
        # batch is cut rather than deduplicated.
        if batch and (item.shape != batch[0].shape or item.identity in seen):
            results.extend(_execute(session, batch))
            batch, seen = [], set()
        batch.append(item)
        if not item.append_only:
            seen.add(item.identity)

    results.extend(_execute(session, batch))
    return results
