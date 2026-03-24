"""Database connection helpers."""

from __future__ import annotations

from event_driven_audio_analytics.shared.settings import DatabaseSettings


def build_postgres_dsn(settings: DatabaseSettings) -> str:
    """Construct a PostgreSQL DSN for TimescaleDB."""

    return (
        f"postgresql://{settings.user}:{settings.password}"
        f"@{settings.host}:{settings.port}/{settings.database}"
    )
