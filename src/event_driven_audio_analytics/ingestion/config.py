"""Configuration helpers for the ingestion service."""

from __future__ import annotations

from dataclasses import dataclass
import os

from event_driven_audio_analytics.shared.settings import BaseServiceSettings, load_base_service_settings


@dataclass(slots=True)
class IngestionSettings:
    """Runtime settings for metadata loading and segment orchestration."""

    base: BaseServiceSettings
    metadata_csv_path: str
    subset: str
    target_sample_rate_hz: int
    segment_duration_s: float
    segment_overlap_s: float

    @classmethod
    def from_env(cls) -> "IngestionSettings":
        return cls(
            base=load_base_service_settings("ingestion"),
            metadata_csv_path=os.getenv("METADATA_CSV_PATH", "data/raw/fma_metadata/tracks.csv"),
            subset=os.getenv("FMA_SUBSET", "small"),
            target_sample_rate_hz=int(os.getenv("TARGET_SAMPLE_RATE_HZ", "32000")),
            segment_duration_s=float(os.getenv("SEGMENT_DURATION_S", "3.0")),
            segment_overlap_s=float(os.getenv("SEGMENT_OVERLAP_S", "1.5")),
        )
