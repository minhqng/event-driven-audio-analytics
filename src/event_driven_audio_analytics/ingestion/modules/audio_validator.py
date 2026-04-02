"""Audio validation and decode/resample helpers for the ingestion service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from event_driven_audio_analytics.shared.audio import DecodedAudio, compute_rms_db, decode_audio_pyav, probe_audio
from event_driven_audio_analytics.shared.checksum import sha256_file

from .metadata_loader import MetadataRecord


VALIDATION_STATUS_VALIDATED = "validated"
VALIDATION_STATUS_MISSING_FILE = "missing_file"
VALIDATION_STATUS_PROBE_FAILED = "probe_failed"
VALIDATION_STATUS_TOO_SHORT = "too_short"
VALIDATION_STATUS_DECODE_FAILED = "decode_failed"
VALIDATION_STATUS_SILENT = "silent"


@dataclass(slots=True)
class ValidationResult:
    """Tracks validation outcome before segmentation and artifact writing."""

    record: MetadataRecord
    validation_status: str
    duration_s: float | None = None
    source_sample_rate_hz: int | None = None
    checksum: str | None = None
    decoded_audio: DecodedAudio | None = None
    rms_db: float | None = None
    validation_error: str | None = None


def validate_audio_record(
    record: MetadataRecord,
    *,
    target_sample_rate_hz: int,
    min_duration_s: float = 1.0,
    silence_threshold_db: float = -60.0,
) -> ValidationResult:
    """Validate one metadata record against the legacy fail-fast policy."""

    file_path = Path(record.source_audio_uri)
    if not file_path.exists():
        return ValidationResult(
            record=record,
            validation_status=VALIDATION_STATUS_MISSING_FILE,
            validation_error=f"Audio file does not exist: {file_path.as_posix()}",
        )

    checksum = sha256_file(file_path)

    try:
        probe = probe_audio(file_path)
    except Exception as exc:
        return ValidationResult(
            record=record,
            validation_status=VALIDATION_STATUS_PROBE_FAILED,
            checksum=checksum,
            validation_error=str(exc),
        )

    if probe.duration_s < min_duration_s:
        return ValidationResult(
            record=record,
            validation_status=VALIDATION_STATUS_TOO_SHORT,
            duration_s=probe.duration_s,
            source_sample_rate_hz=probe.sample_rate_hz,
            checksum=checksum,
            validation_error=(
                f"Audio duration {probe.duration_s:.3f}s is below the "
                f"{min_duration_s:.3f}s minimum."
            ),
        )

    try:
        decoded_audio = decode_audio_pyav(
            file_path,
            target_sample_rate_hz=target_sample_rate_hz,
        )
    except Exception as exc:
        return ValidationResult(
            record=record,
            validation_status=VALIDATION_STATUS_DECODE_FAILED,
            duration_s=probe.duration_s,
            source_sample_rate_hz=probe.sample_rate_hz,
            checksum=checksum,
            validation_error=str(exc),
        )

    rms_db = compute_rms_db(decoded_audio.waveform)
    if rms_db < silence_threshold_db:
        return ValidationResult(
            record=record,
            validation_status=VALIDATION_STATUS_SILENT,
            duration_s=probe.duration_s,
            source_sample_rate_hz=probe.sample_rate_hz,
            checksum=checksum,
            decoded_audio=decoded_audio,
            rms_db=rms_db,
            validation_error=(
                f"Audio RMS {rms_db:.3f} dB is below the "
                f"{silence_threshold_db:.3f} dB silence threshold."
            ),
        )

    return ValidationResult(
        record=record,
        validation_status=VALIDATION_STATUS_VALIDATED,
        duration_s=probe.duration_s,
        source_sample_rate_hz=probe.sample_rate_hz,
        checksum=checksum,
        decoded_audio=decoded_audio,
        rms_db=rms_db,
    )
