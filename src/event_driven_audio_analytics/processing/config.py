"""Configuration helpers for the processing service."""

from __future__ import annotations

from dataclasses import dataclass
import os

from event_driven_audio_analytics.shared.settings import BaseServiceSettings, load_base_service_settings


def _getenv_with_fallback(primary: str, fallback: str | None, default: str) -> str:
    """Read one environment variable with an optional legacy fallback name."""

    value = os.getenv(primary)
    if value is not None:
        return value
    if fallback is not None:
        legacy_value = os.getenv(fallback)
        if legacy_value is not None:
            return legacy_value
    return default


def _parse_bool_env(raw_value: str) -> bool:
    """Parse one conventional boolean environment value."""

    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class ProcessingSettings:
    """Runtime settings for feature extraction."""

    base: BaseServiceSettings
    consumer_group: str
    auto_offset_reset: str
    poll_timeout_s: float
    session_timeout_ms: int
    max_poll_interval_ms: int
    consumer_retry_backoff_ms: int
    consumer_retry_backoff_max_ms: int
    artifact_retry_attempts: int
    artifact_retry_backoff_ms: int
    artifact_retry_backoff_max_ms: int
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
    probe_s3_replay_readiness: bool = False

    @classmethod
    def from_env(cls) -> "ProcessingSettings":
        return cls(
            base=load_base_service_settings("processing"),
            consumer_group=os.getenv(
                "PROCESSING_CONSUMER_GROUP",
                "event-driven-audio-analytics-processing",
            ),
            auto_offset_reset=os.getenv("PROCESSING_AUTO_OFFSET_RESET", "earliest"),
            poll_timeout_s=float(os.getenv("PROCESSING_POLL_TIMEOUT_S", "1.0")),
            session_timeout_ms=int(os.getenv("PROCESSING_SESSION_TIMEOUT_MS", "45000")),
            max_poll_interval_ms=int(os.getenv("PROCESSING_MAX_POLL_INTERVAL_MS", "300000")),
            consumer_retry_backoff_ms=int(
                os.getenv("PROCESSING_CONSUMER_RETRY_BACKOFF_MS", "250")
            ),
            consumer_retry_backoff_max_ms=int(
                os.getenv("PROCESSING_CONSUMER_RETRY_BACKOFF_MAX_MS", "5000")
            ),
            artifact_retry_attempts=int(os.getenv("PROCESSING_ARTIFACT_RETRY_ATTEMPTS", "5")),
            artifact_retry_backoff_ms=int(
                os.getenv("PROCESSING_ARTIFACT_RETRY_BACKOFF_MS", "250")
            ),
            artifact_retry_backoff_max_ms=int(
                os.getenv("PROCESSING_ARTIFACT_RETRY_BACKOFF_MAX_MS", "5000")
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
            producer_retries=int(
                _getenv_with_fallback("KAFKA_PRODUCER_RETRIES", "PRODUCER_RETRIES", "10")
            ),
            producer_retry_backoff_ms=int(
                _getenv_with_fallback(
                    "KAFKA_PRODUCER_RETRY_BACKOFF_MS",
                    "PRODUCER_RETRY_BACKOFF_MS",
                    "250",
                )
            ),
            producer_retry_backoff_max_ms=int(
                _getenv_with_fallback(
                    "KAFKA_PRODUCER_RETRY_BACKOFF_MAX_MS",
                    "PRODUCER_RETRY_BACKOFF_MAX_MS",
                    "5000",
                )
            ),
            producer_delivery_timeout_ms=int(
                _getenv_with_fallback(
                    "KAFKA_PRODUCER_DELIVERY_TIMEOUT_MS",
                    "PRODUCER_DELIVERY_TIMEOUT_MS",
                    "120000",
                )
            ),
            probe_s3_replay_readiness=_parse_bool_env(
                os.getenv("PROCESSING_PROBE_S3_REPLAY_READINESS", "false")
            ),
        )
