"""Shared environment-backed settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from event_driven_audio_analytics.shared.storage import validate_run_id


@dataclass(slots=True)
class BaseServiceSettings:
    """Settings shared by all services."""

    service_name: str
    run_id: str
    kafka_bootstrap_servers: str
    artifacts_root: Path


@dataclass(slots=True)
class DatabaseSettings:
    """Settings required by the writer's TimescaleDB connection."""

    host: str
    port: int
    database: str
    user: str
    password: str


def load_base_service_settings(service_name: str) -> BaseServiceSettings:
    """Load common service settings from the environment."""

    return BaseServiceSettings(
        service_name=os.getenv("SERVICE_NAME", service_name),
        run_id=validate_run_id(os.getenv("RUN_ID", "demo-run")),
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092"),
        artifacts_root=Path(os.getenv("ARTIFACTS_ROOT", "/app/artifacts")),
    )


def load_database_settings() -> DatabaseSettings:
    """Load TimescaleDB settings from the environment."""

    return DatabaseSettings(
        host=os.getenv("POSTGRES_HOST", "timescaledb"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "audio_analytics"),
        user=os.getenv("POSTGRES_USER", "audio_analytics"),
        password=os.getenv("POSTGRES_PASSWORD", "audio_analytics"),
    )
