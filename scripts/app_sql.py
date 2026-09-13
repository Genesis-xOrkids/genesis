"""The application database, read from a script wherever the script runs.

On a machine, statements go through the app's engine on the database URL the
machine has, inside a read-only transaction, so a script that reads cannot write
by accident. A cloud session cannot open a Postgres connection, because its
traffic leaves through an HTTPS proxy. There statements go to Neon's
SQL-over-HTTPS endpoint on `GENESIS_NEON_HOST`, and Claude Code's agent proxy
attaches the read-only connection string stored as the cloud environment's API
credential, in the `Neon-Connection-String` header, so the session never holds it.

This is the one place that knows Neon's answer shape. A script takes the `Read`
that `reader()` yields and passes it statements with named parameters; it never
learns which way they went.
"""

from __future__ import annotations

import datetime
import decimal
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, TextClause

from api.genesis_api.db import engine

TIMEOUT_SECONDS = 60

# Reads one statement with its named parameters, returning its rows.
Read = Callable[[TextClause, Mapping[str, object]], list[dict[str, Any]]]


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise SystemExit(f"Neon sent {value!r} for a boolean")
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise SystemExit(f"Neon sent {value!r} for an integer")
    return int(value)


def _real(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise SystemExit(f"Neon sent {value!r} for a floating-point number")
    return float(value)


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise SystemExit(f"Neon sent {value!r} where text was expected")
    return value


# How each Postgres type Neon answers with becomes the value the driver gives.
# Neon sends booleans, small integers and floats as JSON values and everything
# else as text. A type not listed is refused rather than passed through: an
# unchecked value is the kind of thing that reads wrong without an error.
FROM_NEON: dict[int, Callable[[object], object]] = {
    16: _boolean,
    20: _integer,
    21: _integer,
    23: _integer,
    700: _real,
    701: _real,
    1700: lambda value: decimal.Decimal(_text(value)),
    1082: lambda value: datetime.date.fromisoformat(_text(value)),
    1114: lambda value: datetime.datetime.fromisoformat(_text(value)),
    1184: lambda value: datetime.datetime.fromisoformat(_text(value)),
    2950: lambda value: uuid.UUID(_text(value)),
    19: _text,
    25: _text,
    1042: _text,
    1043: _text,
}


def read_from(connection: Connection) -> Read:
    """Read through a database connection."""

    def read(statement: TextClause, params: Mapping[str, object]) -> list[dict[str, Any]]:
        return [dict(row) for row in connection.execute(statement, params).mappings()]

    return read


def read_over_https(host: str) -> Read:
    """Read through Neon's SQL-over-HTTPS endpoint, as a cloud session must.

    Parameters are sent by position and untyped, so a statement casts them itself
    (`cast(:now as timestamptz)`) to mean the same here as through the driver.
    """

    def read(statement: TextClause, params: Mapping[str, object]) -> list[dict[str, Any]]:
        names = list(params)
        sql = re.sub(
            r"(?<!:):([a-z_]+)\b",
            lambda match: f"${names.index(match.group(1)) + 1}",
            statement.text,
        )
        values = [
            value.isoformat() if isinstance(value, datetime.datetime) else value
            for value in params.values()
        ]
        request = urllib.request.Request(
            f"https://{host}/sql",
            data=json.dumps({"query": sql, "params": values}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                answer = json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read()[:400].decode(errors="replace")
            raise SystemExit(f"Neon refused the query ({error.code}): {detail}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise SystemExit(f"could not reach Neon: {error}") from error

        converters: dict[str, Callable[[object], object]] = {}
        for field in answer["fields"]:
            convert = FROM_NEON.get(field["dataTypeID"])
            if convert is None:
                raise SystemExit(
                    f"column {field['name']} has Postgres type id {field['dataTypeID']}, which "
                    f"this reader does not convert; cast it in SQL, e.g. {field['name']}::text"
                )
            converters[field["name"]] = convert
        return [
            {
                name: None if value is None else converters[name](value)
                for name, value in row.items()
            }
            for row in answer["rows"]
        ]

    return read


@contextmanager
def reader() -> Iterator[Read]:
    """How to read the application database from where this runs."""
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        host = os.environ.get("GENESIS_NEON_HOST")
        if not host:
            raise SystemExit("GENESIS_NEON_HOST is not set on this cloud environment")
        yield read_over_https(host)
        return
    with engine().connect().execution_options(postgresql_readonly=True) as connection:
        yield read_from(connection)
