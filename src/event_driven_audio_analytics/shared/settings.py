"""Shared environment-backed settings."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import os

from event_driven_audio_analytics.shared.storage import StorageBackendSettings, validate_run_id


def _parse_bool_env(raw_value: str) -> bool:
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_env_value(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    if raw_value.strip() == "":
        return None
    return raw_value


def _getenv_aliased(
    canonical_name: str,
    *,
    alias_name: str | None = None,
    default: str,
) -> str:
    canonical_value = _normalize_env_value(os.getenv(canonical_name))
    alias_value = (
        _normalize_env_value(os.getenv(alias_name))
        if alias_name is not None
        else None
    )

    if (
        canonical_value is not None
        and alias_value is not None
        and canonical_value != alias_value
    ):
        raise ValueError(
            "Conflicting storage environment variables: "
            f"{canonical_name}={canonical_value!r} "
            f"{alias_name}={alias_value!r}."
        )

    if canonical_value is not None:
        return canonical_value
    if alias_value is not None:
        return alias_value
    return default


def load_storage_backend_settings(*, artifacts_root: Path) -> StorageBackendSettings:
    """Load shared claim-check backend settings from canonical env vars and aliases."""

    secure = _parse_bool_env(os.getenv("MINIO_SECURE", "false"))
    return StorageBackendSettings(
        backend=os.getenv("STORAGE_BACKEND", "local"),
        artifacts_root=artifacts_root,
        bucket=_getenv_aliased(
            "MINIO_BUCKET",
            alias_name="ARTIFACT_BUCKET",
            default="fma-small-artifacts",
        ),
        endpoint_url=_getenv_aliased(
            "MINIO_ENDPOINT_URL",
            alias_name="MINIO_ENDPOINT",
            default="https://minio:9000" if secure else "http://minio:9000",
        ),
        access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        region=os.getenv("MINIO_REGION", "us-east-1"),
        secure=secure,
        create_bucket=_parse_bool_env(os.getenv("MINIO_CREATE_BUCKET", "false")),
    )


@dataclass(slots=True)
class BaseServiceSettings:
    """Settings shared by all services."""

    service_name: str
    run_id: str
    kafka_bootstrap_servers: str
    artifacts_root: Path
    storage: StorageBackendSettings = field(default_factory=StorageBackendSettings)

    def __post_init__(self) -> None:
        if (
            self.storage.normalized_backend() == "local"
            and self.storage.artifacts_root == StorageBackendSettings().artifacts_root
            and self.artifacts_root != self.storage.artifacts_root
        ):
            self.storage = replace(self.storage, artifacts_root=self.artifacts_root)


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

    artifacts_root = Path(os.getenv("ARTIFACTS_ROOT", "/app/artifacts"))
    return BaseServiceSettings(
        service_name=os.getenv("SERVICE_NAME", service_name),
        run_id=validate_run_id(os.getenv("RUN_ID", "demo-run")),
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092"),
        artifacts_root=artifacts_root,
        storage=load_storage_backend_settings(artifacts_root=artifacts_root),
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
