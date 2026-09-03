"""The model graph, validated once at startup.

Per CLAUDE.md the database is the API: models define the GraphQL schema. That
only holds if the model graph is complete, so the invariants the read path
depends on are checked here at import time. A missing relationship is a startup
error, not a runtime warning discovered by whoever first queries that field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import Table
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Mapper, RelationshipProperty, configure_mappers

from api.genesis_api.models import Base

# Columns the API never exposes. Embeddings are an internal retrieval detail:
# 768 floats per product is not something a client should be able to select.
# Compared case-insensitively: pgvector reports its type name as "VECTOR".
INTERNAL_COLUMN_TYPES = {"vector"}


class SchemaError(RuntimeError):
    """Raised at startup when the model graph cannot back a GraphQL schema."""


@dataclass(frozen=True)
class RelationshipPlan:
    """How the loader traverses one relationship with a single query.

    ``local_column`` and ``remote_column`` name the two sides of the join. For a
    many-to-one the local side is the FK and the remote side is the parent's
    ``id``; for a one-to-many it is the reverse.
    """

    key: str
    target_mapper: Mapper[Any]
    local_column: str
    remote_column: str
    uselist: bool


def _relationship_plan(relationship: RelationshipProperty[Any]) -> RelationshipPlan:
    pairs = relationship.local_remote_pairs
    if pairs is None or len(pairs) != 1:
        raise SchemaError(
            f"{relationship.parent.class_.__name__}.{relationship.key} joins on "
            f"{0 if pairs is None else len(pairs)} column pairs; the loader supports "
            "exactly one. Add an explicit primaryjoin or model the link table."
        )
    local, remote = pairs[0]
    return RelationshipPlan(
        key=relationship.key,
        target_mapper=relationship.mapper,
        local_column=local.name,
        remote_column=remote.name,
        uselist=bool(relationship.uselist),
    )


def validate_model_graph() -> None:
    """Fail fast on the graph shapes the read path cannot serve.

    Three checks, each corresponding to a failure that otherwise surfaces only
    on the first query that happens to traverse the bad edge:

    1. Every table the API can reach has an integer ``id``. The loader keys
       parents by ``id``, so a table without one builds fine and throws on read.
    2. Every FK the API traverses points at an ``id`` column, for the same reason.
    3. Every FK that has a declared relationship joins on exactly one column pair.
    """
    configure_mappers()
    problems: list[str] = []

    for mapper in Base.registry.mappers:
        table = cast(Table, mapper.local_table)
        pk = list(table.primary_key.columns)
        if len(pk) != 1 or pk[0].name != "id" or pk[0].type.python_type is not int:
            problems.append(f"{mapper.class_.__name__}: needs a single integer 'id' primary key")

        for fk in table.foreign_keys:
            if fk.column.name != "id":
                problems.append(
                    f"{mapper.class_.__name__}.{fk.parent.name}: foreign key targets "
                    f"{fk.target_fullname}, but the loader resolves parents by id"
                )

        for relationship in sa_inspect(mapper.class_).relationships:
            try:
                _relationship_plan(relationship)
            except SchemaError as exc:
                problems.append(str(exc))

    if problems:
        raise SchemaError(
            "model graph cannot back a GraphQL schema:\n  " + "\n  ".join(sorted(problems))
        )


def exposed_columns(mapper: Mapper[Any]) -> list[str]:
    """Scalar columns this mapper exposes to GraphQL, in declaration order."""
    return [
        column.name
        for column in mapper.local_table.columns
        if type(column.type).__name__.lower() not in INTERNAL_COLUMN_TYPES
    ]


def relationship_plans(mapper: Mapper[Any]) -> dict[str, RelationshipPlan]:
    """Every relationship on this mapper, keyed by field name."""
    return {
        relationship.key: _relationship_plan(relationship)
        for relationship in sa_inspect(mapper.class_).relationships
    }


def all_mappers() -> list[Mapper[Any]]:
    return sorted(Base.registry.mappers, key=lambda m: m.class_.__name__)
