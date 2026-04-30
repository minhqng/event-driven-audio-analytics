"""Build deterministic FMA-Small dataset bundles from persisted run truth."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import shutil

from event_driven_audio_analytics.shared.checksum import sha256_file
from event_driven_audio_analytics.shared.db import open_database_connection
from event_driven_audio_analytics.shared.settings import DatabaseSettings
from event_driven_audio_analytics.shared.storage import (
    resolve_artifact_uri,
    run_root,
    validate_run_id,
)


FORMAT_VERSION = "fma-small-dataset-bundle.v1"
GENERATOR_VERSION = "dataset-exporter-mvp.v1"
TRAINING_SPLIT_FORMAT_VERSION = "fma-small-training-splits.v1"
NORMALIZATION_STATS_FORMAT_VERSION = "fma-small-normalization-stats.v1"
EXPECTED_SUBSET = "small"
EXPECTED_MEL_BINS = 128
EXPECTED_MEL_FRAMES = 300
HIGH_SILENT_RATIO_THRESHOLD = 0.95
SPLIT_RATIOS = {
    "train": 0.8,
    "validation": 0.1,
    "test": 0.1,
}
SPLIT_NAMES = tuple(SPLIT_RATIOS)
BUNDLE_FILE_NAMES = (
    "dataset-build-manifest.json",
    "run-summary.json",
    "quality-verdict.json",
    "accepted-tracks.csv",
    "rejected-tracks.csv",
    "accepted-segments.csv",
    "rejected-segments.csv",
    "anomaly-summary.json",
    "label-map.json",
    "dataset-card.md",
)
TRAINING_SPLIT_FILE_NAMES = (
    "splits/split-manifest.json",
    "splits/train.parquet",
    "splits/validation.parquet",
    "splits/test.parquet",
    "stats/normalization-stats.json",
)

ACCEPTED_TRACK_FIELDS = (
    "run_id",
    "track_id",
    "artist_id",
    "genre",
    "label_id",
    "subset",
    "source_audio_uri",
    "duration_s",
    "checksum",
    "segments_persisted",
    "avg_rms",
    "silent_ratio",
    "manifest_uri",
)
REJECTED_TRACK_FIELDS = (
    "run_id",
    "track_id",
    "artist_id",
    "genre",
    "subset",
    "source_audio_uri",
    "duration_s",
    "checksum",
    "validation_status",
    "rejection_reason",
    "manifest_uri",
)
ACCEPTED_SEGMENT_FIELDS = (
    "run_id",
    "track_id",
    "segment_idx",
    "label_id",
    "genre",
    "artifact_uri",
    "checksum",
    "manifest_uri",
    "rms",
    "silent_flag",
    "mel_bins",
    "mel_frames",
    "processing_ms",
)
REJECTED_SEGMENT_FIELDS = (
    "run_id",
    "track_id",
    "segment_idx",
    "artifact_uri",
    "reason",
    "source",
)
TRAINING_SPLIT_FIELDS = (
    "run_id",
    "split",
    "track_id",
    "artist_id",
    "genre",
    "label_id",
    "subset",
    "segment_idx",
    "artifact_uri",
    "checksum",
    "manifest_uri",
    "rms",
    "silent_flag",
    "mel_bins",
    "mel_frames",
    "processing_ms",
    "source_audio_uri",
    "track_duration_s",
    "track_checksum",
    "segments_persisted",
    "track_avg_rms",
    "track_silent_ratio",
)


@dataclass(frozen=True, slots=True)
class RunSummaryRow:
    run_id: str
    first_seen_at: str | None
    last_seen_at: str | None
    tracks_total: float
    segments_total: float
    validation_failures: float
    artifact_write_ms: float
    segments_persisted: int
    avg_rms: float | None
    avg_processing_ms: float | None
    silent_ratio: float
    processing_error_count: int
    writer_error_count: int
    total_error_events: float
    error_rate: float


@dataclass(frozen=True, slots=True)
class TrackRow:
    run_id: str
    track_id: int
    artist_id: int | None
    genre: str
    subset: str
    source_audio_uri: str
    validation_status: str
    duration_s: float
    manifest_uri: str | None
    checksum: str | None
    segments_persisted: int
    silent_segments: int
    silent_ratio: float | None
    avg_rms: float | None
    avg_processing_ms: float | None
    track_state: str


@dataclass(frozen=True, slots=True)
class FeatureRow:
    run_id: str
    track_id: int
    segment_idx: int
    artifact_uri: str
    checksum: str
    manifest_uri: str | None
    rms: float
    silent_flag: bool
    mel_bins: int
    mel_frames: int
    processing_ms: float


@dataclass(frozen=True, slots=True)
class ManifestSegmentRow:
    run_id: str
    track_id: int
    segment_idx: int
    artifact_uri: str
    checksum: str
    manifest_uri: str | None
    sample_rate: int | None = None
    duration_s: float | None = None
    is_last_segment: bool | None = None


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    run_id: str
    run_summary: RunSummaryRow
    tracks: tuple[TrackRow, ...]
    features: tuple[FeatureRow, ...]


@dataclass(frozen=True, slots=True)
class Anomaly:
    type: str
    severity: str
    message: str
    example: dict[str, object]


@dataclass(frozen=True, slots=True)
class DatasetExportResult:
    run_id: str
    output_dir: Path
    file_count: int
    quality_verdict: str
    accepted_tracks: int
    rejected_tracks: int
    accepted_segments: int
    rejected_segments: int


@dataclass(slots=True)
class _ClassifiedBundle:
    accepted_tracks: list[dict[str, object]]
    rejected_tracks: list[dict[str, object]]
    accepted_segments: list[dict[str, object]]
    rejected_segments: list[dict[str, object]]
    label_map: dict[str, object]
    anomalies: list[Anomaly]
    quality_verdict: dict[str, object]
    run_summary: dict[str, object]


@dataclass(frozen=True, slots=True)
class _TrainingSplitResult:
    files: dict[str, int | None]
    split_manifest: dict[str, object]


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, default=_json_default, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _write_csv(
    path: Path,
    *,
    fieldnames: tuple[str, ...],
    rows: list[dict[str, object]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fieldnames),
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field_name: _csv_value(row.get(field_name)) for field_name in fieldnames})


def _isoformat_or_none(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _row_count(path: Path) -> int | None:
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return max(sum(1 for _ in handle) - 1, 0)
    return None


def _manifest_path(artifacts_root: Path, run_id: str) -> Path:
    return run_root(artifacts_root, run_id) / "manifests" / "segments.parquet"


def _load_manifest_rows(
    *,
    artifacts_root: Path,
    snapshot: SourceSnapshot,
) -> tuple[tuple[ManifestSegmentRow, ...], list[Anomaly]]:
    path = _manifest_path(artifacts_root, snapshot.run_id)
    manifest_required = bool(snapshot.features) or any(
        track.validation_status == "validated" and track.segments_persisted > 0
        for track in snapshot.tracks
    )
    if not path.exists():
        if not manifest_required:
            return (), []
        return (), [
            Anomaly(
                type="segment_manifest_missing",
                severity="blocking",
                message="Required claim-check segment manifest is missing.",
                example={"path": path.as_posix()},
            )
        ]

    try:
        import polars as pl

        rows = pl.read_parquet(path).to_dicts()
    except Exception as exc:
        return (), [
            Anomaly(
                type="segment_manifest_unreadable",
                severity="blocking",
                message="Claim-check segment manifest could not be read.",
                example={"path": path.as_posix(), "error": str(exc)},
            )
        ]

    manifest_rows: list[ManifestSegmentRow] = []
    anomalies: list[Anomaly] = []
    required_fields = {"run_id", "track_id", "segment_idx", "artifact_uri", "checksum"}
    for row in rows:
        missing = sorted(required_fields - set(row))
        if missing:
            anomalies.append(
                Anomaly(
                    type="segment_manifest_schema_invalid",
                    severity="blocking",
                    message="Claim-check segment manifest row is missing required fields.",
                    example={"missing_fields": missing},
                )
            )
            continue
        if str(row["run_id"]) != snapshot.run_id:
            anomalies.append(
                Anomaly(
                    type="segment_manifest_run_id_mismatch",
                    severity="blocking",
                    message="Claim-check segment manifest row belongs to another run.",
                    example={
                        "expected_run_id": snapshot.run_id,
                        "actual_run_id": str(row["run_id"]),
                    },
                )
            )
            continue
        manifest_rows.append(
            ManifestSegmentRow(
                run_id=str(row["run_id"]),
                track_id=int(row["track_id"]),
                segment_idx=int(row["segment_idx"]),
                artifact_uri=str(row["artifact_uri"]),
                checksum=str(row["checksum"]),
                manifest_uri=str(row["manifest_uri"]) if row.get("manifest_uri") else None,
                sample_rate=int(row["sample_rate"]) if row.get("sample_rate") is not None else None,
                duration_s=float(row["duration_s"]) if row.get("duration_s") is not None else None,
                is_last_segment=(
                    bool(row["is_last_segment"]) if row.get("is_last_segment") is not None else None
                ),
            )
        )
    return tuple(manifest_rows), anomalies


def _add_anomaly(
    anomalies: list[Anomaly],
    *,
    anomaly_type: str,
    severity: str,
    message: str,
    example: dict[str, object],
) -> None:
    anomalies.append(
        Anomaly(
            type=anomaly_type,
            severity=severity,
            message=message,
            example=example,
        )
    )


def _build_manifest_index(
    manifest_rows: tuple[ManifestSegmentRow, ...],
    anomalies: list[Anomaly],
) -> dict[tuple[int, int], ManifestSegmentRow]:
    manifest_by_key: dict[tuple[int, int], ManifestSegmentRow] = {}
    for row in manifest_rows:
        key = (row.track_id, row.segment_idx)
        if key in manifest_by_key:
            _add_anomaly(
                anomalies,
                anomaly_type="duplicate_manifest_segment_key",
                severity="blocking",
                message="Segment manifest contains duplicate logical segment keys.",
                example={"track_id": row.track_id, "segment_idx": row.segment_idx},
            )
            continue
        manifest_by_key[key] = row
    return manifest_by_key


def _group_features(
    features: tuple[FeatureRow, ...],
    anomalies: list[Anomaly],
) -> dict[tuple[int, int], list[FeatureRow]]:
    features_by_key: dict[tuple[int, int], list[FeatureRow]] = {}
    for feature in features:
        features_by_key.setdefault((feature.track_id, feature.segment_idx), []).append(feature)

    for (track_id, segment_idx), rows in sorted(features_by_key.items()):
        if len(rows) > 1:
            _add_anomaly(
                anomalies,
                anomaly_type="duplicate_audio_features_key",
                severity="blocking",
                message="audio_features contains duplicate logical segment keys.",
                example={"track_id": track_id, "segment_idx": segment_idx, "count": len(rows)},
            )
    return features_by_key


def _artifact_rejection_reasons(
    *,
    artifacts_root: Path,
    feature: FeatureRow,
    manifest_row: ManifestSegmentRow | None,
    manifest_required: bool,
    anomalies: list[Anomaly],
) -> list[str]:
    reasons: list[str] = []
    if manifest_required and manifest_row is None:
        reasons.append("manifest_row_missing")
        _add_anomaly(
            anomalies,
            anomaly_type="manifest_row_missing",
            severity="blocking",
            message="audio_features row has no matching claim-check manifest row.",
            example={"track_id": feature.track_id, "segment_idx": feature.segment_idx},
        )
    if manifest_row is not None:
        if manifest_row.artifact_uri != feature.artifact_uri:
            reasons.append("manifest_artifact_uri_mismatch")
            _add_anomaly(
                anomalies,
                anomaly_type="manifest_artifact_uri_mismatch",
                severity="blocking",
                message="audio_features artifact_uri differs from the claim-check manifest.",
                example={"track_id": feature.track_id, "segment_idx": feature.segment_idx},
            )
        if manifest_row.checksum != feature.checksum:
            reasons.append("manifest_checksum_mismatch")
            _add_anomaly(
                anomalies,
                anomaly_type="manifest_checksum_mismatch",
                severity="blocking",
                message="audio_features checksum differs from the claim-check manifest.",
                example={"track_id": feature.track_id, "segment_idx": feature.segment_idx},
            )
        if (
            manifest_row.manifest_uri
            and feature.manifest_uri
            and manifest_row.manifest_uri != feature.manifest_uri
        ):
            reasons.append("manifest_uri_mismatch")
            _add_anomaly(
                anomalies,
                anomaly_type="manifest_uri_mismatch",
                severity="blocking",
                message="audio_features manifest_uri differs from the claim-check manifest row.",
                example={"track_id": feature.track_id, "segment_idx": feature.segment_idx},
            )

    try:
        artifact_path = resolve_artifact_uri(artifacts_root, feature.artifact_uri)
    except ValueError as exc:
        reasons.append("artifact_uri_invalid")
        _add_anomaly(
            anomalies,
            anomaly_type="artifact_uri_invalid",
            severity="blocking",
            message="Segment artifact URI does not resolve inside artifacts_root.",
            example={
                "track_id": feature.track_id,
                "segment_idx": feature.segment_idx,
                "artifact_uri": feature.artifact_uri,
                "error": str(exc),
            },
        )
        return reasons

    if not artifact_path.exists():
        reasons.append("artifact_missing")
        _add_anomaly(
            anomalies,
            anomaly_type="artifact_missing",
            severity="blocking",
            message="Segment artifact referenced by audio_features is missing.",
            example={
                "track_id": feature.track_id,
                "segment_idx": feature.segment_idx,
                "artifact_uri": feature.artifact_uri,
            },
        )
        return reasons

    actual_checksum = sha256_file(artifact_path)
    if actual_checksum != feature.checksum:
        reasons.append("artifact_checksum_mismatch")
        _add_anomaly(
            anomalies,
            anomaly_type="artifact_checksum_mismatch",
            severity="blocking",
            message="Segment artifact checksum does not match audio_features.",
            example={
                "track_id": feature.track_id,
                "segment_idx": feature.segment_idx,
                "expected": feature.checksum,
                "actual": actual_checksum,
            },
        )
    return reasons


def _summarize_anomalies(anomalies: list[Anomaly], *, run_id: str) -> dict[str, object]:
    groups: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for anomaly in anomalies:
        groups.setdefault(
            (anomaly.severity, anomaly.type, anomaly.message),
            [],
        ).append(anomaly.example)

    items = []
    for (severity, anomaly_type, message), examples in sorted(groups.items()):
        items.append(
            {
                "type": anomaly_type,
                "severity": severity,
                "message": message,
                "count": len(examples),
                "examples": examples[:5],
            }
        )
    return {
        "run_id": run_id,
        "total": len(anomalies),
        "items": items,
    }


def _derive_quality_verdict(anomalies: list[Anomaly], *, run_id: str) -> dict[str, object]:
    blocking = [anomaly for anomaly in anomalies if anomaly.severity == "blocking"]
    warnings = [anomaly for anomaly in anomalies if anomaly.severity == "warning"]
    if blocking:
        verdict = "fail"
    elif warnings:
        verdict = "pass_with_warnings"
    else:
        verdict = "pass"
    return {
        "run_id": run_id,
        "verdict": verdict,
        "blocking_anomaly_count": len(blocking),
        "warning_anomaly_count": len(warnings),
        "reasons": sorted({anomaly.type for anomaly in [*blocking, *warnings]}),
        "rules": {
            "blocking": [
                "missing or unreadable required segment manifest",
                "missing matching manifest row for persisted feature",
                "missing segment artifact",
                "artifact checksum mismatch",
                "duplicate logical segment keys",
                "validated track without accepted segments",
                "no accepted FMA-Small dataset tracks",
            ],
            "warning": [
                "track-level validation failures",
                "processing or writer error events",
                "high accepted-run silent ratio",
            ],
        },
    }


def _build_label_map(
    accepted_track_rows: list[TrackRow],
    accepted_segment_count_by_track: dict[int, int],
) -> dict[str, object]:
    genres = sorted({track.genre for track in accepted_track_rows})
    labels = [
        {
            "label_id": label_id,
            "genre": genre,
            "track_count": sum(1 for track in accepted_track_rows if track.genre == genre),
            "segment_count": sum(
                accepted_segment_count_by_track.get(track.track_id, 0)
                for track in accepted_track_rows
                if track.genre == genre
            ),
        }
        for label_id, genre in enumerate(genres)
    ]
    return {
        "policy": "deterministic sorted genre labels from accepted FMA-Small tracks",
        "labels": labels,
    }


def _label_id_by_genre(label_map: dict[str, object]) -> dict[str, int]:
    labels = label_map["labels"]
    if not isinstance(labels, list):
        return {}
    return {
        str(label["genre"]): int(label["label_id"])
        for label in labels
        if isinstance(label, dict)
    }


def _classify_bundle(
    *,
    snapshot: SourceSnapshot,
    artifacts_root: Path,
    manifest_rows: tuple[ManifestSegmentRow, ...],
    manifest_anomalies: list[Anomaly],
) -> _ClassifiedBundle:
    anomalies = list(manifest_anomalies)
    manifest_by_key = _build_manifest_index(manifest_rows, anomalies)
    features_by_key = _group_features(snapshot.features, anomalies)
    track_by_id = {track.track_id: track for track in snapshot.tracks}
    manifest_required = bool(snapshot.features) or any(
        track.validation_status == "validated" and track.segments_persisted > 0
        for track in snapshot.tracks
    )

    if snapshot.run_summary.validation_failures > 0:
        _add_anomaly(
            anomalies,
            anomaly_type="track_validation_failures",
            severity="warning",
            message="Run contains FMA-Small tracks rejected during ingestion validation.",
            example={"validation_failures": snapshot.run_summary.validation_failures},
        )
    if snapshot.run_summary.processing_error_count > 0:
        _add_anomaly(
            anomalies,
            anomaly_type="processing_errors_present",
            severity="warning",
            message="Run contains processing error events in system_metrics.",
            example={"processing_error_count": snapshot.run_summary.processing_error_count},
        )
    if snapshot.run_summary.writer_error_count > 0:
        _add_anomaly(
            anomalies,
            anomaly_type="writer_errors_present",
            severity="warning",
            message="Run contains writer error events in system_metrics.",
            example={"writer_error_count": snapshot.run_summary.writer_error_count},
        )
    if snapshot.run_summary.silent_ratio >= HIGH_SILENT_RATIO_THRESHOLD and snapshot.features:
        _add_anomaly(
            anomalies,
            anomaly_type="high_silent_ratio",
            severity="warning",
            message="Accepted run silent ratio is high.",
            example={"silent_ratio": snapshot.run_summary.silent_ratio},
        )

    accepted_feature_rows: list[FeatureRow] = []
    rejected_segments: list[dict[str, object]] = []
    rejected_keys: set[tuple[int, int]] = set()
    for key, rows in sorted(features_by_key.items()):
        track_id, segment_idx = key
        track = track_by_id.get(track_id)
        for feature in rows:
            reasons: list[str] = []
            if len(rows) > 1:
                reasons.append("duplicate_audio_features_key")
            if track is None:
                reasons.append("track_metadata_missing")
                _add_anomaly(
                    anomalies,
                    anomaly_type="feature_without_track_metadata",
                    severity="blocking",
                    message="audio_features row has no matching track_metadata row.",
                    example={"track_id": track_id, "segment_idx": segment_idx},
                )
            elif track.validation_status != "validated":
                reasons.append(f"track_validation_status={track.validation_status}")
                _add_anomaly(
                    anomalies,
                    anomaly_type="feature_for_rejected_track",
                    severity="blocking",
                    message="audio_features row exists for a track rejected by validation.",
                    example={
                        "track_id": track_id,
                        "segment_idx": segment_idx,
                        "validation_status": track.validation_status,
                    },
                )
            if feature.mel_bins != EXPECTED_MEL_BINS or feature.mel_frames != EXPECTED_MEL_FRAMES:
                reasons.append("unexpected_mel_shape")
                _add_anomaly(
                    anomalies,
                    anomaly_type="unexpected_mel_shape",
                    severity="blocking",
                    message="audio_features row does not match the locked log-mel summary shape.",
                    example={
                        "track_id": track_id,
                        "segment_idx": segment_idx,
                        "mel_bins": feature.mel_bins,
                        "mel_frames": feature.mel_frames,
                    },
                )

            reasons.extend(
                _artifact_rejection_reasons(
                    artifacts_root=artifacts_root,
                    feature=feature,
                    manifest_row=manifest_by_key.get(key),
                    manifest_required=manifest_required,
                    anomalies=anomalies,
                )
            )
            if reasons:
                rejected_keys.add(key)
                rejected_segments.append(
                    {
                        "run_id": snapshot.run_id,
                        "track_id": track_id,
                        "segment_idx": segment_idx,
                        "artifact_uri": feature.artifact_uri,
                        "reason": ";".join(sorted(set(reasons))),
                        "source": "audio_features",
                    }
                )
            else:
                accepted_feature_rows.append(feature)

    for key, row in sorted(manifest_by_key.items()):
        if key in features_by_key:
            continue
        rejected_keys.add(key)
        rejected_segments.append(
            {
                "run_id": snapshot.run_id,
                "track_id": row.track_id,
                "segment_idx": row.segment_idx,
                "artifact_uri": row.artifact_uri,
                "reason": "missing_audio_features_row",
                "source": "segment_manifest",
            }
        )
        _add_anomaly(
            anomalies,
            anomaly_type="manifest_segment_missing_features",
            severity="blocking",
            message="Claim-check manifest segment has no persisted audio_features row.",
            example={"track_id": row.track_id, "segment_idx": row.segment_idx},
        )

    accepted_segment_count_by_track: dict[int, int] = {}
    for feature in accepted_feature_rows:
        accepted_segment_count_by_track[feature.track_id] = (
            accepted_segment_count_by_track.get(feature.track_id, 0) + 1
        )

    accepted_track_rows: list[TrackRow] = []
    rejected_track_rows: list[dict[str, object]] = []
    for track in sorted(snapshot.tracks, key=lambda row: row.track_id):
        if track.subset != EXPECTED_SUBSET:
            reason = f"subset_not_{EXPECTED_SUBSET}"
        elif track.validation_status != "validated":
            reason = f"validation_status={track.validation_status}"
        elif accepted_segment_count_by_track.get(track.track_id, 0) <= 0:
            reason = (
                "validated_without_persisted_segments"
                if track.segments_persisted <= 0
                else "validated_without_accepted_segments"
            )
            _add_anomaly(
                anomalies,
                anomaly_type="validated_track_without_accepted_segments",
                severity="blocking",
                message="Validated track has no accepted dataset segments.",
                example={"track_id": track.track_id, "reason": reason},
            )
        else:
            accepted_track_rows.append(track)
            continue

        rejected_track_rows.append(
            {
                "run_id": track.run_id,
                "track_id": track.track_id,
                "artist_id": track.artist_id,
                "genre": track.genre,
                "subset": track.subset,
                "source_audio_uri": track.source_audio_uri,
                "duration_s": track.duration_s,
                "checksum": track.checksum,
                "validation_status": track.validation_status,
                "rejection_reason": reason,
                "manifest_uri": track.manifest_uri,
            }
        )

    label_map = _build_label_map(accepted_track_rows, accepted_segment_count_by_track)
    label_ids = _label_id_by_genre(label_map)
    accepted_track_ids = {track.track_id for track in accepted_track_rows}
    accepted_tracks = [
        {
            "run_id": track.run_id,
            "track_id": track.track_id,
            "artist_id": track.artist_id,
            "genre": track.genre,
            "label_id": label_ids[track.genre],
            "subset": track.subset,
            "source_audio_uri": track.source_audio_uri,
            "duration_s": track.duration_s,
            "checksum": track.checksum,
            "segments_persisted": track.segments_persisted,
            "avg_rms": track.avg_rms,
            "silent_ratio": track.silent_ratio,
            "manifest_uri": track.manifest_uri,
        }
        for track in accepted_track_rows
    ]
    accepted_segments = []
    for feature in sorted(accepted_feature_rows, key=lambda row: (row.track_id, row.segment_idx)):
        if feature.track_id not in accepted_track_ids:
            continue
        track = track_by_id[feature.track_id]
        manifest_row = manifest_by_key.get((feature.track_id, feature.segment_idx))
        accepted_segments.append(
            {
                "run_id": feature.run_id,
                "track_id": feature.track_id,
                "segment_idx": feature.segment_idx,
                "label_id": label_ids[track.genre],
                "genre": track.genre,
                "artifact_uri": feature.artifact_uri,
                "checksum": feature.checksum,
                "manifest_uri": (
                    manifest_row.manifest_uri
                    if manifest_row is not None and manifest_row.manifest_uri is not None
                    else feature.manifest_uri
                ),
                "rms": feature.rms,
                "silent_flag": feature.silent_flag,
                "mel_bins": feature.mel_bins,
                "mel_frames": feature.mel_frames,
                "processing_ms": feature.processing_ms,
            }
        )

    if snapshot.tracks and not accepted_tracks:
        _add_anomaly(
            anomalies,
            anomaly_type="no_accepted_dataset_tracks",
            severity="blocking",
            message="Run produced no accepted FMA-Small dataset tracks.",
            example={
                "tracks_total": len(snapshot.tracks),
                "rejected_tracks": len(rejected_track_rows),
                "accepted_segments": len(accepted_segments),
            },
        )

    rejected_segments.sort(key=lambda row: (int(row["track_id"]), int(row["segment_idx"]), str(row["source"])))
    quality_verdict = _derive_quality_verdict(anomalies, run_id=snapshot.run_id)
    run_summary = {
        "run_id": snapshot.run_id,
        "format_version": FORMAT_VERSION,
        "source_summary": asdict(snapshot.run_summary),
        "tracks": {
            "total": len(snapshot.tracks),
            "accepted": len(accepted_tracks),
            "rejected": len(rejected_track_rows),
        },
        "segments": {
            "features_persisted": len(snapshot.features),
            "accepted": len(accepted_segments),
            "rejected": len(rejected_segments),
        },
        "labels": {
            "count": len(label_map["labels"]) if isinstance(label_map["labels"], list) else 0,
        },
        "quality_verdict": quality_verdict["verdict"],
    }

    return _ClassifiedBundle(
        accepted_tracks=accepted_tracks,
        rejected_tracks=rejected_track_rows,
        accepted_segments=accepted_segments,
        rejected_segments=rejected_segments,
        label_map=label_map,
        anomalies=anomalies,
        quality_verdict=quality_verdict,
        run_summary=run_summary,
    )


def _stable_split_sort_key(*, run_id: str, group_key: object) -> str:
    return hashlib.sha256(f"{run_id}:{group_key}".encode("utf-8")).hexdigest()


def _split_group_counts(group_count: int) -> dict[str, int]:
    if group_count <= 0:
        return {split_name: 0 for split_name in SPLIT_NAMES}
    if group_count == 1:
        return {"train": 1, "validation": 0, "test": 0}
    if group_count == 2:
        return {"train": 1, "validation": 0, "test": 1}

    validation_count = max(1, int(group_count * SPLIT_RATIOS["validation"]))
    test_count = max(1, int(group_count * SPLIT_RATIOS["test"]))
    train_count = group_count - validation_count - test_count
    return {
        "train": train_count,
        "validation": validation_count,
        "test": test_count,
    }


def _assign_ordered_groups(
    *,
    run_id: str,
    group_keys: list[object],
) -> dict[object, str]:
    ordered_keys = sorted(
        group_keys,
        key=lambda key: _stable_split_sort_key(run_id=run_id, group_key=key),
    )
    counts = _split_group_counts(len(ordered_keys))
    assignments: dict[object, str] = {}
    cursor = 0
    for split_name in SPLIT_NAMES:
        for key in ordered_keys[cursor : cursor + counts[split_name]]:
            assignments[key] = split_name
        cursor += counts[split_name]
    return assignments


def _has_artist_id(track: dict[str, object]) -> bool:
    artist_id = track.get("artist_id")
    return artist_id is not None and str(artist_id) != ""


def _build_track_split_assignments(
    *,
    run_id: str,
    accepted_tracks: list[dict[str, object]],
    accepted_segments: list[dict[str, object]],
) -> tuple[dict[int, str], str, bool, str | None]:
    if not accepted_tracks or not accepted_segments:
        return {}, "none_no_accepted_segments", False, "no accepted segments available"

    track_id_by_group: dict[object, list[int]] = {}
    if all(_has_artist_id(track) for track in accepted_tracks):
        for track in accepted_tracks:
            track_id_by_group.setdefault(track["artist_id"], []).append(int(track["track_id"]))
        split_type = (
            "artist_aware_track_level"
            if len(track_id_by_group) >= len(SPLIT_NAMES)
            else "artist_aware_degraded"
        )
        artist_leakage_risk = False
        degradation_reason = (
            None
            if split_type == "artist_aware_track_level"
            else (
                f"only {len(track_id_by_group)} artist group(s) available; "
                "validation and/or test may be empty"
            )
        )
    else:
        for track in accepted_tracks:
            track_id_by_group.setdefault(track["track_id"], []).append(int(track["track_id"]))
        split_type = "track_level_fallback"
        artist_leakage_risk = True
        degradation_reason = "artist_id is unavailable for at least one accepted track"

    group_assignments = _assign_ordered_groups(
        run_id=run_id,
        group_keys=list(track_id_by_group),
    )
    track_assignments: dict[int, str] = {}
    for group_key, track_ids in track_id_by_group.items():
        split_name = group_assignments[group_key]
        for track_id in track_ids:
            track_assignments[track_id] = split_name
    return track_assignments, split_type, artist_leakage_risk, degradation_reason


def _build_training_rows_by_split(
    *,
    run_id: str,
    classified: _ClassifiedBundle,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, object]]:
    track_by_id = {
        int(track["track_id"]): track
        for track in classified.accepted_tracks
    }
    track_assignments, split_type, artist_leakage_risk, degradation_reason = (
        _build_track_split_assignments(
            run_id=run_id,
            accepted_tracks=classified.accepted_tracks,
            accepted_segments=classified.accepted_segments,
        )
    )
    rows_by_split: dict[str, list[dict[str, object]]] = {
        split_name: [] for split_name in SPLIT_NAMES
    }

    for segment in sorted(
        classified.accepted_segments,
        key=lambda row: (int(row["track_id"]), int(row["segment_idx"])),
    ):
        track_id = int(segment["track_id"])
        track = track_by_id.get(track_id)
        split_name = track_assignments.get(track_id)
        if track is None or split_name is None:
            continue
        rows_by_split[split_name].append(
            {
                "run_id": run_id,
                "split": split_name,
                "track_id": track_id,
                "artist_id": track.get("artist_id"),
                "genre": track.get("genre"),
                "label_id": track.get("label_id"),
                "subset": track.get("subset"),
                "segment_idx": segment.get("segment_idx"),
                "artifact_uri": segment.get("artifact_uri"),
                "checksum": segment.get("checksum"),
                "manifest_uri": segment.get("manifest_uri"),
                "rms": segment.get("rms"),
                "silent_flag": segment.get("silent_flag"),
                "mel_bins": segment.get("mel_bins"),
                "mel_frames": segment.get("mel_frames"),
                "processing_ms": segment.get("processing_ms"),
                "source_audio_uri": track.get("source_audio_uri"),
                "track_duration_s": track.get("duration_s"),
                "track_checksum": track.get("checksum"),
                "segments_persisted": track.get("segments_persisted"),
                "track_avg_rms": track.get("avg_rms"),
                "track_silent_ratio": track.get("silent_ratio"),
            }
        )

    return rows_by_split, {
        "split_type": split_type,
        "artist_leakage_risk": artist_leakage_risk,
        "degradation_reason": degradation_reason,
    }


def _training_split_schema() -> dict[str, object]:
    import polars as pl

    return {
        "run_id": pl.Utf8,
        "split": pl.Utf8,
        "track_id": pl.Int64,
        "artist_id": pl.Int64,
        "genre": pl.Utf8,
        "label_id": pl.Int64,
        "subset": pl.Utf8,
        "segment_idx": pl.Int64,
        "artifact_uri": pl.Utf8,
        "checksum": pl.Utf8,
        "manifest_uri": pl.Utf8,
        "rms": pl.Float64,
        "silent_flag": pl.Boolean,
        "mel_bins": pl.Int64,
        "mel_frames": pl.Int64,
        "processing_ms": pl.Float64,
        "source_audio_uri": pl.Utf8,
        "track_duration_s": pl.Float64,
        "track_checksum": pl.Utf8,
        "segments_persisted": pl.Int64,
        "track_avg_rms": pl.Float64,
        "track_silent_ratio": pl.Float64,
    }


def _write_training_split_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    import polars as pl

    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        field_name: [row.get(field_name) for row in rows]
        for field_name in TRAINING_SPLIT_FIELDS
    }
    pl.DataFrame(data, schema=_training_split_schema()).write_parquet(path)


def _numeric_stats(rows: list[dict[str, object]], field_name: str) -> dict[str, object]:
    values = [
        float(row[field_name])
        for row in rows
        if row.get(field_name) is not None
    ]
    if not values:
        return {"status": "not_available", "count": 0}
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {
        "status": "available",
        "count": len(values),
        "mean": mean,
        "std": math.sqrt(variance),
        "min": min(values),
        "max": max(values),
    }


def _label_distribution_for_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[int, str], dict[str, object]] = {}
    track_ids_by_label: dict[tuple[int, str], set[int]] = {}
    for row in rows:
        key = (int(row["label_id"]), str(row["genre"]))
        item = grouped.setdefault(
            key,
            {
                "label_id": key[0],
                "genre": key[1],
                "track_count": 0,
                "segment_count": 0,
            },
        )
        item["segment_count"] = int(item["segment_count"]) + 1
        track_ids_by_label.setdefault(key, set()).add(int(row["track_id"]))

    for key, item in grouped.items():
        item["track_count"] = len(track_ids_by_label[key])
    return [grouped[key] for key in sorted(grouped)]


def _normalization_stats_payload(
    *,
    run_id: str,
    train_rows: list[dict[str, object]],
) -> dict[str, object]:
    train_row_count = len(train_rows)
    true_count = sum(1 for row in train_rows if bool(row.get("silent_flag")))
    false_count = train_row_count - true_count
    return {
        "run_id": run_id,
        "format_version": NORMALIZATION_STATS_FORMAT_VERSION,
        "source_split": "train",
        "source_file": "splits/train.parquet",
        "status": "available" if train_rows else "not_available",
        "reason": None if train_rows else "train split has no rows",
        "row_count": train_row_count,
        "track_count": len({int(row["track_id"]) for row in train_rows}),
        "segment_count": train_row_count,
        "features": {
            field_name: _numeric_stats(train_rows, field_name)
            for field_name in ("rms", "processing_ms", "mel_bins", "mel_frames")
        },
        "silent_flag": {
            "status": "available" if train_rows else "not_available",
            "count": train_row_count,
            "true_count": true_count,
            "false_count": false_count,
            "true_ratio": true_count / train_row_count if train_row_count else None,
        },
        "label_distribution": _label_distribution_for_rows(train_rows),
        "tensor_stats": {
            "status": "not_available",
            "reason": "log-mel tensors are not persisted by the current pipeline",
        },
    }


def _split_counts(rows_by_split: dict[str, list[dict[str, object]]]) -> dict[str, dict[str, int]]:
    return {
        split_name: {
            "artists": len(
                {
                    int(row["artist_id"])
                    for row in rows
                    if row.get("artist_id") is not None
                }
            ),
            "tracks": len({int(row["track_id"]) for row in rows}),
            "segments": len(rows),
        }
        for split_name, rows in rows_by_split.items()
    }


def _split_label_distribution(
    rows_by_split: dict[str, list[dict[str, object]]],
) -> dict[str, list[dict[str, object]]]:
    return {
        split_name: _label_distribution_for_rows(rows)
        for split_name, rows in rows_by_split.items()
    }


def _split_file_items(
    *,
    output_dir: Path,
    files: dict[str, int | None],
) -> list[dict[str, object]]:
    file_items = []
    for relative_path in sorted(files):
        path = output_dir / relative_path
        file_items.append(
            {
                "path": relative_path,
                "sha256": sha256_file(path),
                "row_count": files[relative_path],
            }
        )
    return file_items


def _write_training_split_outputs(
    *,
    output_dir: Path,
    run_id: str,
    classified: _ClassifiedBundle,
) -> _TrainingSplitResult:
    rows_by_split, split_metadata = _build_training_rows_by_split(
        run_id=run_id,
        classified=classified,
    )
    split_files: dict[str, int | None] = {}
    for split_name in SPLIT_NAMES:
        relative_path = f"splits/{split_name}.parquet"
        rows = rows_by_split[split_name]
        _write_training_split_parquet(output_dir / relative_path, rows)
        split_files[relative_path] = len(rows)

    stats_path = "stats/normalization-stats.json"
    (output_dir / stats_path).parent.mkdir(parents=True, exist_ok=True)
    _write_json(
        output_dir / stats_path,
        _normalization_stats_payload(run_id=run_id, train_rows=rows_by_split["train"]),
    )
    split_files[stats_path] = None
    split_type = str(split_metadata["split_type"])
    if split_type.startswith("artist_aware"):
        split_unit = "artist groups assign tracks; segments inherit track split"
        seed_policy = "stable sha256 ordering of '<run_id>:<artist_id>'; no wall-clock randomness"
    elif split_type == "track_level_fallback":
        split_unit = "tracks assign directly; segments inherit track split"
        seed_policy = "stable sha256 ordering of '<run_id>:<track_id>'; no wall-clock randomness"
    else:
        split_unit = "none; no accepted segment rows available"
        seed_policy = "not applied because no accepted segment rows are available"

    split_manifest = {
        "run_id": run_id,
        "format_version": TRAINING_SPLIT_FORMAT_VERSION,
        "split_type": split_type,
        "split_unit": split_unit,
        "ratios": SPLIT_RATIOS,
        "seed_policy": seed_policy,
        "artist_leakage_risk": split_metadata["artist_leakage_risk"],
        "degradation_reason": split_metadata["degradation_reason"],
        "counts": _split_counts(rows_by_split),
        "label_distribution": _split_label_distribution(rows_by_split),
        "normalization_source": stats_path,
        "normalization_training_source": "splits/train.parquet",
        "tensor_export": {
            "status": "not_available",
            "reason": "log-mel tensors are not persisted by the current pipeline",
            "future_work": "persist or explicitly recompute tensor artifacts in a separately scoped phase",
        },
        "files": _split_file_items(output_dir=output_dir, files=split_files),
    }
    split_manifest_path = "splits/split-manifest.json"
    _write_json(output_dir / split_manifest_path, split_manifest)
    return _TrainingSplitResult(
        files={split_manifest_path: None, **split_files},
        split_manifest=split_manifest,
    )


def _dataset_card(
    classified: _ClassifiedBundle,
    *,
    run_id: str,
    split_manifest: dict[str, object],
) -> str:
    run_summary = classified.run_summary
    track_counts = run_summary["tracks"]
    segment_counts = run_summary["segments"]
    labels = classified.label_map["labels"]
    label_lines = []
    if isinstance(labels, list) and labels:
        for label in labels:
            if isinstance(label, dict):
                label_lines.append(f"- `{label['label_id']}`: {label['genre']}")
    else:
        label_lines.append("- No accepted labels.")

    return "\n".join(
        [
            f"# FMA-Small Dataset Bundle: {run_id}",
            "",
            "## Scope",
            "",
            "This bundle is generated for FMA-Small only. It does not include model training, "
            "model serving, or raw FMA MP3 redistribution.",
            "",
            "## Source Of Truth",
            "",
            "- Track and feature summaries: TimescaleDB persisted truth.",
            "- Audio segment references: claim-check artifacts under `artifacts/runs/<run_id>/`.",
            "- Review console and Grafana: inspection surfaces only.",
            "",
            "## Counts",
            "",
            f"- Tracks accepted: {track_counts['accepted']}",
            f"- Tracks rejected: {track_counts['rejected']}",
            f"- Segments accepted: {segment_counts['accepted']}",
            f"- Segments rejected: {segment_counts['rejected']}",
            f"- Quality verdict: `{classified.quality_verdict['verdict']}`",
            "",
            "## Labels",
            "",
            *label_lines,
            "",
            "## Acceptance Rules",
            "",
            "- Accepted tracks must be `validation_status=validated` and have accepted segments.",
            "- Accepted segments must have persisted features, matching manifest rows, existing "
            "artifacts, matching checksums, and the locked log-mel summary shape.",
            "- Rejected tracks and segments are retained as explicit output rows.",
            "",
            "## Training-Oriented Exports",
            "",
            "- Split outputs are written under `splits/` as Parquet reference tables plus split metadata.",
            f"- Split type: `{split_manifest['split_type']}`.",
            "- Split unit: artist-aware track assignment when artist metadata is available; "
            "segments inherit their track split.",
            "- Normalization statistics are written under `stats/` and computed from "
            "`splits/train.parquet` only.",
            "- See `splits/split-manifest.json` for split counts, label distribution, "
            "and leakage notes.",
            "",
            "## Known Limits",
            "",
            "- RMS, silence flags, and log-mel dimensions are exported from persisted summaries.",
            "- Actual log-mel tensors are not exported because they are not persisted by the current pipeline.",
            "- Split Parquet files contain references and scalar summaries, not tensor values.",
            "- Raw FMA MP3 files are referenced by source URI only and are not copied into the bundle.",
            "",
        ]
    )


def _write_bundle_files(
    *,
    output_dir: Path,
    run_id: str,
    classified: _ClassifiedBundle,
) -> dict[str, int | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, int | None] = {}

    json_payloads = {
        "run-summary.json": classified.run_summary,
        "quality-verdict.json": classified.quality_verdict,
        "anomaly-summary.json": _summarize_anomalies(classified.anomalies, run_id=run_id),
        "label-map.json": classified.label_map,
    }
    for relative_path, payload in json_payloads.items():
        _write_json(output_dir / relative_path, payload)
        files[relative_path] = None

    csv_payloads = {
        "accepted-tracks.csv": (ACCEPTED_TRACK_FIELDS, classified.accepted_tracks),
        "rejected-tracks.csv": (REJECTED_TRACK_FIELDS, classified.rejected_tracks),
        "accepted-segments.csv": (ACCEPTED_SEGMENT_FIELDS, classified.accepted_segments),
        "rejected-segments.csv": (REJECTED_SEGMENT_FIELDS, classified.rejected_segments),
    }
    for relative_path, (fieldnames, rows) in csv_payloads.items():
        _write_csv(output_dir / relative_path, fieldnames=fieldnames, rows=rows)
        files[relative_path] = len(rows)

    training_split_result = _write_training_split_outputs(
        output_dir=output_dir,
        run_id=run_id,
        classified=classified,
    )
    files.update(training_split_result.files)

    dataset_card_path = output_dir / "dataset-card.md"
    dataset_card_path.write_text(
        _dataset_card(
            classified,
            run_id=run_id,
            split_manifest=training_split_result.split_manifest,
        ),
        encoding="utf-8",
    )
    files["dataset-card.md"] = None
    return files


def _write_dataset_build_manifest(
    *,
    output_dir: Path,
    snapshot: SourceSnapshot,
    files: dict[str, int | None],
) -> None:
    file_items = []
    for relative_path in sorted(files):
        path = output_dir / relative_path
        file_items.append(
            {
                "path": relative_path,
                "sha256": sha256_file(path),
                "row_count": files[relative_path] if files[relative_path] is not None else _row_count(path),
            }
        )

    payload = {
        "run_id": snapshot.run_id,
        "format_version": FORMAT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generated_at": snapshot.run_summary.last_seen_at,
        "generated_at_source": "vw_dashboard_run_summary.last_seen_at",
        "source_truth": {
            "tracks": "track_metadata via vw_review_tracks",
            "features": "audio_features",
            "run_summary": "vw_dashboard_run_summary",
            "segment_manifest": f"artifacts/runs/{snapshot.run_id}/manifests/segments.parquet",
        },
        "determinism": {
            "sort_keys": ["track_id", "segment_idx"],
            "timestamp_policy": "uses persisted run last_seen_at, not wall-clock time",
        },
        "files": file_items,
    }
    _write_json(output_dir / "dataset-build-manifest.json", payload)


def _ensure_output_child(*, datasets_root: Path, output_dir: Path) -> None:
    resolved_root = datasets_root.resolve()
    resolved_output = output_dir.resolve()
    try:
        resolved_output.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            "dataset output directory must stay inside DATASET_EXPORT_ROOT "
            f"root={resolved_root.as_posix()} output={resolved_output.as_posix()}."
        ) from exc
    if resolved_output == resolved_root:
        raise ValueError("dataset output directory must include a run_id child path.")


def _remove_output_path(path: Path) -> None:
    if path.exists() or path.is_symlink():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def _publish_bundle_files(*, datasets_root: Path, output_dir: Path, staging_dir: Path) -> None:
    _ensure_output_child(datasets_root=datasets_root, output_dir=output_dir)
    _ensure_output_child(datasets_root=datasets_root, output_dir=staging_dir)
    _remove_output_path(output_dir)
    staging_dir.replace(output_dir)


def build_dataset_bundle(
    *,
    snapshot: SourceSnapshot,
    artifacts_root: Path,
    datasets_root: Path,
) -> DatasetExportResult:
    """Write the deterministic dataset bundle for one completed run."""

    run_id = validate_run_id(snapshot.run_id)
    output_dir = datasets_root / run_id
    staging_dir = datasets_root / f".{run_id}.tmp"
    manifest_rows, manifest_anomalies = _load_manifest_rows(
        artifacts_root=artifacts_root,
        snapshot=snapshot,
    )
    classified = _classify_bundle(
        snapshot=snapshot,
        artifacts_root=artifacts_root,
        manifest_rows=manifest_rows,
        manifest_anomalies=manifest_anomalies,
    )
    _ensure_output_child(datasets_root=datasets_root, output_dir=output_dir)
    _ensure_output_child(datasets_root=datasets_root, output_dir=staging_dir)
    _remove_output_path(staging_dir)
    files = _write_bundle_files(
        output_dir=staging_dir,
        run_id=run_id,
        classified=classified,
    )
    _write_dataset_build_manifest(output_dir=staging_dir, snapshot=snapshot, files=files)
    _publish_bundle_files(
        datasets_root=datasets_root,
        output_dir=output_dir,
        staging_dir=staging_dir,
    )
    return DatasetExportResult(
        run_id=run_id,
        output_dir=output_dir,
        file_count=len(files) + 1,
        quality_verdict=str(classified.quality_verdict["verdict"]),
        accepted_tracks=len(classified.accepted_tracks),
        rejected_tracks=len(classified.rejected_tracks),
        accepted_segments=len(classified.accepted_segments),
        rejected_segments=len(classified.rejected_segments),
    )


def _query_run_summary(cursor: object, *, run_id: str) -> RunSummaryRow | None:
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
        (run_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return RunSummaryRow(
        run_id=str(row[0]),
        first_seen_at=_isoformat_or_none(row[1]),
        last_seen_at=_isoformat_or_none(row[2]),
        tracks_total=float(row[3]),
        segments_total=float(row[4]),
        validation_failures=float(row[5]),
        artifact_write_ms=float(row[6]),
        segments_persisted=int(row[7]),
        avg_rms=_float_or_none(row[8]),
        avg_processing_ms=_float_or_none(row[9]),
        silent_ratio=float(row[10]),
        processing_error_count=int(row[11]),
        writer_error_count=int(row[12]),
        total_error_events=float(row[13]),
        error_rate=float(row[14]),
    )


def _query_tracks(cursor: object, *, run_id: str) -> tuple[TrackRow, ...]:
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
        ORDER BY track_id ASC;
        """,
        (run_id,),
    )
    rows = cursor.fetchall()
    return tuple(
        TrackRow(
            run_id=str(row[0]),
            track_id=int(row[1]),
            artist_id=int(row[2]) if row[2] is not None else None,
            genre=str(row[3]),
            subset=str(row[4]),
            source_audio_uri=str(row[5]),
            validation_status=str(row[6]),
            duration_s=float(row[7]),
            manifest_uri=str(row[8]) if row[8] is not None else None,
            checksum=str(row[9]) if row[9] is not None else None,
            segments_persisted=int(row[10]),
            silent_segments=int(row[11]),
            silent_ratio=_float_or_none(row[12]),
            avg_rms=_float_or_none(row[13]),
            avg_processing_ms=_float_or_none(row[14]),
            track_state=str(row[15]),
        )
        for row in rows
    )


def _query_features(cursor: object, *, run_id: str) -> tuple[FeatureRow, ...]:
    cursor.execute(
        """
        SELECT
            run_id,
            track_id,
            segment_idx,
            artifact_uri,
            checksum,
            manifest_uri,
            rms,
            silent_flag,
            mel_bins,
            mel_frames,
            processing_ms
        FROM audio_features
        WHERE run_id = %s
        ORDER BY track_id ASC, segment_idx ASC;
        """,
        (run_id,),
    )
    rows = cursor.fetchall()
    return tuple(
        FeatureRow(
            run_id=str(row[0]),
            track_id=int(row[1]),
            segment_idx=int(row[2]),
            artifact_uri=str(row[3]),
            checksum=str(row[4]),
            manifest_uri=str(row[5]) if row[5] is not None else None,
            rms=float(row[6]),
            silent_flag=bool(row[7]),
            mel_bins=int(row[8]),
            mel_frames=int(row[9]),
            processing_ms=float(row[10]),
        )
        for row in rows
    )


def load_source_snapshot(
    *,
    database: DatabaseSettings,
    run_id: str,
) -> SourceSnapshot:
    """Load the existing TimescaleDB truth needed by the dataset exporter."""

    validated_run_id = validate_run_id(run_id)
    with open_database_connection(database) as connection:
        with connection.cursor() as cursor:
            run_summary = _query_run_summary(cursor, run_id=validated_run_id)
            if run_summary is None:
                raise ValueError(f"Run not found in vw_dashboard_run_summary: {validated_run_id}.")
            tracks = _query_tracks(cursor, run_id=validated_run_id)
            features = _query_features(cursor, run_id=validated_run_id)

    return SourceSnapshot(
        run_id=validated_run_id,
        run_summary=run_summary,
        tracks=tracks,
        features=features,
    )


def export_dataset_bundle(
    *,
    database: DatabaseSettings,
    artifacts_root: Path,
    datasets_root: Path,
    run_id: str,
) -> DatasetExportResult:
    """Load persisted truth and write the run-scoped dataset bundle."""

    snapshot = load_source_snapshot(database=database, run_id=run_id)
    return build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=artifacts_root,
        datasets_root=datasets_root,
    )
