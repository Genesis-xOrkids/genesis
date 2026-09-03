"""GraphQL types, derived from the model graph.

Generated, not written. Every table becomes a type, every scalar column becomes
a field, every relationship becomes a field pointing at another generated type.
Adding a model to ``models/__init__`` is the whole of adding it to the API.

Types carry plain values loaded through Core, never ORM instances: the read path
never constructs a mapped object, so nothing can lazy-load during serialization.
"""

from __future__ import annotations

import datetime
import decimal
import enum
import types as pytypes
from typing import Any

import strawberry
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapper

from api.genesis_api.graphql.registry import (
    SchemaError,
    all_mappers,
    exposed_columns,
    relationship_plans,
    validate_model_graph,
)

# Generated types live in one namespace so Strawberry can resolve the string
# annotations that make circular relationships (Product.offers <-> Offer.product)
# expressible without forward-declaration gymnastics.
_TYPE_NAMESPACE: dict[str, Any] = {}
_ENUM_CACHE: dict[type[enum.Enum], Any] = {}

_SCALARS: list[tuple[type, type]] = [
    (Boolean, bool),
    (Integer, int),
    (Float, float),
    (Numeric, decimal.Decimal),
    (DateTime, datetime.datetime),
    (Date, datetime.date),
    (Text, str),
    (String, str),
]


def _graphql_enum(python_enum: type[enum.Enum]) -> Any:
    """Wrap a domain enum for GraphQL once, so every type shares one instance."""
    if python_enum not in _ENUM_CACHE:
        _ENUM_CACHE[python_enum] = strawberry.enum(python_enum)
    return _ENUM_CACHE[python_enum]


def _column_annotation(column: Any) -> Any:
    """Map a SQLAlchemy column to its GraphQL annotation.

    Nullability is carried through verbatim: a nullable column is ``T | None`` so
    "unknown" survives into the client, where the component decides how to render
    it. Coercing null to a zero-value here would erase the distinction the schema
    exists to preserve.
    """
    column_type = column.type
    annotation: Any = None

    if isinstance(column_type, SAEnum) and column_type.enum_class is not None:
        annotation = _graphql_enum(column_type.enum_class)
    else:
        for sa_type, py_type in _SCALARS:
            if isinstance(column_type, sa_type):
                annotation = py_type
                break

    if annotation is None:
        raise SchemaError(
            f"column {column.table.name}.{column.name} has type "
            f"{type(column_type).__name__}, which has no GraphQL mapping. Add one to "
            "_SCALARS or mark the type internal in registry.INTERNAL_COLUMN_TYPES."
        )

    return annotation | None if column.nullable else annotation


def _type_name(mapper: Mapper[Any]) -> str:
    return str(mapper.class_.__name__)


def build_types() -> dict[str, Any]:
    """Build every GraphQL type from the model graph.

    Two passes: create the empty classes first so relationship annotations can
    name types that do not exist yet, then fill in fields and decorate.
    """
    validate_model_graph()
    if _TYPE_NAMESPACE:
        return _TYPE_NAMESPACE

    mappers = all_mappers()
    raw: dict[str, type] = {}

    for mapper in mappers:
        name = _type_name(mapper)
        raw[name] = pytypes.new_class(name, (), {})

    for mapper in mappers:
        name = _type_name(mapper)
        cls = raw[name]
        annotations: dict[str, Any] = {}

        for column_name in exposed_columns(mapper):
            column = mapper.local_table.columns[column_name]
            annotations[column_name] = _column_annotation(column)
            # Everything defaults to None so a type can be constructed from a
            # partial selection: the client asked for three fields, we build an
            # instance with three fields set.
            setattr(cls, column_name, None)

        for key, plan in relationship_plans(mapper).items():
            target = _type_name(plan.target_mapper)
            annotations[key] = f"list[{target}]" if plan.uselist else f"{target} | None"
            setattr(cls, key, None)

        cls.__annotations__ = annotations
        cls.__module__ = __name__

    for name, cls in raw.items():
        _TYPE_NAMESPACE[name] = cls

    # Strawberry resolves string annotations against the defining module's
    # globals, so the namespace has to be visible here before decoration.
    globals().update(_TYPE_NAMESPACE)

    for name in list(_TYPE_NAMESPACE):
        _TYPE_NAMESPACE[name] = strawberry.type(_TYPE_NAMESPACE[name])
        globals()[name] = _TYPE_NAMESPACE[name]

    return _TYPE_NAMESPACE


def graphql_type_for(mapper: Mapper[Any]) -> Any:
    return build_types()[_type_name(mapper)]
