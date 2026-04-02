"""Database connection helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
from typing import TYPE_CHECKING, Any

from event_driven_audio_analytics.shared.settings import DatabaseSettings

if TYPE_CHECKING:
    from psycopg import Connection, Cursor
else:
    Connection = Any
    Cursor = Any


def build_postgres_dsn(settings: DatabaseSettings) -> str:
    """Construct a PostgreSQL DSN for TimescaleDB."""

    return (
        f"postgresql://{settings.user}:{settings.password}"
        f"@{settings.host}:{settings.port}/{settings.database}"
    )


def open_database_connection(settings: DatabaseSettings) -> Connection:
    """Open a TimescaleDB connection using the shared settings."""

    import psycopg

    return psycopg.connect(build_postgres_dsn(settings), autocommit=False)


@contextmanager
def transaction_cursor(settings: DatabaseSettings) -> Iterator[tuple[Connection, Cursor]]:
    """Yield a cursor wrapped in a commit-or-rollback transaction."""

    with open_database_connection(settings) as connection:
        with connection.cursor() as cursor:
            try:
                yield connection, cursor
            except Exception:
                connection.rollback()
                raise
            connection.commit()


def advisory_lock_key(*parts: object) -> int:
    """Build a stable advisory lock key for a composite logical identifier."""

    digest = hashlib.blake2b(
        "::".join(str(part) for part in parts).encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


def acquire_transaction_advisory_lock(cursor: Cursor, *parts: object) -> None:
    """Acquire a transaction-scoped advisory lock for the provided key parts."""

    cursor.execute("SELECT pg_advisory_xact_lock(%s);", (advisory_lock_key(*parts),))
