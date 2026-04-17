"""Review-response helpers and small validation utilities."""

from __future__ import annotations

from datetime import datetime


def isoformat_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def validate_run_id(run_id: str) -> str:
    normalized = run_id.strip()
    if normalized == "":
        raise ValueError("run_id must not be empty or whitespace.")
    if normalized in {".", ".."} or any(character in normalized for character in ("/", "\\", ":")):
        raise ValueError("run_id must be a single relative path segment.")
    return normalized


def normalize_limit(
    value: int | None,
    *,
    default_limit: int,
    max_limit: int,
) -> int:
    if value is None:
        return default_limit
    if value <= 0:
        raise ValueError("limit must be positive.")
    return min(value, max_limit)


def normalize_offset(value: int | None) -> int:
    if value is None:
        return 0
    if value < 0:
        raise ValueError("offset must be zero or positive.")
    return value


def build_page_payload(
    *,
    items: list[dict[str, object]],
    total: int,
    limit: int,
    offset: int,
) -> dict[str, object]:
    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": offset + len(items) < total,
    }


def build_db_provenance() -> dict[str, str]:
    return {"source": "db"}


def build_fs_provenance() -> dict[str, str]:
    return {"source": "fs"}


def build_derived_provenance() -> dict[str, str]:
    return {"source": "derived"}


def derive_run_state(summary: dict[str, object]) -> dict[str, object]:
    segments_persisted = int(summary["segments_persisted"])
    validation_failures = float(summary["validation_failures"])
    processing_error_count = int(summary["processing_error_count"])
    writer_error_count = int(summary["writer_error_count"])
    tracks_total = float(summary["tracks_total"])

    if segments_persisted > 0 and processing_error_count == 0 and writer_error_count == 0:
        if validation_failures == 0.0:
            return {
                "value": "persisted",
                "label": "Persisted",
                "reason": "Run reached TimescaleDB without downstream errors.",
                "provenance": build_derived_provenance(),
            }
        return {
            "value": "mixed",
            "label": "Mixed",
            "reason": "Some rows persisted, but the run also includes validation failures.",
            "provenance": build_derived_provenance(),
        }

    if validation_failures > 0.0 and tracks_total > 0.0:
        return {
            "value": "metadata_only",
            "label": "Metadata-only",
            "reason": "Tracks are present in metadata, but no segments reached persisted features.",
            "provenance": build_derived_provenance(),
        }

    if processing_error_count > 0 or writer_error_count > 0:
        return {
            "value": "errors",
            "label": "Errors",
            "reason": "Downstream processing or writer errors were recorded for this run.",
            "provenance": build_derived_provenance(),
        }

    return {
        "value": "empty",
        "label": "Empty",
        "reason": "The run has no persisted segments and no recorded validation outcome yet.",
        "provenance": build_derived_provenance(),
    }


def derive_track_state(track_summary: dict[str, object]) -> dict[str, object]:
    validation_status = str(track_summary["validation_status"])
    segments_persisted = int(track_summary["segments_persisted"])

    if segments_persisted > 0:
        return {
            "value": "persisted",
            "label": "Persisted",
            "reason": "This track produced persisted segment summaries.",
            "provenance": build_derived_provenance(),
        }

    return {
        "value": "metadata_only",
        "label": "Metadata-only",
        "reason": (
            "This track exists only as metadata for the current run. "
            f"validation_status={validation_status}."
        ),
        "provenance": build_derived_provenance(),
    }
