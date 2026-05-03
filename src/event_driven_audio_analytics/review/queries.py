"""Read-only queries for the run review service."""

from __future__ import annotations

from dataclasses import dataclass
from json import JSONDecodeError
import json
from pathlib import Path

from event_driven_audio_analytics.shared.db import open_database_connection
from event_driven_audio_analytics.shared.storage import (
    build_claim_check_store,
    build_claim_check_store_for_uri,
    run_root,
    validate_manifest_artifact_uri,
    validate_segment_artifact_uri,
)

from .config import ReviewSettings
from .schemas import (
    build_db_provenance,
    build_derived_provenance,
    build_fs_provenance,
    build_page_payload,
    derive_run_state,
    derive_track_state,
    isoformat_or_none,
    validate_run_id,
)


@dataclass(frozen=True, slots=True)
class SegmentArtifactRef:
    uri: str
    checksum: str
    exists: bool
    local_path: Path | None


def _store_exists_provenance(store: object) -> str:
    backend = store.settings.normalized_backend()
    return "fs" if backend == "local" else backend


def _canonical_run_root(artifacts_root: Path, run_id: str) -> Path:
    return run_root(artifacts_root, validate_run_id(run_id))


def _processing_state_path(artifacts_root: Path, run_id: str) -> Path:
    return _canonical_run_root(artifacts_root, run_id) / "state" / "processing_metrics.json"


def _derived_manifest_runtime_ref(
    settings: ReviewSettings,
    *,
    run_id: str,
) -> tuple[str, bool, str]:
    store = build_claim_check_store(settings.base.storage)
    manifest_uri_value = store.manifest_uri(run_id)
    return (
        manifest_uri_value,
        store.exists(manifest_uri_value),
        _store_exists_provenance(store),
    )


def lookup_segment_artifact_path(
    settings: ReviewSettings,
    *,
    run_id: str,
    track_id: int,
    segment_idx: int,
) -> Path | None:
    validated_run_id = validate_run_id(run_id)
    with open_database_connection(settings.database) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT artifact_uri, checksum
                FROM audio_features
                WHERE run_id = %s
                  AND track_id = %s
                  AND segment_idx = %s
                ORDER BY ts DESC
                LIMIT 1;
                """,
                (validated_run_id, track_id, segment_idx),
            )
            row = cursor.fetchone()
    if row is None:
        return None
    try:
        uri = str(row[0])
        store = build_claim_check_store_for_uri(settings.base.storage, uri)
        validate_segment_artifact_uri(
            uri,
            run_id=validated_run_id,
            track_id=track_id,
            segment_idx=segment_idx,
            bucket=store.settings.bucket,
        )
        return store.local_path(uri)
    except ValueError:
        return None


def lookup_segment_artifact_ref(
    settings: ReviewSettings,
    *,
    run_id: str,
    track_id: int,
    segment_idx: int,
) -> SegmentArtifactRef | None:
    validated_run_id = validate_run_id(run_id)
    with open_database_connection(settings.database) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT artifact_uri
                FROM audio_features
                WHERE run_id = %s
                  AND track_id = %s
                  AND segment_idx = %s
                ORDER BY ts DESC
                LIMIT 1;
                """,
                (validated_run_id, track_id, segment_idx),
            )
            row = cursor.fetchone()
    if row is None:
        return None

    uri = str(row[0])
    checksum = str(row[1])
    store = build_claim_check_store_for_uri(settings.base.storage, uri)
    try:
        validate_segment_artifact_uri(
            uri,
            run_id=validated_run_id,
            track_id=track_id,
            segment_idx=segment_idx,
            bucket=store.settings.bucket,
        )
        return SegmentArtifactRef(
            uri=uri,
            checksum=checksum,
            exists=store.exists(uri),
            local_path=store.local_path(uri),
        )
    except ValueError:
        return None


def _build_run_item(row: tuple[object, ...]) -> dict[str, object]:
    summary = {
        "run_id": str(row[0]),
        "first_seen_at": isoformat_or_none(row[1]),
        "last_seen_at": isoformat_or_none(row[2]),
        "tracks_total": float(row[3]),
        "segments_total": float(row[4]),
        "validation_failures": float(row[5]),
        "artifact_write_ms": float(row[6]),
        "segments_persisted": int(row[7]),
        "avg_rms": None if row[8] is None else float(row[8]),
        "avg_processing_ms": None if row[9] is None else float(row[9]),
        "silent_ratio": float(row[10]),
        "processing_error_count": int(row[11]),
        "writer_error_count": int(row[12]),
        "total_error_events": float(row[13]),
        "error_rate": float(row[14]),
    }
    summary["state"] = derive_run_state(summary)
    summary["provenance"] = build_db_provenance()
    summary["links"] = {
        "detail_url": f"/api/runs/{summary['run_id']}",
        "tracks_url": f"/api/runs/{summary['run_id']}/tracks",
    }
    return summary


def _build_track_item(row: tuple[object, ...]) -> dict[str, object]:
    summary = {
        "run_id": str(row[0]),
        "track_id": int(row[1]),
        "artist_id": int(row[2]),
        "genre": str(row[3]),
        "subset": str(row[4]),
        "source_audio_uri": str(row[5]),
        "validation_status": str(row[6]),
        "duration_s": float(row[7]),
        "manifest_uri": row[8],
        "checksum": row[9],
        "segments_persisted": int(row[10]),
        "silent_segments": int(row[11]),
        "silent_ratio": None if row[12] is None else float(row[12]),
        "avg_rms": None if row[13] is None else float(row[13]),
        "avg_processing_ms": None if row[14] is None else float(row[14]),
        "track_state_value": str(row[15]),
    }
    summary["track_state"] = derive_track_state(summary)
    summary["provenance"] = build_db_provenance()
    summary["links"] = {
        "detail_url": f"/api/runs/{summary['run_id']}/tracks/{summary['track_id']}",
    }
    return summary


def list_runs(
    settings: ReviewSettings,
    *,
    limit: int,
    offset: int,
    demo_mode: bool,
) -> dict[str, object]:
    pinned_run_ids = list(settings.pinned_run_ids)
    with open_database_connection(settings.database) as connection:
        with connection.cursor() as cursor:
            if demo_mode and pinned_run_ids:
                cursor.execute(
                    """
                    SELECT
                        run_id,
                        first_seen_at,
                        last_seen_at,
                        tracks_total,
                        segments_total,
                        validation_failures,
                        artifact_write_ms,
                        segments_persisted,
                        avg_rms,
                        avg_processing_ms,
                        silent_ratio,
                        processing_error_count,
                        writer_error_count,
                        total_error_events,
                        error_rate,
                        COUNT(*) OVER() AS total_count
                    FROM vw_dashboard_run_summary
                    WHERE run_id = ANY(%s)
                    ORDER BY
                        array_position(%s::text[], run_id) ASC,
                        last_seen_at DESC NULLS LAST,
                        run_id DESC
                    LIMIT %s OFFSET %s;
                    """,
                    (pinned_run_ids, pinned_run_ids, limit, offset),
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        run_id,
                        first_seen_at,
                        last_seen_at,
                        tracks_total,
                        segments_total,
                        validation_failures,
                        artifact_write_ms,
                        segments_persisted,
                        avg_rms,
                        avg_processing_ms,
                        silent_ratio,
                        processing_error_count,
                        writer_error_count,
                        total_error_events,
                        error_rate,
                        COUNT(*) OVER() AS total_count
                    FROM vw_dashboard_run_summary
                    ORDER BY last_seen_at DESC NULLS LAST, run_id DESC
                    LIMIT %s OFFSET %s;
                    """,
                    (limit, offset),
                )
            rows = cursor.fetchall()

    total = int(rows[0][15]) if rows else 0
    items = [_build_run_item(row[:15]) for row in rows]
    payload = build_page_payload(items=items, total=total, limit=limit, offset=offset)
    payload["mode"] = {
        "demo_mode": demo_mode,
        "pinned_run_ids": list(settings.pinned_run_ids) if demo_mode else [],
        "provenance": build_derived_provenance(),
    }
    return payload


def get_run_detail(settings: ReviewSettings, run_id: str) -> dict[str, object] | None:
    validated_run_id = validate_run_id(run_id)
    with open_database_connection(settings.database) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    run_id,
                    first_seen_at,
                    last_seen_at,
                    tracks_total,
                    segments_total,
                    validation_failures,
                    artifact_write_ms,
                    segments_persisted,
                    avg_rms,
                    avg_processing_ms,
                    silent_ratio,
                    processing_error_count,
                    writer_error_count,
                    total_error_events,
                    error_rate
                FROM vw_dashboard_run_summary
                WHERE run_id = %s;
                """,
                (validated_run_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            cursor.execute(
                """
                SELECT validation_status, track_count
                FROM vw_dashboard_run_validation
                WHERE run_id = %s
                ORDER BY validation_status ASC;
                """,
                (validated_run_id,),
            )
            validation_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    topic_name,
                    partition_id,
                    last_committed_offset,
                    updated_at
                FROM run_checkpoints
                WHERE run_id = %s
                ORDER BY topic_name ASC, partition_id ASC;
                """,
                (validated_run_id,),
            )
            checkpoint_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT manifest_uri
                FROM audio_features
                WHERE run_id = %s
                  AND manifest_uri IS NOT NULL
                ORDER BY ts DESC, track_id ASC, segment_idx ASC
                LIMIT 1;
                """,
                (validated_run_id,),
            )
            manifest_row = cursor.fetchone()

    if manifest_row is not None and manifest_row[0] is not None:
        manifest_uri_value = str(manifest_row[0])
        manifest_store = build_claim_check_store_for_uri(settings.base.storage, manifest_uri_value)
        try:
            validate_manifest_artifact_uri(
                manifest_uri_value,
                run_id=validated_run_id,
                bucket=manifest_store.settings.bucket,
            )
            manifest_exists = manifest_store.exists(manifest_uri_value)
        except ValueError:
            manifest_exists = False
        manifest_exists_provenance = _store_exists_provenance(manifest_store)
    else:
        manifest_uri_value, manifest_exists, manifest_exists_provenance = _derived_manifest_runtime_ref(
            settings,
            run_id=validated_run_id,
        )
    processing_state_path = _processing_state_path(settings.base.artifacts_root, validated_run_id)

    processing_state_payload: dict[str, object] | None = None
    processing_state_error: str | None = None
    if processing_state_path.exists():
        try:
            raw_state = json.loads(processing_state_path.read_text(encoding="utf-8"))
            if not isinstance(raw_state, dict):
                raise TypeError("Processing state must decode to an object.")
            segments = raw_state.get("segments", [])
            if not isinstance(segments, list):
                raise TypeError("Processing state field segments must decode to a list.")
            silent_segments = sum(
                1
                for segment in segments
                if isinstance(segment, dict) and bool(segment.get("silent_flag"))
            )
            segment_count = len(segments)
            processing_state_payload = {
                "run_id": raw_state.get("run_id"),
                "segment_count": segment_count,
                "silent_segments": silent_segments,
                "silent_ratio": 0.0 if segment_count == 0 else silent_segments / float(segment_count),
                "provenance": build_fs_provenance(),
            }
        except (OSError, TypeError, JSONDecodeError) as exc:
            processing_state_error = str(exc)

    summary = _build_run_item(row)
    return {
        "run": summary,
        "validation_outcomes": {
            "items": [
                {
                    "validation_status": str(validation_status),
                    "track_count": int(track_count),
                    "provenance": build_db_provenance(),
                }
                for validation_status, track_count in validation_rows
            ],
            "provenance": build_db_provenance(),
        },
        "runtime_proof": {
            "emphasis": "secondary",
            "provenance": build_derived_provenance(),
            "manifest": {
                "path": manifest_uri_value,
                "exists": manifest_exists,
                "provenance": {
                    "path": "claim_check_uri",
                    "exists": manifest_exists_provenance,
                },
            },
            "processing_state": {
                "path": processing_state_path.as_posix(),
                "exists": processing_state_path.exists(),
                "state": processing_state_payload,
                "read_error": processing_state_error,
                "provenance": {
                    "path": "fs",
                    "exists": "fs",
                    "state": "fs" if processing_state_payload is not None else "fs",
                },
            },
            "checkpoints": {
                "items": [
                    {
                        "topic_name": str(topic_name),
                        "partition_id": int(partition_id),
                        "last_committed_offset": int(last_committed_offset),
                        "updated_at": isoformat_or_none(updated_at),
                        "provenance": build_db_provenance(),
                    }
                    for topic_name, partition_id, last_committed_offset, updated_at in checkpoint_rows
                ],
                "provenance": build_db_provenance(),
            },
        },
        "links": {
            "tracks_url": f"/api/runs/{validated_run_id}/tracks",
        },
    }


def list_tracks_for_run(
    settings: ReviewSettings,
    *,
    run_id: str,
    limit: int,
    offset: int,
) -> dict[str, object]:
    validated_run_id = validate_run_id(run_id)
    with open_database_connection(settings.database) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    run_id,
                    track_id,
                    artist_id,
                    genre,
                    subset,
                    source_audio_uri,
                    validation_status,
                    duration_s,
                    manifest_uri,
                    checksum,
                    segments_persisted,
                    silent_segments,
                    silent_ratio,
                    avg_rms,
                    avg_processing_ms,
                    track_state,
                    COUNT(*) OVER() AS total_count
                FROM vw_review_tracks
                WHERE run_id = %s
                ORDER BY track_id ASC
                LIMIT %s OFFSET %s;
                """,
                (validated_run_id, limit, offset),
            )
            rows = cursor.fetchall()

    total = int(rows[0][16]) if rows else 0
    items = [_build_track_item(row[:16]) for row in rows]
    payload = build_page_payload(items=items, total=total, limit=limit, offset=offset)
    payload["run_id"] = validated_run_id
    payload["provenance"] = build_db_provenance()
    return payload


def get_track_detail(
    settings: ReviewSettings,
    *,
    run_id: str,
    track_id: int,
    segments_limit: int,
    segments_offset: int,
) -> dict[str, object] | None:
    validated_run_id = validate_run_id(run_id)
    with open_database_connection(settings.database) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    run_id,
                    track_id,
                    artist_id,
                    genre,
                    subset,
                    source_audio_uri,
                    validation_status,
                    duration_s,
                    manifest_uri,
                    checksum,
                    segments_persisted,
                    silent_segments,
                    silent_ratio,
                    avg_rms,
                    avg_processing_ms,
                    track_state
                FROM vw_review_tracks
                WHERE run_id = %s
                  AND track_id = %s;
                """,
                (validated_run_id, track_id),
            )
            track_row = cursor.fetchone()
            if track_row is None:
                return None

            cursor.execute(
                """
                SELECT
                    ts,
                    segment_idx,
                    rms,
                    silent_flag,
                    processing_ms,
                    artifact_uri,
                    checksum,
                    manifest_uri,
                    COUNT(*) OVER() AS total_count
                FROM audio_features
                WHERE run_id = %s
                  AND track_id = %s
                ORDER BY segment_idx ASC
                LIMIT %s OFFSET %s;
                """,
                (validated_run_id, track_id, segments_limit, segments_offset),
            )
            segment_rows = cursor.fetchall()

    segments_total = int(segment_rows[0][8]) if segment_rows else 0
    segment_items: list[dict[str, object]] = []
    for ts, segment_idx, rms, silent_flag, processing_ms, artifact_uri, checksum, manifest_uri, _total in segment_rows:
        uri = str(artifact_uri)
        store = build_claim_check_store_for_uri(settings.base.storage, uri)
        try:
            validate_segment_artifact_uri(
                uri,
                run_id=validated_run_id,
                track_id=track_id,
                segment_idx=int(segment_idx),
                bucket=store.settings.bucket,
            )
            artifact_exists = store.exists(uri)
        except ValueError:
            artifact_exists = False
        artifact_exists_provenance = _store_exists_provenance(store)
        segment_items.append(
            {
                "ts": isoformat_or_none(ts),
                "segment_idx": int(segment_idx),
                "rms": float(rms),
                "silent_flag": bool(silent_flag),
                "processing_ms": float(processing_ms),
                "checksum": str(checksum),
                "manifest_uri": manifest_uri,
                "provenance": build_db_provenance(),
                "artifact": {
                    "uri": str(artifact_uri),
                    "media_url": (
                        f"/media/runs/{validated_run_id}/segments/{track_id}/{int(segment_idx)}.wav"
                    ),
                    "exists": artifact_exists,
                    "provenance": {
                        "uri": "db",
                        "media_url": "derived",
                        "exists": artifact_exists_provenance,
                    },
                },
            }
        )

    return {
        "run_id": validated_run_id,
        "track": _build_track_item(track_row),
        "segments": build_page_payload(
            items=segment_items,
            total=segments_total,
            limit=segments_limit,
            offset=segments_offset,
        ),
    }
