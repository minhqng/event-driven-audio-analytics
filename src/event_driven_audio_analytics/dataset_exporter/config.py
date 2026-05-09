"""Configuration helpers for the dataset exporter."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

from event_driven_audio_analytics.shared.settings import (
    DatabaseSettings,
    load_storage_backend_settings,
    load_database_settings,
)
from event_driven_audio_analytics.shared.storage import StorageBackendSettings


@dataclass(slots=True)
class DatasetExporterSettings:
    """Runtime settings for the offline dataset bundle generator."""

    database: DatabaseSettings
    artifacts_root: Path
    datasets_root: Path
    storage: StorageBackendSettings = field(default_factory=StorageBackendSettings)

    @classmethod
    def from_env(cls) -> "DatasetExporterSettings":
        artifacts_root = Path(os.getenv("ARTIFACTS_ROOT", "/app/artifacts"))
        return cls(
            database=load_database_settings(),
            artifacts_root=artifacts_root,
            datasets_root=Path(
                os.getenv("DATASET_EXPORT_ROOT", str(artifacts_root / "datasets"))
            ),
            storage=load_storage_backend_settings(artifacts_root=artifacts_root),
        )
