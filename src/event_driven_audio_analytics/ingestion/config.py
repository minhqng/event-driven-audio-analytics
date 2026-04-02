"""Configuration helpers for the ingestion service."""

from __future__ import annotations

from dataclasses import dataclass
import os

from event_driven_audio_analytics.shared.settings import BaseServiceSettings, load_base_service_settings


def _parse_track_id_allowlist(raw_value: str) -> tuple[int, ...]:
    """Parse a comma-separated list of track ids from the environment."""

    if not raw_value.strip():
        return ()

    track_ids: list[int] = []
    for raw_part in raw_value.split(","):
        part = raw_part.strip()
        if not part:
            continue
        track_ids.append(int(part))
    return tuple(track_ids)


@dataclass(slots=True)
class IngestionSettings:
    """Runtime settings for metadata loading and segment orchestration."""

    base: BaseServiceSettings
    metadata_csv_path: str
    audio_root_path: str
    subset: str
    target_sample_rate_hz: int
    segment_duration_s: float
    segment_overlap_s: float
    min_duration_s: float
    silence_threshold_db: float
    track_id_allowlist: tuple[int, ...]
    max_tracks: int | None

    @classmethod
    def from_env(cls) -> "IngestionSettings":
        max_tracks_raw = os.getenv("INGESTION_MAX_TRACKS", "1").strip()
        return cls(
            base=load_base_service_settings("ingestion"),
            metadata_csv_path=os.getenv("METADATA_CSV_PATH", "data/raw/fma_metadata/tracks.csv"),
            audio_root_path=os.getenv("AUDIO_ROOT_PATH", "data/raw/fma_small"),
            subset=os.getenv("FMA_SUBSET", "small"),
            target_sample_rate_hz=int(os.getenv("TARGET_SAMPLE_RATE_HZ", "32000")),
            segment_duration_s=float(os.getenv("SEGMENT_DURATION_S", "3.0")),
            segment_overlap_s=float(os.getenv("SEGMENT_OVERLAP_S", "1.5")),
            min_duration_s=float(os.getenv("MIN_DURATION_S", "1.0")),
            silence_threshold_db=float(os.getenv("SILENCE_THRESHOLD_DB", "-60.0")),
            track_id_allowlist=_parse_track_id_allowlist(os.getenv("TRACK_ID_ALLOWLIST", "")),
            max_tracks=int(max_tracks_raw) if max_tracks_raw else None,
        )
