"""Review-response helpers and small validation utilities."""

from __future__ import annotations

from datetime import datetime

from event_driven_audio_analytics.shared.storage import validate_run_id as validate_run_id


def isoformat_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


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


def _stage_item(*, stage_id: str, label: str, value: str, reason: str) -> dict[str, object]:
    return {
        "id": stage_id,
        "label": label,
        "value": value,
        "reason": reason,
        "provenance": build_derived_provenance(),
    }


def derive_pipeline_stages(
    summary: dict[str, object],
    *,
    validation_outcomes: list[dict[str, object]],
    runtime_proof: dict[str, object],
) -> dict[str, object]:
    """Derive honest review-stage statuses from persisted review evidence only.

    The stage contract intentionally avoids reporting live service health. Values are
    constrained to ready, degraded, failed, empty, and unknown, and each reason cites
    only evidence already present in the run detail payload.
    """

    tracks_total = float(summary["tracks_total"])
    segments_total = float(summary["segments_total"])
    validation_failures = float(summary["validation_failures"])
    segments_persisted = int(summary["segments_persisted"])
    processing_error_count = int(summary["processing_error_count"])
    writer_error_count = int(summary["writer_error_count"])
    total_error_events = float(summary["total_error_events"])

    manifest = runtime_proof.get("manifest", {})
    processing_state = runtime_proof.get("processing_state", {})
    manifest_exists = bool(manifest.get("exists")) if isinstance(manifest, dict) else False
    processing_state_read_error = (
        processing_state.get("read_error") if isinstance(processing_state, dict) else None
    )

    has_any_run_signal = any(
        (
            tracks_total > 0.0,
            segments_total > 0.0,
            validation_failures > 0.0,
            segments_persisted > 0,
            processing_error_count > 0,
            writer_error_count > 0,
            total_error_events > 0.0,
        )
    )

    if has_any_run_signal:
        metadata_stage = _stage_item(
            stage_id="metadata",
            label="Metadata",
            value="ready",
            reason="Run summary metadata is present in the review payload.",
        )
    else:
        metadata_stage = _stage_item(
            stage_id="metadata",
            label="Metadata",
            value="empty",
            reason="No run summary rows, tracks, segments, or errors are present in the review payload.",
        )

    if not has_any_run_signal:
        validation_stage = _stage_item(
            stage_id="validation",
            label="Validation",
            value="empty",
            reason="No validation outcomes are present because the run has no observable review data.",
        )
    elif validation_failures > 0.0:
        validation_stage = _stage_item(
            stage_id="validation",
            label="Validation",
            value="degraded",
            reason="Validation outcomes include rejected or non-persisted track metadata.",
        )
    elif validation_outcomes:
        validation_stage = _stage_item(
            stage_id="validation",
            label="Validation",
            value="ready",
            reason="Validation outcome counts are present and no validation failures are reported.",
        )
    else:
        validation_stage = _stage_item(
            stage_id="validation",
            label="Validation",
            value="unknown",
            reason="Run metadata is present, but no validation outcome counts were returned.",
        )

    if processing_error_count > 0 or writer_error_count > 0:
        features_stage = _stage_item(
            stage_id="features",
            label="Features",
            value="failed",
            reason="Processing or writer error counts are recorded for this run.",
        )
    elif segments_persisted > 0:
        features_stage = _stage_item(
            stage_id="features",
            label="Features",
            value="ready",
            reason="Persisted segment feature rows are present in the review summary.",
        )
    else:
        features_stage = _stage_item(
            stage_id="features",
            label="Features",
            value="empty",
            reason="No persisted segment feature rows are present in the review summary.",
        )

    if segments_persisted <= 0:
        artifacts_stage = _stage_item(
            stage_id="artifacts",
            label="Artifacts",
            value="empty",
            reason="No persisted segment rows are available to prove review artifacts.",
        )
    elif processing_state_read_error:
        artifacts_stage = _stage_item(
            stage_id="artifacts",
            label="Artifacts",
            value="degraded",
            reason=f"Persisted segments are present, but processing state could not be read: {processing_state_read_error}",
        )
    elif manifest_exists:
        artifacts_stage = _stage_item(
            stage_id="artifacts",
            label="Artifacts",
            value="ready",
            reason="A manifest reference exists for the run and persisted segment rows are present.",
        )
    else:
        artifacts_stage = _stage_item(
            stage_id="artifacts",
            label="Artifacts",
            value="degraded",
            reason="Persisted segment rows are present, but no existing manifest reference is observable.",
        )

    upstream_values = {
        str(metadata_stage["value"]),
        str(validation_stage["value"]),
        str(features_stage["value"]),
        str(artifacts_stage["value"]),
    }
    if upstream_values == {"empty"}:
        review_stage = _stage_item(
            stage_id="review",
            label="Review",
            value="empty",
            reason="No review data is available to summarize for this run.",
        )
    elif upstream_values == {"ready"}:
        review_stage = _stage_item(
            stage_id="review",
            label="Review",
            value="ready",
            reason="All observable review stages are ready from persisted payload evidence.",
        )
    elif "unknown" in upstream_values:
        review_stage = _stage_item(
            stage_id="review",
            label="Review",
            value="unknown",
            reason="Some review stage evidence is missing from the payload.",
        )
    else:
        review_stage = _stage_item(
            stage_id="review",
            label="Review",
            value="degraded",
            reason="One or more observable review stages are incomplete or recorded errors.",
        )

    return {
        "items": [metadata_stage, validation_stage, features_stage, artifacts_stage, review_stage],
        "provenance": build_derived_provenance(),
    }
