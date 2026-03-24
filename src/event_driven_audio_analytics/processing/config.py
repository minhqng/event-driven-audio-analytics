"""Configuration helpers for the processing service."""

from __future__ import annotations

from dataclasses import dataclass
import os

from event_driven_audio_analytics.shared.settings import BaseServiceSettings, load_base_service_settings


@dataclass(slots=True)
class ProcessingSettings:
    """Runtime settings for feature extraction."""

    base: BaseServiceSettings
    n_mels: int
    target_frames: int
    silence_threshold_db: float

    @classmethod
    def from_env(cls) -> "ProcessingSettings":
        return cls(
            base=load_base_service_settings("processing"),
            n_mels=int(os.getenv("N_MELS", "128")),
            target_frames=int(os.getenv("TARGET_FRAMES", "300")),
            silence_threshold_db=float(os.getenv("SILENCE_THRESHOLD_DB", "-60.0")),
        )
