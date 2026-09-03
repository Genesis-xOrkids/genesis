"""The design principles in CLAUDE.md, enforced as tests.

A principle nobody checks decays into a comment. Each test here corresponds to a
rule that is cheap to violate by accident and expensive to discover later.
"""

from __future__ import annotations

import enum
import inspect

import pytest
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import configure_mappers

from api.genesis_api.models import Base
from api.genesis_api.models import enums as domain_enums

configure_mappers()

ALL_TABLES = sorted(Base.metadata.tables.values(), key=lambda t: t.name)
DOMAIN_ENUM_CLASSES = [
    obj
    for _, obj in inspect.getmembers(domain_enums, inspect.isclass)
    if issubclass(obj, enum.Enum) and obj.__module__ == domain_enums.__name__
]


@pytest.mark.parametrize("enum_class", DOMAIN_ENUM_CLASSES, ids=lambda c: c.__name__)
def test_enum_member_names_equal_their_values(enum_class: type[enum.Enum]) -> None:
    """SQLAlchemy uses member names as DB labels, so a member whose name differs
    from its value writes one string to Postgres and reads another in Python."""
    mismatched = [f"{m.name}={m.value!r}" for m in enum_class if m.name != m.value]
    assert not mismatched, f"{enum_class.__name__} members must satisfy name == value: {mismatched}"


@pytest.mark.parametrize("enum_class", DOMAIN_ENUM_CLASSES, ids=lambda c: c.__name__)
def test_enum_values_are_lowercase(enum_class: type[enum.Enum]) -> None:
    upper = [m.value for m in enum_class if m.value != m.value.lower()]
    assert not upper, f"{enum_class.__name__} values must be lowercase: {upper}"


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda t: t.name)
def test_every_table_has_integer_id_primary_key(table) -> None:
    """The GraphQL loader resolves FK-referenced parents by ``.c.id``. A table
    without an integer ``id`` passes type building and throws at query time."""
    pk_columns = list(table.primary_key.columns)
    assert len(pk_columns) == 1, f"{table.name} must have a single-column primary key"
    assert pk_columns[0].name == "id", f"{table.name} primary key must be named 'id'"
    assert pk_columns[0].type.python_type is int, f"{table.name}.id must be an integer"


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda t: t.name)
def test_every_foreign_key_targets_an_id_column(table) -> None:
    """A FK to a non-``id`` column builds fine and fails on any read that
    traverses the relationship."""
    offenders = [
        f"{fk.parent.name} -> {fk.target_fullname}"
        for fk in table.foreign_keys
        if fk.column.name != "id"
    ]
    assert not offenders, f"{table.name} has FKs not pointing at an id column: {offenders}"


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda t: t.name)
def test_constraints_follow_the_naming_convention(table) -> None:
    """Named constraints in ``__table_args__``: unique_{table}_{columns},
    ix_{table}_{columns}. An unnamed constraint lands in the database with a
    server-generated name that Alembic then cannot reliably drop."""
    for constraint in table.constraints:
        if type(constraint).__name__ == "PrimaryKeyConstraint":
            continue
        assert constraint.name is not None, f"{table.name} has an unnamed constraint"
        assert not str(constraint.name).startswith("_unnamed_"), (
            f"{table.name} has an unnamed constraint"
        )
    for index in table.indexes:
        assert index.name.startswith("ix_"), f"{table.name}: index {index.name} must start with ix_"


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda t: t.name)
def test_no_json_columns(table) -> None:
    """No JSON/JSONB: structured, typed columns. The long tail belongs in typed
    attribute rows, raw payloads belong in object storage."""
    json_columns = [
        c.name for c in table.columns if type(c.type).__name__.upper() in {"JSON", "JSONB"}
    ]
    assert not json_columns, f"{table.name} has JSON columns: {json_columns}"


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda t: t.name)
def test_boolean_columns_have_no_is_prefix(table) -> None:
    offenders = [
        c.name
        for c in table.columns
        if type(c.type).__name__ == "Boolean" and c.name.startswith("is_")
    ]
    assert not offenders, f"{table.name} booleans must not use an is_ prefix: {offenders}"


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda t: t.name)
def test_datetime_columns_end_in_at_and_are_timezone_aware(table) -> None:
    """Time fields end in ``_at``. Naive timestamps silently compare wrong
    against anything a connector supplies in UTC."""
    for column in table.columns:
        if type(column.type).__name__ != "DateTime":
            continue
        assert column.name.endswith("_at"), f"{table.name}.{column.name} must end in _at"
        assert column.type.timezone, f"{table.name}.{column.name} must be timezone-aware"


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda t: t.name)
def test_enum_columns_use_named_native_enums(table) -> None:
    """An unnamed Enum type gets a generated name in Postgres that migrations
    cannot target."""
    for column in table.columns:
        if not isinstance(column.type, SAEnum):
            continue
        assert column.type.name, f"{table.name}.{column.name} uses an unnamed Enum type"
        assert column.type.native_enum, (
            f"{table.name}.{column.name} must use a native Postgres enum"
        )


def test_money_columns_carry_a_unit_suffix() -> None:
    """Unit suffixes on names. A bare ``price`` invites a currency mix-up that no
    type system catches."""
    offenders: list[str] = []
    for table in ALL_TABLES:
        for column in table.columns:
            name = column.name
            if any(token in name for token in ("price", "budget", "amount")) and not (
                name.endswith("_usd_cents") or name.endswith("_amount_minor") or name == "amount"
            ):
                if name in {"price_tier"}:
                    continue
                offenders.append(f"{table.name}.{name}")
    assert not offenders, f"money columns need a unit suffix: {offenders}"


def test_every_relationship_target_is_reachable_from_metadata() -> None:
    """A relationship to a model that was never imported into
    ``models/__init__`` is invisible to Alembic and to the type builder."""
    from sqlalchemy import inspect as sa_inspect

    known = set(Base.metadata.tables)
    for mapper in Base.registry.mappers:
        for rel in sa_inspect(mapper.class_).relationships:
            target = rel.target.name
            assert target in known, (
                f"{mapper.class_.__name__}.{rel.key} targets unregistered table {target}"
            )


POSTGRES_IDENTIFIER_LIMIT = 63


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda t: t.name)
def test_identifiers_fit_within_the_postgres_limit(table) -> None:
    """Postgres truncates identifiers at 63 characters, silently.

    A truncated constraint name does not raise: it lands in the database under a
    different name than the model declares, and every subsequent autogenerate
    proposes dropping and recreating it. This is how a naming convention that
    already supplies a ``ck_{table}_`` prefix turns a hand-written
    ``ck_{table}_{rule}`` name into permanent migration drift.
    """
    too_long: list[str] = []
    if len(table.name) > POSTGRES_IDENTIFIER_LIMIT:
        too_long.append(f"table {table.name} ({len(table.name)})")
    for column in table.columns:
        if len(column.name) > POSTGRES_IDENTIFIER_LIMIT:
            too_long.append(f"column {column.name} ({len(column.name)})")
    for constraint in table.constraints:
        rendered = constraint.name
        if rendered is None:
            continue
        rendered = str(rendered)
        if rendered.startswith("_unnamed_"):
            continue
        if len(rendered) > POSTGRES_IDENTIFIER_LIMIT:
            too_long.append(f"constraint {rendered} ({len(rendered)})")
    for index in table.indexes:
        if index.name and len(index.name) > POSTGRES_IDENTIFIER_LIMIT:
            too_long.append(f"index {index.name} ({len(index.name)})")
    assert not too_long, (
        f"{table.name}: identifiers exceed {POSTGRES_IDENTIFIER_LIMIT} chars: {too_long}"
    )


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda t: t.name)
def test_check_constraint_names_do_not_repeat_their_prefix(table) -> None:
    """The naming convention supplies ``ck_{table}_``; a name that repeats it
    produces ``ck_table_ck_table_rule`` and then gets truncated."""
    offenders = [
        str(c.name)
        for c in table.constraints
        if type(c).__name__ == "CheckConstraint"
        and c.name
        and str(c.name).startswith(f"ck_{table.name}_ck_")
    ]
    assert not offenders, f"{table.name}: check names repeat the ck_ prefix: {offenders}"
