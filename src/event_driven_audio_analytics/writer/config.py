"""Configuration helpers for the writer service."""

from __future__ import annotations

from dataclasses import dataclass

from event_driven_audio_analytics.shared.settings import (
    BaseServiceSettings,
    DatabaseSettings,
    load_base_service_settings,
    load_database_settings,
)


@dataclass(slots=True)
class WriterSettings:
    """Runtime settings for TimescaleDB persistence and checkpoint-aware consumption."""

    base: BaseServiceSettings
    database: DatabaseSettings
    consumer_group: str

    @classmethod
    def from_env(cls) -> "WriterSettings":
        return cls(
            base=load_base_service_settings("writer"),
            database=load_database_settings(),
            consumer_group="event-driven-audio-analytics-writer",
        )
