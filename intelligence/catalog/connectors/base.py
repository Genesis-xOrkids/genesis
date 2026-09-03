"""The connector contract.

A connector's whole job is translation: source records in, canonical
:mod:`intelligence.catalog.normalized` values out. It never touches the database
and never decides what a fact means - it reports what its source says and fails
loudly on what it cannot read.

Keeping the contract this narrow is what makes "design for M data sources" true
rather than aspirational: a new network is one class implementing one method.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable

from intelligence.catalog.normalized import NormalizationResult


@runtime_checkable
class Connector(Protocol):
    """Translates one source's records into canonical values."""

    @property
    def source(self) -> str:
        """The stable identifier that, with a record's own id, forms the natural
        key catalog upserts run on. Changing it re-imports the source as new
        rows, so it is set once and left alone."""
        ...

    def normalize(self, records: Iterable[Any]) -> NormalizationResult:
        """Translate raw source records. Never raises for a single bad record:
        that record is quarantined and the run continues."""
        ...
