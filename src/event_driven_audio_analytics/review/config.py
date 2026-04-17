"""Configuration helpers for the review service."""

from __future__ import annotations

from dataclasses import dataclass
import os

from event_driven_audio_analytics.shared.settings import (
    BaseServiceSettings,
    DatabaseSettings,
    load_base_service_settings,
    load_database_settings,
)


def _split_pinned_run_ids(raw_value: str) -> tuple[str, ...]:
    return tuple(
        value.strip()
        for value in raw_value.split(",")
        if value.strip()
    )


@dataclass(slots=True)
class ReviewSettings:
    """Runtime settings for the read-only review surface."""

    base: BaseServiceSettings
    database: DatabaseSettings
    host: str
    port: int
    default_limit: int
    max_limit: int
    pinned_run_ids: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "ReviewSettings":
        return cls(
            base=load_base_service_settings("review"),
            database=load_database_settings(),
            host=os.getenv("REVIEW_HOST", "0.0.0.0"),
            port=int(os.getenv("REVIEW_PORT", "8080")),
            default_limit=int(os.getenv("REVIEW_DEFAULT_LIMIT", "8")),
            max_limit=int(os.getenv("REVIEW_MAX_LIMIT", "25")),
            pinned_run_ids=_split_pinned_run_ids(
                os.getenv("REVIEW_PINNED_RUN_IDS", "")
            ),
        )
