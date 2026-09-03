"""The GraphQL schema, assembled from the model graph.

Queries are generated: every model gets a list field and a by-id field, and the
selection set drives loading. The write side is one door - a single ``writeData``
mutation taking entity targets and named field writes - so intent lives in the
client and the backend keeps one write path per fact.
"""

from __future__ import annotations

from typing import Any

import strawberry
from sqlalchemy.orm import Mapper
from strawberry.types.nodes import SelectedField

from api.genesis_api.db import read_connection, write_session
from api.genesis_api.graphql.loader import Selection, instantiate, load_rows
from api.genesis_api.graphql.registry import (
    all_mappers,
    exposed_columns,
    relationship_plans,
)
from api.genesis_api.graphql.type_builder import build_types
from api.genesis_api.writer import WriteSpec, write


def _graphql_to_python_names(mapper: Mapper[Any]) -> dict[str, str]:
    """Map the camelCase names a client sends to the snake_case columns.

    Strawberry camelCases field names on the way out, so the loader has to undo
    that on the way in. Built from the model rather than a hand-kept table.
    """
    names: dict[str, str] = {}
    for name in list(exposed_columns(mapper)) + list(relationship_plans(mapper)):
        head, *rest = name.split("_")
        names[head + "".join(part.title() for part in rest)] = name
    return names


def selection_from_info(info: Any, mapper: Mapper[Any]) -> Selection:
    """Turn the client's selection set into a load plan."""
    selection = Selection()
    fields = getattr(info, "selected_fields", [])
    for field in fields:
        _walk(field, mapper, selection)
    return selection


def _walk(field: Any, mapper: Mapper[Any], selection: Selection) -> None:
    names = _graphql_to_python_names(mapper)
    plans = relationship_plans(mapper)
    for sub in getattr(field, "selections", []):
        if not isinstance(sub, SelectedField):
            continue
        python_name = names.get(sub.name)
        if python_name is None:
            continue
        if python_name in plans:
            child = selection.children.setdefault(python_name, Selection())
            nested = Selection()
            _walk(sub, plans[python_name].target_mapper, nested)
            child.fields |= nested.fields
            for key, value in nested.children.items():
                child.children[key] = value
        else:
            selection.fields.add(python_name)


@strawberry.input
class FieldWrite:
    """One named field on the target entity."""

    name: str
    # Values arrive as strings and are coerced by the column type. Enums and
    # integers both come through here; a value that will not coerce raises.
    value: str | None = None


@strawberry.input
class WriteTarget:
    """One entity to write, identified by its natural key.

    Admit, edit, and annotate are payload shapes, not separate mutations: the
    intent lives in the client, and the backend keeps one write path per fact.
    """

    entity: str
    natural_key: list[FieldWrite]
    values: list[FieldWrite]


@strawberry.type
class WriteOutcome:
    entity: str
    id: int
    created: bool


def _resolve_column(mapper: Mapper[Any], name: str) -> str:
    """Resolve an incoming field name to a column, accepting either casing.

    Clients send camelCase because that is what the schema advertises, so the
    write door has to undo it exactly as the read path does. An unknown name
    raises here rather than reaching the writer as a mystery column.
    """
    columns = mapper.local_table.columns.keys()
    if name in columns:
        return name
    mapped = _graphql_to_python_names(mapper).get(name)
    if mapped is None or mapped not in columns:
        raise ValueError(f"{mapper.class_.__name__}: no such field {name!r}")
    return mapped


def _coerce(mapper: Mapper[Any], column_name: str, raw: str | None) -> Any:
    """Coerce an incoming string to the column's Python type.

    Raises on anything that will not convert. Never substitutes a default: a
    write that silently stored the wrong value is worse than a rejected one.
    """
    if raw is None:
        return None
    column = mapper.local_table.columns[column_name]
    column_type = column.type
    if hasattr(column_type, "enum_class") and column_type.enum_class is not None:
        return column_type.enum_class(raw)
    python_type = column_type.python_type
    if python_type is bool:
        if raw.lower() not in {"true", "false"}:
            raise ValueError(f"{column_name}: expected true or false, got {raw!r}")
        return raw.lower() == "true"
    if python_type is int:
        return int(raw)
    if python_type is float:
        return float(raw)
    return raw


def _build_query_type() -> type:
    """One list field and one by-id field per model."""
    types = build_types()
    namespace: dict[str, Any] = {}
    annotations: dict[str, Any] = {}

    for mapper in all_mappers():
        name = mapper.class_.__name__
        graphql_type = types[name]
        head, *rest = _snake(name).split("_")
        list_field = head + "".join(p.title() for p in rest) + "s"
        single_field = head + "".join(p.title() for p in rest)

        def make_list(bound_mapper: Mapper[Any] = mapper) -> Any:
            def resolver(info: strawberry.Info, limit: int = 50) -> list[Any]:
                selection = selection_from_info(info, bound_mapper)
                with read_connection() as connection:
                    rows, _ = load_rows(connection, bound_mapper, selection, limit=limit)
                    return instantiate(bound_mapper, rows, selection)

            return resolver

        def make_single(bound_mapper: Mapper[Any] = mapper) -> Any:
            def resolver(info: strawberry.Info, id: int) -> Any:
                selection = selection_from_info(info, bound_mapper)
                table = bound_mapper.local_table
                with read_connection() as connection:
                    rows, _ = load_rows(connection, bound_mapper, selection, where=table.c.id == id)
                    built = instantiate(bound_mapper, rows, selection)
                    return built[0] if built else None

            return resolver

        namespace[list_field] = strawberry.field(resolver=make_list())
        annotations[list_field] = list[graphql_type]  # type: ignore[valid-type]
        namespace[single_field] = strawberry.field(resolver=make_single())
        annotations[single_field] = graphql_type | None

    namespace["__annotations__"] = annotations
    query = type("Query", (), namespace)
    return strawberry.type(query)


def _snake(name: str) -> str:
    out: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index:
            out.append("_")
        out.append(char.lower())
    return "".join(out)


def _named_values(mapper: Mapper[Any], items: list[FieldWrite]) -> dict[str, Any]:
    """Resolve and coerce a list of named writes into column values."""
    resolved: dict[str, Any] = {}
    for item in items:
        column_name = _resolve_column(mapper, item.name)
        resolved[column_name] = _coerce(mapper, column_name, item.value)
    return resolved


@strawberry.type
class Mutation:
    @strawberry.mutation
    def write_data(self, targets: list[WriteTarget]) -> list[WriteOutcome]:
        """The one write door.

        Every source reaches the database through this mutation and the writer
        behind it. There is deliberately no mutation per action: a mutation per
        field or per clinical-style event recreates the sprawl the single write
        path exists to prevent.
        """
        mappers = {mapper.class_.__name__: mapper for mapper in all_mappers()}
        specs: list[WriteSpec] = []
        for target in targets:
            mapper = mappers.get(target.entity)
            if mapper is None:
                raise ValueError(f"unknown entity {target.entity!r}")
            specs.append(
                WriteSpec(
                    entity=target.entity,
                    natural_key=_named_values(mapper, target.natural_key),
                    values=_named_values(mapper, target.values),
                )
            )

        with write_session() as session:
            results = write(session, specs)

        return [WriteOutcome(entity=r.entity, id=r.id, created=r.created) for r in results]


def build_schema() -> strawberry.Schema:
    return strawberry.Schema(query=_build_query_type(), mutation=Mutation)


schema = build_schema()
