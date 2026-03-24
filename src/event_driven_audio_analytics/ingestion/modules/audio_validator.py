"""Audio validation placeholders for the ingestion service."""

from __future__ import annotations

from dataclasses import dataclass

from .metadata_loader import MetadataRecord


@dataclass(slots=True)
class ValidationResult:
    """Tracks validation outcome before segmentation."""

    record: MetadataRecord
    validation_status: str
    checksum: str | None = None


def validate_audio_record(record: MetadataRecord) -> ValidationResult:
    """Return a placeholder validation result for a metadata record."""

    # TODO: implement path checks, decode validation, duration checks, and checksum creation.
    return ValidationResult(record=record, validation_status="todo")
