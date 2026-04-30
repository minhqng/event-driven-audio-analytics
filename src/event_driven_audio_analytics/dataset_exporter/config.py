"""Configuration helpers for the dataset exporter."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from event_driven_audio_analytics.shared.settings import (
    DatabaseSettings,
    load_database_settings,
)


@dataclass(slots=True)
class DatasetExporterSettings:
    """Runtime settings for the offline dataset bundle generator."""

    database: DatabaseSettings
    artifacts_root: Path
    datasets_root: Path

    @classmethod
    def from_env(cls) -> "DatasetExporterSettings":
        artifacts_root = Path(os.getenv("ARTIFACTS_ROOT", "/app/artifacts"))
        return cls(
            database=load_database_settings(),
            artifacts_root=artifacts_root,
            datasets_root=Path(
                os.getenv("DATASET_EXPORT_ROOT", str(artifacts_root / "datasets"))
            ),
        )

