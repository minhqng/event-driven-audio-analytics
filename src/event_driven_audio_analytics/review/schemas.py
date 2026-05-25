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
                "reason": "Run đã ghi tới TimescaleDB và không có downstream errors.",
                "provenance": build_derived_provenance(),
            }
        return {
            "value": "mixed",
            "label": "Mixed",
            "reason": "Một số rows đã persist, nhưng run vẫn có validation failures.",
            "provenance": build_derived_provenance(),
        }

    if validation_failures > 0.0 and tracks_total > 0.0:
        return {
            "value": "metadata_only",
            "label": "Metadata-only",
            "reason": "Tracks đã có trong metadata, nhưng chưa có segments nào tới persisted features.",
            "provenance": build_derived_provenance(),
        }

    if processing_error_count > 0 or writer_error_count > 0:
        return {
            "value": "errors",
            "label": "Errors",
            "reason": "Run này đã ghi nhận downstream processing hoặc writer errors.",
            "provenance": build_derived_provenance(),
        }

    return {
        "value": "empty",
        "label": "Empty",
        "reason": "Run chưa có persisted segments và chưa có validation outcome được ghi nhận.",
        "provenance": build_derived_provenance(),
    }


def derive_track_state(track_summary: dict[str, object]) -> dict[str, object]:
    validation_status = str(track_summary["validation_status"])
    segments_persisted = int(track_summary["segments_persisted"])

    if segments_persisted > 0:
        return {
            "value": "persisted",
            "label": "Persisted",
            "reason": "Track này đã tạo persisted segment summaries.",
            "provenance": build_derived_provenance(),
        }

    return {
        "value": "metadata_only",
        "label": "Metadata-only",
        "reason": (
            "Track này hiện chỉ tồn tại ở metadata của run hiện tại. "
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
            reason="Run summary metadata đã có trong review payload.",
        )
    else:
        metadata_stage = _stage_item(
            stage_id="metadata",
            label="Metadata",
            value="empty",
            reason="Review payload chưa có run summary rows, tracks, segments hoặc errors.",
        )

    if not has_any_run_signal:
        validation_stage = _stage_item(
            stage_id="validation",
            label="Validation",
            value="empty",
            reason="Chưa có validation outcomes vì run chưa có review data quan sát được.",
        )
    elif validation_failures > 0.0:
        validation_stage = _stage_item(
            stage_id="validation",
            label="Validation",
            value="degraded",
            reason="Validation outcomes có rejected hoặc non-persisted track metadata.",
        )
    elif validation_outcomes:
        validation_stage = _stage_item(
            stage_id="validation",
            label="Validation",
            value="ready",
            reason="Đã có validation outcome counts và không ghi nhận validation failures.",
        )
    else:
        validation_stage = _stage_item(
            stage_id="validation",
            label="Validation",
            value="unknown",
            reason="Run metadata đã có, nhưng chưa trả về validation outcome counts.",
        )

    if processing_error_count > 0 or writer_error_count > 0:
        features_stage = _stage_item(
            stage_id="features",
            label="Features",
            value="failed",
            reason="Run này có processing hoặc writer error counts.",
        )
    elif segments_persisted > 0:
        features_stage = _stage_item(
            stage_id="features",
            label="Features",
            value="ready",
            reason="Persisted segment feature rows đã có trong review summary.",
        )
    else:
        features_stage = _stage_item(
            stage_id="features",
            label="Features",
            value="empty",
            reason="Review summary chưa có persisted segment feature rows.",
        )

    if segments_persisted <= 0:
        artifacts_stage = _stage_item(
            stage_id="artifacts",
            label="Artifacts",
            value="empty",
            reason="Chưa có persisted segment rows để chứng minh review artifacts.",
        )
    elif processing_state_read_error:
        artifacts_stage = _stage_item(
            stage_id="artifacts",
            label="Artifacts",
            value="degraded",
            reason=f"Persisted segments đã có, nhưng không đọc được processing state: {processing_state_read_error}",
        )
    elif manifest_exists:
        artifacts_stage = _stage_item(
            stage_id="artifacts",
            label="Artifacts",
            value="ready",
            reason="Run đã có manifest reference và persisted segment rows.",
        )
    else:
        artifacts_stage = _stage_item(
            stage_id="artifacts",
            label="Artifacts",
            value="degraded",
            reason="Persisted segment rows đã có, nhưng chưa quan sát được manifest reference tồn tại.",
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
            reason="Chưa có review data để tổng hợp cho run này.",
        )
    elif upstream_values == {"ready"}:
        review_stage = _stage_item(
            stage_id="review",
            label="Review",
            value="ready",
            reason="Tất cả review stages quan sát được đều ready từ persisted payload evidence.",
        )
    elif "unknown" in upstream_values:
        review_stage = _stage_item(
            stage_id="review",
            label="Review",
            value="unknown",
            reason="Một số review stage evidence đang thiếu trong payload.",
        )
    else:
        review_stage = _stage_item(
            stage_id="review",
            label="Review",
            value="degraded",
            reason="Một hoặc nhiều review stages quan sát được chưa hoàn tất hoặc có errors.",
        )

    return {
        "items": [metadata_stage, validation_stage, features_stage, artifacts_stage, review_stage],
        "provenance": build_derived_provenance(),
    }
