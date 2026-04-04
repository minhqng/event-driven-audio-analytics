"""Configuration helpers for the processing service."""

from __future__ import annotations

from dataclasses import dataclass
import os

from event_driven_audio_analytics.shared.settings import BaseServiceSettings, load_base_service_settings


@dataclass(slots=True)
class ProcessingSettings:
    """Runtime settings for feature extraction."""

    base: BaseServiceSettings
    consumer_group: str
    target_sample_rate_hz: int
    n_mels: int
    n_fft: int
    hop_length: int
    f_min: int
    f_max: int
    target_frames: int
    silence_threshold_db: float
    segment_silence_floor: float
    log_epsilon: float
    producer_retries: int
    producer_retry_backoff_ms: int
    producer_retry_backoff_max_ms: int
    producer_delivery_timeout_ms: int

    @classmethod
    def from_env(cls) -> "ProcessingSettings":
        return cls(
            base=load_base_service_settings("processing"),
            consumer_group=os.getenv(
                "PROCESSING_CONSUMER_GROUP",
                "event-driven-audio-analytics-processing",
            ),
            target_sample_rate_hz=int(os.getenv("TARGET_SAMPLE_RATE_HZ", "32000")),
            n_mels=int(os.getenv("N_MELS", "128")),
            n_fft=int(os.getenv("N_FFT", "1024")),
            hop_length=int(os.getenv("HOP_LENGTH", "320")),
            f_min=int(os.getenv("F_MIN", "0")),
            f_max=int(os.getenv("F_MAX", "16000")),
            target_frames=int(os.getenv("TARGET_FRAMES", "300")),
            silence_threshold_db=float(os.getenv("SILENCE_THRESHOLD_DB", "-60.0")),
            segment_silence_floor=float(os.getenv("SEGMENT_SILENCE_FLOOR", "1e-7")),
            log_epsilon=float(os.getenv("LOG_EPSILON", "1e-9")),
            producer_retries=int(os.getenv("PRODUCER_RETRIES", "10")),
            producer_retry_backoff_ms=int(os.getenv("PRODUCER_RETRY_BACKOFF_MS", "250")),
            producer_retry_backoff_max_ms=int(
                os.getenv("PRODUCER_RETRY_BACKOFF_MAX_MS", "5000")
            ),
            producer_delivery_timeout_ms=int(
                os.getenv("PRODUCER_DELIVERY_TIMEOUT_MS", "120000")
            ),
        )
