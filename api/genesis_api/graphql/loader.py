"""Selection-driven loading.

The GraphQL selection set drives the query plan: the loader issues exactly one
SQL statement per requested relationship, at any depth, and nothing else. There
are no dataloaders on this path and no per-query configuration - the client asks
for what it needs and the backend loads exactly that.

The read path is Core. Rows come back as plain dicts and are turned into
Strawberry types before the session closes, so no ORM instance exists to lazy
load during serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper

from api.genesis_api.graphql.registry import (
    RelationshipPlan,
    exposed_columns,
    relationship_plans,
)
from api.genesis_api.graphql.type_builder import graphql_type_for


@dataclass
class Selection:
    """One node of the requested tree: scalar fields plus nested relationships."""

    fields: set[str] = field(default_factory=set)
    children: dict[str, Selection] = field(default_factory=dict)


@dataclass
class LoadStats:
    """Query accounting, so "one query per relationship" is measurable.

    Tests assert on this rather than trusting the claim; an N+1 regression shows
    up as a count, not as a latency someone notices in production.
    """

    queries: int = 0
    per_relationship: list[str] = field(default_factory=list)


def _row_dicts(
    connection: Connection, statement: Select[Any], stats: LoadStats, label: str
) -> list[dict[str, Any]]:
    stats.queries += 1
    stats.per_relationship.append(label)
    return [dict(row) for row in connection.execute(statement).mappings()]


def load_rows(
    connection: Connection,
    mapper: Mapper[Any],
    selection: Selection,
    *,
    where: Any | None = None,
    order_by: Any | None = None,
    limit: int | None = None,
    stats: LoadStats | None = None,
    require_columns: frozenset[str] = frozenset(),
    _label: str = "root",
) -> tuple[list[dict[str, Any]], LoadStats]:
    """Load ``mapper`` rows and every relationship the selection asked for.

    ``require_columns`` names columns the caller needs regardless of what the
    client selected. A one-to-many parent groups its children by the child's
    foreign key, so that column has to come back even when nobody asked for it.
    """
    stats = stats or LoadStats()
    table = mapper.local_table
    plans = relationship_plans(mapper)

    # Always select id and any column a child join needs, even when the client
    # did not ask for it: the join keys are how the tree gets assembled.
    wanted = {name for name in selection.fields if name in table.columns}
    wanted &= set(exposed_columns(mapper))
    wanted.add("id")
    wanted |= {name for name in require_columns if name in table.columns}
    for key in selection.children:
        plan = plans.get(key)
        if plan is not None and plan.local_column in table.columns:
            wanted.add(plan.local_column)

    statement = select(*[table.columns[name] for name in sorted(wanted)])
    if where is not None:
        statement = statement.where(where)
    if order_by is not None:
        statement = statement.order_by(order_by)
    else:
        statement = statement.order_by(table.columns["id"])
    if limit is not None:
        statement = statement.limit(limit)

    rows = _row_dicts(connection, statement, stats, _label)
    if not rows:
        return rows, stats

    for key, child_selection in selection.children.items():
        plan = plans.get(key)
        if plan is None:
            continue
        _attach_relationship(connection, rows, key, plan, child_selection, stats, _label)

    return rows, stats


def _attach_relationship(
    connection: Connection,
    rows: list[dict[str, Any]],
    key: str,
    plan: RelationshipPlan,
    child_selection: Selection,
    stats: LoadStats,
    parent_label: str,
) -> None:
    """Load one relationship for every parent row with a single query."""
    target_table = plan.target_mapper.local_table
    join_values = {row[plan.local_column] for row in rows if row.get(plan.local_column) is not None}

    if not join_values:
        for row in rows:
            row[key] = None if not plan.uselist else []
        return

    child_rows, _ = load_rows(
        connection,
        plan.target_mapper,
        child_selection,
        where=target_table.columns[plan.remote_column].in_(join_values),
        stats=stats,
        require_columns=frozenset({plan.remote_column}),
        _label=f"{parent_label}.{key}",
    )

    if plan.uselist:
        grouped: dict[Any, list[dict[str, Any]]] = {}
        for child in child_rows:
            grouped.setdefault(child[plan.remote_column], []).append(child)
        for row in rows:
            row[key] = grouped.get(row[plan.local_column], [])
    else:
        indexed = {child[plan.remote_column]: child for child in child_rows}
        for row in rows:
            row[key] = indexed.get(row[plan.local_column])


def instantiate(mapper: Mapper[Any], rows: list[dict[str, Any]], selection: Selection) -> list[Any]:
    """Turn loaded dicts into Strawberry types, inside the session.

    Only the fields the client selected are set; everything else stays at its
    ``None`` default, so a partial selection produces a partial instance rather
    than a lie about the row.
    """
    graphql_type = graphql_type_for(mapper)
    plans = relationship_plans(mapper)
    columns = set(exposed_columns(mapper))
    scalar_fields = (selection.fields & columns) | ({"id"} & columns)

    instances: list[Any] = []
    for row in rows:
        instance = graphql_type()
        for name in scalar_fields:
            if name in row:
                setattr(instance, name, row[name])
        for key, child_selection in selection.children.items():
            plan = plans.get(key)
            if plan is None or key not in row:
                continue
            value = row[key]
            if plan.uselist:
                setattr(
                    instance,
                    key,
                    instantiate(plan.target_mapper, value or [], child_selection),
                )
            else:
                built = instantiate(plan.target_mapper, [value], child_selection) if value else []
                setattr(instance, key, built[0] if built else None)
        instances.append(instance)
    return instances
