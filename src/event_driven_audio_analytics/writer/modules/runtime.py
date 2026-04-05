"""Runtime readiness checks for the writer service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from event_driven_audio_analytics.shared.contracts.topics import (
    AUDIO_FEATURES,
    AUDIO_METADATA,
    SYSTEM_METRICS,
)
from event_driven_audio_analytics.shared.db import close_database_pool, open_database_pool

if TYPE_CHECKING:
    from confluent_kafka.admin import ClusterMetadata

    from event_driven_audio_analytics.writer.config import WriterSettings


REQUIRED_WRITER_TOPICS = (
    AUDIO_METADATA,
    AUDIO_FEATURES,
    SYSTEM_METRICS,
)
REQUIRED_WRITER_TABLES = (
    "track_metadata",
    "audio_features",
    "system_metrics",
    "run_checkpoints",
)
KAFKA_METADATA_TIMEOUT_S = 5.0


@dataclass(slots=True)
class WriterReadinessError(RuntimeError):
    """Raised when writer runtime dependencies are not ready."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def _list_kafka_topics(bootstrap_servers: str) -> set[str]:
    """Return the currently visible Kafka topics."""

    from confluent_kafka.admin import AdminClient

    admin_client = AdminClient({"bootstrap.servers": bootstrap_servers})
    metadata: ClusterMetadata = admin_client.list_topics(timeout=KAFKA_METADATA_TIMEOUT_S)
    return set(metadata.topics)


def _list_database_tables(settings: "WriterSettings") -> set[str]:
    """Return the currently visible public tables in the writer database."""

    pool = open_database_pool(
        settings.database,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        timeout_s=settings.db_pool_timeout_s,
    )
    try:
        with pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT tablename
                    FROM pg_catalog.pg_tables
                    WHERE schemaname = 'public'
                      AND tablename = ANY(%s)
                    ORDER BY tablename;
                    """,
                    (list(REQUIRED_WRITER_TABLES),),
                )
                return {str(row[0]) for row in cursor.fetchall()}
    finally:
        close_database_pool(pool)


def check_runtime_dependencies(settings: "WriterSettings") -> None:
    """Validate the current writer runtime dependencies once."""

    visible_topics = _list_kafka_topics(settings.base.kafka_bootstrap_servers)
    missing_topics = sorted(set(REQUIRED_WRITER_TOPICS) - visible_topics)
    if missing_topics:
        raise WriterReadinessError(
            "Kafka is reachable but missing required writer topics: "
            f"{', '.join(missing_topics)}."
        )

    visible_tables = _list_database_tables(settings)
    missing_tables = sorted(set(REQUIRED_WRITER_TABLES) - visible_tables)
    if missing_tables:
        raise WriterReadinessError(
            "TimescaleDB is reachable but missing required writer tables: "
            f"{', '.join(missing_tables)}."
        )
