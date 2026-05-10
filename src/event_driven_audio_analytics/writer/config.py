"""Configuration helpers for the writer service."""

from __future__ import annotations

from dataclasses import dataclass
import os

from event_driven_audio_analytics.shared.contracts.topics import WRITER_INPUT_TOPICS
from event_driven_audio_analytics.shared.settings import (
    BaseServiceSettings,
    DatabaseSettings,
    load_base_service_settings,
    load_database_settings,
)


def _parse_input_topics(raw_value: str) -> tuple[str, ...]:
    """Parse and validate the writer topic subscription override."""

    if not raw_value.strip():
        return WRITER_INPUT_TOPICS

    topics = tuple(part.strip() for part in raw_value.split(",") if part.strip())
    if not topics:
        return WRITER_INPUT_TOPICS

    supported_topics = set(WRITER_INPUT_TOPICS)
    unsupported_topics = sorted(set(topics) - supported_topics)
    if unsupported_topics:
        raise ValueError(
            "WRITER_INPUT_TOPICS may only include: "
            f"{', '.join(WRITER_INPUT_TOPICS)}. "
            f"Unsupported: {', '.join(unsupported_topics)}."
        )
    return topics


@dataclass(slots=True)
class WriterSettings:
    """Runtime settings for TimescaleDB persistence and checkpoint-aware consumption."""

    base: BaseServiceSettings
    database: DatabaseSettings
    consumer_group: str
    auto_offset_reset: str
    poll_timeout_s: float
    session_timeout_ms: int
    max_poll_interval_ms: int
    consumer_retry_backoff_ms: int
    consumer_retry_backoff_max_ms: int
    db_pool_min_size: int
    db_pool_max_size: int
    db_pool_timeout_s: float
    input_topics: tuple[str, ...] = WRITER_INPUT_TOPICS

    @classmethod
    def from_env(cls) -> "WriterSettings":
        return cls(
            base=load_base_service_settings("writer"),
            database=load_database_settings(),
            consumer_group=os.getenv(
                "WRITER_CONSUMER_GROUP",
                "event-driven-audio-analytics-writer",
            ),
            auto_offset_reset=os.getenv("WRITER_AUTO_OFFSET_RESET", "earliest"),
            poll_timeout_s=float(os.getenv("WRITER_POLL_TIMEOUT_S", "1.0")),
            session_timeout_ms=int(os.getenv("WRITER_SESSION_TIMEOUT_MS", "45000")),
            max_poll_interval_ms=int(os.getenv("WRITER_MAX_POLL_INTERVAL_MS", "300000")),
            consumer_retry_backoff_ms=int(
                os.getenv("WRITER_CONSUMER_RETRY_BACKOFF_MS", "250")
            ),
            consumer_retry_backoff_max_ms=int(
                os.getenv("WRITER_CONSUMER_RETRY_BACKOFF_MAX_MS", "5000")
            ),
            db_pool_min_size=int(os.getenv("WRITER_DB_POOL_MIN_SIZE", "1")),
            db_pool_max_size=int(os.getenv("WRITER_DB_POOL_MAX_SIZE", "4")),
            db_pool_timeout_s=float(os.getenv("WRITER_DB_POOL_TIMEOUT_S", "30.0")),
            input_topics=_parse_input_topics(os.getenv("WRITER_INPUT_TOPICS", "")),
        )
