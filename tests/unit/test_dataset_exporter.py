from __future__ import annotations

import csv
import json
from pathlib import Path

import polars as pl
import pytest

from event_driven_audio_analytics.dataset_exporter import app as dataset_exporter_app
from event_driven_audio_analytics.dataset_exporter import exporter as exporter_module
from event_driven_audio_analytics.dataset_exporter.config import DatasetExporterSettings
from event_driven_audio_analytics.dataset_exporter.exporter import (
    DatasetExportResult,
    FeatureRow,
    RunSummaryRow,
    SourceSnapshot,
    TrackRow,
    build_dataset_bundle,
    load_source_snapshot,
)
from event_driven_audio_analytics.shared.checksum import sha256_file
from event_driven_audio_analytics.shared.settings import DatabaseSettings
from event_driven_audio_analytics.shared.storage import manifest_uri, resolve_artifact_uri, segment_artifact_uri


EXPECTED_BUNDLE_FILES = {
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
    "splits/split-manifest.json",
    "splits/train.parquet",
    "splits/validation.parquet",
    "splits/test.parquet",
    "stats/normalization-stats.json",
}
_DEFAULT_ARTIST_ID = object()


class FakeCursor:
    def __init__(
        self,
        *,
        fetchone_results: list[object] | None = None,
        fetchall_results: list[list[tuple[object, ...]]] | None = None,
    ) -> None:
        self.fetchone_results = list(fetchone_results or [])
        self.fetchall_results = list(fetchall_results or [])
        self.executed: list[tuple[str, object]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> object:
        if not self.fetchone_results:
            return None
        return self.fetchone_results.pop(0)

    def fetchall(self) -> list[tuple[object, ...]]:
        if not self.fetchall_results:
            return []
        return self.fetchall_results.pop(0)


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self._cursor


def _run_summary(
    *,
    run_id: str,
    tracks_total: float = 1.0,
    segments_total: float = 1.0,
    validation_failures: float = 0.0,
    segments_persisted: int = 1,
    silent_ratio: float = 0.0,
) -> RunSummaryRow:
    return RunSummaryRow(
        run_id=run_id,
        first_seen_at="2026-04-29T01:00:00Z",
        last_seen_at="2026-04-29T01:05:00Z",
        tracks_total=tracks_total,
        segments_total=segments_total,
        validation_failures=validation_failures,
        artifact_write_ms=3.5,
        segments_persisted=segments_persisted,
        avg_rms=-10.0 if segments_persisted else None,
        avg_processing_ms=4.2 if segments_persisted else None,
        silent_ratio=silent_ratio,
        processing_error_count=0,
        writer_error_count=0,
        total_error_events=validation_failures,
        error_rate=0.0 if tracks_total == 0 else validation_failures / tracks_total,
    )


def _track(
    *,
    run_id: str,
    track_id: int,
    artist_id: object = _DEFAULT_ARTIST_ID,
    genre: str = "Hip-Hop",
    validation_status: str = "validated",
    segments_persisted: int = 1,
    has_manifest_uri: bool | None = None,
) -> TrackRow:
    include_manifest_uri = segments_persisted > 0 if has_manifest_uri is None else has_manifest_uri
    resolved_artist_id = track_id + 100 if artist_id is _DEFAULT_ARTIST_ID else artist_id
    return TrackRow(
        run_id=run_id,
        track_id=track_id,
        artist_id=resolved_artist_id,
        genre=genre,
        subset="small",
        source_audio_uri=f"/app/data/local/fma_small/{track_id:06d}.mp3",
        validation_status=validation_status,
        duration_s=29.95,
        manifest_uri=(
            f"/artifacts/runs/{run_id}/manifests/segments.parquet"
            if include_manifest_uri
            else None
        ),
        checksum=f"sha256:track-{track_id}",
        segments_persisted=segments_persisted,
        silent_segments=0,
        silent_ratio=0.0 if segments_persisted > 0 else None,
        avg_rms=-10.0 if segments_persisted > 0 else None,
        avg_processing_ms=4.2 if segments_persisted > 0 else None,
        track_state="persisted" if segments_persisted > 0 else "metadata_only",
    )


def _write_segment_artifact(
    artifacts_root: Path,
    *,
    run_id: str,
    track_id: int,
    segment_idx: int,
    payload: bytes = b"RIFF-dataset-exporter-test",
) -> tuple[str, str]:
    artifact_uri = segment_artifact_uri(artifacts_root, run_id, track_id, segment_idx)
    artifact_path = resolve_artifact_uri(artifacts_root, artifact_uri)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(payload)
    return artifact_uri, sha256_file(artifact_path)


def _feature(
    *,
    run_id: str,
    track_id: int,
    segment_idx: int,
    artifact_uri: str,
    checksum: str,
    rms: float = -9.5,
    silent_flag: bool = False,
    processing_ms: float = 5.0,
    manifest_uri_override: str | None = None,
    include_manifest_uri: bool = True,
) -> FeatureRow:
    return FeatureRow(
        run_id=run_id,
        track_id=track_id,
        segment_idx=segment_idx,
        artifact_uri=artifact_uri,
        checksum=checksum,
        manifest_uri=(
            manifest_uri_override
            if manifest_uri_override is not None
            else f"/artifacts/runs/{run_id}/manifests/segments.parquet"
            if include_manifest_uri
            else None
        ),
        rms=rms,
        silent_flag=silent_flag,
        mel_bins=128,
        mel_frames=300,
        processing_ms=processing_ms,
    )


def _write_manifest(
    artifacts_root: Path,
    *,
    run_id: str,
    rows: list[dict[str, object]],
) -> None:
    manifest_path = resolve_artifact_uri(artifacts_root, manifest_uri(artifacts_root, run_id))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(manifest_path)


def _manifest_row(
    *,
    run_id: str,
    track_id: int,
    segment_idx: int,
    artifact_uri: str,
    checksum: str,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "track_id": track_id,
        "segment_idx": segment_idx,
        "artifact_uri": artifact_uri,
        "checksum": checksum,
        "manifest_uri": f"/artifacts/runs/{run_id}/manifests/segments.parquet",
        "sample_rate": 32000,
        "duration_s": 3.0,
        "is_last_segment": True,
    }


def _snapshot_with_valid_tracks(
    artifacts_root: Path,
    *,
    run_id: str,
    track_specs: list[dict[str, object]],
) -> SourceSnapshot:
    tracks: list[TrackRow] = []
    features: list[FeatureRow] = []
    manifest_rows: list[dict[str, object]] = []
    for spec in track_specs:
        track_id = int(spec["track_id"])
        raw_artist_id = spec["artist_id"] if "artist_id" in spec else track_id + 100
        artist_id = None if raw_artist_id is None else int(raw_artist_id)
        segment_count = int(spec.get("segment_count", 1))
        genre = str(spec.get("genre", "Hip-Hop"))
        tracks.append(
            _track(
                run_id=run_id,
                track_id=track_id,
                artist_id=artist_id,
                genre=genre,
                segments_persisted=segment_count,
            )
        )
        for segment_idx in range(segment_count):
            artifact_uri, checksum = _write_segment_artifact(
                artifacts_root,
                run_id=run_id,
                track_id=track_id,
                segment_idx=segment_idx,
                payload=f"{track_id}-{segment_idx}".encode("utf-8"),
            )
            manifest_rows.append(
                _manifest_row(
                    run_id=run_id,
                    track_id=track_id,
                    segment_idx=segment_idx,
                    artifact_uri=artifact_uri,
                    checksum=checksum,
                )
            )
            features.append(
                _feature(
                    run_id=run_id,
                    track_id=track_id,
                    segment_idx=segment_idx,
                    artifact_uri=artifact_uri,
                    checksum=checksum,
                    rms=float(spec.get("rms", -9.5)),
                    silent_flag=bool(spec.get("silent_flag", False)),
                    processing_ms=float(spec.get("processing_ms", 5.0)),
                )
            )
    _write_manifest(artifacts_root, run_id=run_id, rows=manifest_rows)
    return SourceSnapshot(
        run_id=run_id,
        run_summary=_run_summary(
            run_id=run_id,
            tracks_total=float(len(tracks)),
            segments_total=float(len(features)),
            segments_persisted=len(features),
        ),
        tracks=tuple(tracks),
        features=tuple(features),
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bundle_file_paths(output_dir: Path) -> set[str]:
    return {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
    }


def _assert_required_bundle_files(output_dir: Path) -> None:
    assert _bundle_file_paths(output_dir) == EXPECTED_BUNDLE_FILES


def test_exporter_classifies_accepted_and_metadata_only_rejected_tracks(tmp_path: Path) -> None:
    run_id = "demo-run"
    artifact_uri, checksum = _write_segment_artifact(
        tmp_path,
        run_id=run_id,
        track_id=2,
        segment_idx=0,
    )
    _write_manifest(
        tmp_path,
        run_id=run_id,
        rows=[
            _manifest_row(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            )
        ],
    )
    snapshot = SourceSnapshot(
        run_id=run_id,
        run_summary=_run_summary(
            run_id=run_id,
            tracks_total=2.0,
            validation_failures=1.0,
        ),
        tracks=(
            _track(run_id=run_id, track_id=2),
            _track(
                run_id=run_id,
                track_id=666,
                validation_status="silent",
                segments_persisted=0,
            ),
        ),
        features=(
            _feature(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            ),
        ),
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    assert result.quality_verdict == "pass_with_warnings"
    assert result.accepted_tracks == 1
    assert result.rejected_tracks == 1
    _assert_required_bundle_files(result.output_dir)
    accepted_tracks = _read_csv(result.output_dir / "accepted-tracks.csv")
    rejected_tracks = _read_csv(result.output_dir / "rejected-tracks.csv")
    accepted_segments = _read_csv(result.output_dir / "accepted-segments.csv")
    assert accepted_tracks[0]["track_id"] == "2"
    assert accepted_tracks[0]["label_id"] == "0"
    assert rejected_tracks[0]["track_id"] == "666"
    assert rejected_tracks[0]["rejection_reason"] == "validation_status=silent"
    assert accepted_segments[0]["artifact_uri"] == artifact_uri


def test_exporter_output_is_deterministic_for_same_snapshot(tmp_path: Path) -> None:
    run_id = "demo-run"
    artifact_uri, checksum = _write_segment_artifact(
        tmp_path,
        run_id=run_id,
        track_id=2,
        segment_idx=0,
    )
    _write_manifest(
        tmp_path,
        run_id=run_id,
        rows=[
            _manifest_row(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            )
        ],
    )
    snapshot = SourceSnapshot(
        run_id=run_id,
        run_summary=_run_summary(run_id=run_id),
        tracks=(_track(run_id=run_id, track_id=2),),
        features=(
            _feature(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            ),
        ),
    )

    first_result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "first",
    )
    second_result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "second",
    )

    _assert_required_bundle_files(first_result.output_dir)
    _assert_required_bundle_files(second_result.output_dir)
    for relative_path in sorted(EXPECTED_BUNDLE_FILES):
        assert (first_result.output_dir / relative_path).read_bytes() == (
            second_result.output_dir / relative_path
        ).read_bytes()
    manifest_paths = {
        item["path"]
        for item in _read_json(first_result.output_dir / "dataset-build-manifest.json")["files"]
    }
    assert "stats/normalization-stats.json" in manifest_paths
    assert "splits/normalization-stats.json" not in manifest_paths
    assert not (first_result.output_dir / "splits" / "normalization-stats.json").exists()


def test_exporter_replaces_existing_output_bundle(tmp_path: Path) -> None:
    run_id = "demo-run"
    artifact_uri, checksum = _write_segment_artifact(
        tmp_path,
        run_id=run_id,
        track_id=2,
        segment_idx=0,
    )
    _write_manifest(
        tmp_path,
        run_id=run_id,
        rows=[
            _manifest_row(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            )
        ],
    )
    snapshot = SourceSnapshot(
        run_id=run_id,
        run_summary=_run_summary(run_id=run_id),
        tracks=(_track(run_id=run_id, track_id=2),),
        features=(
            _feature(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            ),
        ),
    )
    datasets_root = tmp_path / "datasets"

    first_result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=datasets_root,
    )
    accepted_tracks_path = first_result.output_dir / "accepted-tracks.csv"
    accepted_tracks_path.write_text("stale-owned-output\n", encoding="utf-8")
    (first_result.output_dir / "stale.txt").write_text("stale-unowned-output", encoding="utf-8")
    stale_dir = first_result.output_dir / "splits"
    (stale_dir / "train.parquet").write_text("stale", encoding="utf-8")

    second_result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=datasets_root,
    )

    _assert_required_bundle_files(second_result.output_dir)
    assert (second_result.output_dir / "accepted-tracks.csv").read_text(encoding="utf-8") != (
        "stale-owned-output\n"
    )
    assert not (second_result.output_dir / "stale.txt").exists()
    assert pl.read_parquet(stale_dir / "train.parquet").height == 1


def test_exporter_rejects_missing_artifact_reference(tmp_path: Path) -> None:
    run_id = "demo-run"
    artifact_uri = segment_artifact_uri(tmp_path, run_id, 2, 0)
    checksum = "sha256:missing"
    _write_manifest(
        tmp_path,
        run_id=run_id,
        rows=[
            _manifest_row(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            )
        ],
    )
    snapshot = SourceSnapshot(
        run_id=run_id,
        run_summary=_run_summary(run_id=run_id),
        tracks=(_track(run_id=run_id, track_id=2),),
        features=(
            _feature(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            ),
        ),
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    assert result.quality_verdict == "fail"
    assert result.accepted_segments == 0
    rejected_segments = _read_csv(result.output_dir / "rejected-segments.csv")
    rejected_tracks = _read_csv(result.output_dir / "rejected-tracks.csv")
    quality = _read_json(result.output_dir / "quality-verdict.json")
    assert rejected_segments[0]["reason"] == "artifact_missing"
    assert rejected_tracks[0]["rejection_reason"] == "validated_without_accepted_segments"
    assert "artifact_missing" in quality["reasons"]


def test_exporter_excludes_rejected_tracks_and_segments_from_training_splits(
    tmp_path: Path,
) -> None:
    run_id = "demo-run"
    valid_uri, valid_checksum = _write_segment_artifact(
        tmp_path,
        run_id=run_id,
        track_id=2,
        segment_idx=0,
    )
    rejected_uri = segment_artifact_uri(tmp_path, run_id, 3, 0)
    rejected_checksum = "sha256:missing"
    _write_manifest(
        tmp_path,
        run_id=run_id,
        rows=[
            _manifest_row(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=valid_uri,
                checksum=valid_checksum,
            ),
            _manifest_row(
                run_id=run_id,
                track_id=3,
                segment_idx=0,
                artifact_uri=rejected_uri,
                checksum=rejected_checksum,
            ),
        ],
    )
    snapshot = SourceSnapshot(
        run_id=run_id,
        run_summary=_run_summary(run_id=run_id, tracks_total=2.0, segments_total=2.0),
        tracks=(
            _track(run_id=run_id, track_id=2),
            _track(run_id=run_id, track_id=3),
        ),
        features=(
            _feature(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=valid_uri,
                checksum=valid_checksum,
            ),
            _feature(
                run_id=run_id,
                track_id=3,
                segment_idx=0,
                artifact_uri=rejected_uri,
                checksum=rejected_checksum,
            ),
        ),
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    split_rows = []
    for split_name in ("train", "validation", "test"):
        split_rows.extend(
            pl.read_parquet(result.output_dir / "splits" / f"{split_name}.parquet").to_dicts()
        )
    rejected_segments = _read_csv(result.output_dir / "rejected-segments.csv")
    rejected_tracks = _read_csv(result.output_dir / "rejected-tracks.csv")
    assert result.accepted_tracks == 1
    assert result.accepted_segments == 1
    assert rejected_tracks[0]["track_id"] == "3"
    assert rejected_segments[0]["track_id"] == "3"
    assert {int(row["track_id"]) for row in split_rows} == {2}
    assert {int(row["segment_idx"]) for row in split_rows} == {0}


def test_exporter_marks_metadata_only_validation_failure_bundle_as_fail(
    tmp_path: Path,
) -> None:
    run_id = "demo-validation-failure"
    snapshot = SourceSnapshot(
        run_id=run_id,
        run_summary=_run_summary(
            run_id=run_id,
            tracks_total=1.0,
            segments_total=0.0,
            validation_failures=1.0,
            segments_persisted=0,
        ),
        tracks=(
            _track(
                run_id=run_id,
                track_id=910003,
                validation_status="silent",
                segments_persisted=0,
            ),
        ),
        features=(),
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    quality = _read_json(result.output_dir / "quality-verdict.json")
    stats = _read_json(result.output_dir / "stats" / "normalization-stats.json")
    assert result.quality_verdict == "fail"
    assert result.accepted_tracks == 0
    assert result.accepted_segments == 0
    assert "no_accepted_dataset_tracks" in quality["reasons"]
    assert "track_validation_failures" in quality["reasons"]
    assert pl.read_parquet(result.output_dir / "splits" / "train.parquet").height == 0
    assert stats["status"] == "not_available"


def test_exporter_quality_verdict_keeps_warning_reasons_when_blocking(tmp_path: Path) -> None:
    run_id = "demo-run"
    artifact_uri = segment_artifact_uri(tmp_path, run_id, 2, 0)
    checksum = "sha256:missing"
    _write_manifest(
        tmp_path,
        run_id=run_id,
        rows=[
            _manifest_row(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            )
        ],
    )
    snapshot = SourceSnapshot(
        run_id=run_id,
        run_summary=_run_summary(run_id=run_id, validation_failures=1.0),
        tracks=(_track(run_id=run_id, track_id=2),),
        features=(
            _feature(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            ),
        ),
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    quality = _read_json(result.output_dir / "quality-verdict.json")
    assert result.quality_verdict == "fail"
    assert quality["warning_anomaly_count"] == 1
    assert "artifact_missing" in quality["reasons"]
    assert "track_validation_failures" in quality["reasons"]


def test_exporter_uses_manifest_row_uri_for_accepted_segments(tmp_path: Path) -> None:
    run_id = "demo-run"
    artifact_uri, checksum = _write_segment_artifact(
        tmp_path,
        run_id=run_id,
        track_id=2,
        segment_idx=0,
    )
    _write_manifest(
        tmp_path,
        run_id=run_id,
        rows=[
            _manifest_row(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            )
        ],
    )
    snapshot = SourceSnapshot(
        run_id=run_id,
        run_summary=_run_summary(run_id=run_id),
        tracks=(_track(run_id=run_id, track_id=2),),
        features=(
            _feature(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
                include_manifest_uri=False,
            ),
        ),
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    accepted_segments = _read_csv(result.output_dir / "accepted-segments.csv")
    assert accepted_segments[0]["manifest_uri"] == (
        f"/artifacts/runs/{run_id}/manifests/segments.parquet"
    )


def test_exporter_rejects_manifest_uri_mismatch(tmp_path: Path) -> None:
    run_id = "demo-run"
    artifact_uri, checksum = _write_segment_artifact(
        tmp_path,
        run_id=run_id,
        track_id=2,
        segment_idx=0,
    )
    _write_manifest(
        tmp_path,
        run_id=run_id,
        rows=[
            _manifest_row(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            )
        ],
    )
    snapshot = SourceSnapshot(
        run_id=run_id,
        run_summary=_run_summary(run_id=run_id),
        tracks=(_track(run_id=run_id, track_id=2),),
        features=(
            _feature(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
                manifest_uri_override=f"/artifacts/runs/{run_id}/manifests/wrong.parquet",
            ),
        ),
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    rejected_segments = _read_csv(result.output_dir / "rejected-segments.csv")
    anomaly_summary = _read_json(result.output_dir / "anomaly-summary.json")
    assert result.quality_verdict == "fail"
    assert "manifest_uri_mismatch" in rejected_segments[0]["reason"]
    assert any(item["type"] == "manifest_uri_mismatch" for item in anomaly_summary["items"])


def test_exporter_generates_stable_sorted_label_map(tmp_path: Path) -> None:
    run_id = "demo-run"
    first_uri, first_checksum = _write_segment_artifact(
        tmp_path,
        run_id=run_id,
        track_id=20,
        segment_idx=0,
        payload=b"rock",
    )
    second_uri, second_checksum = _write_segment_artifact(
        tmp_path,
        run_id=run_id,
        track_id=10,
        segment_idx=0,
        payload=b"ambient",
    )
    _write_manifest(
        tmp_path,
        run_id=run_id,
        rows=[
            _manifest_row(
                run_id=run_id,
                track_id=20,
                segment_idx=0,
                artifact_uri=first_uri,
                checksum=first_checksum,
            ),
            _manifest_row(
                run_id=run_id,
                track_id=10,
                segment_idx=0,
                artifact_uri=second_uri,
                checksum=second_checksum,
            ),
        ],
    )
    snapshot = SourceSnapshot(
        run_id=run_id,
        run_summary=_run_summary(run_id=run_id, tracks_total=2.0, segments_total=2.0),
        tracks=(
            _track(run_id=run_id, track_id=20, genre="Rock"),
            _track(run_id=run_id, track_id=10, genre="Ambient"),
        ),
        features=(
            _feature(
                run_id=run_id,
                track_id=20,
                segment_idx=0,
                artifact_uri=first_uri,
                checksum=first_checksum,
            ),
            _feature(
                run_id=run_id,
                track_id=10,
                segment_idx=0,
                artifact_uri=second_uri,
                checksum=second_checksum,
            ),
        ),
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    label_map = _read_json(result.output_dir / "label-map.json")
    accepted_segments = _read_csv(result.output_dir / "accepted-segments.csv")
    assert label_map["labels"] == [
        {"genre": "Ambient", "label_id": 0, "segment_count": 1, "track_count": 1},
        {"genre": "Rock", "label_id": 1, "segment_count": 1, "track_count": 1},
    ]
    assert [(row["track_id"], row["label_id"]) for row in accepted_segments] == [
        ("10", "0"),
        ("20", "1"),
    ]


def test_exporter_writes_artist_aware_training_splits_without_artist_leakage(
    tmp_path: Path,
) -> None:
    run_id = "demo-run"
    snapshot = _snapshot_with_valid_tracks(
        tmp_path,
        run_id=run_id,
        track_specs=[
            {"track_id": 10, "artist_id": 900, "genre": "Hip-Hop", "segment_count": 2},
            {"track_id": 11, "artist_id": 900, "genre": "Hip-Hop", "segment_count": 1},
            {"track_id": 20, "artist_id": 901, "genre": "Rock"},
            {"track_id": 30, "artist_id": 902, "genre": "Ambient"},
            {"track_id": 40, "artist_id": 903, "genre": "Folk"},
        ],
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    split_manifest = _read_json(result.output_dir / "splits" / "split-manifest.json")
    assert split_manifest["split_type"] == "artist_aware_track_level"
    assert split_manifest["artist_leakage_risk"] is False
    assert split_manifest["tensor_export"]["status"] == "not_available"
    assert set(pl.read_parquet(result.output_dir / "splits" / "train.parquet").columns) == set(
        exporter_module.TRAINING_SPLIT_FIELDS
    )

    split_artists: dict[str, set[int]] = {}
    split_by_track: dict[int, str] = {}
    segment_total = 0
    for split_name in ("train", "validation", "test"):
        rows = pl.read_parquet(result.output_dir / "splits" / f"{split_name}.parquet").to_dicts()
        segment_total += len(rows)
        split_artists[split_name] = {
            int(row["artist_id"])
            for row in rows
            if row["artist_id"] is not None
        }
        for row in rows:
            split_by_track[int(row["track_id"])] = split_name

    assert segment_total == result.accepted_segments
    assert split_by_track[10] == split_by_track[11]
    assert split_artists["train"].isdisjoint(split_artists["validation"])
    assert split_artists["train"].isdisjoint(split_artists["test"])
    assert split_artists["validation"].isdisjoint(split_artists["test"])


def test_exporter_falls_back_to_track_level_splits_when_artist_id_is_missing(
    tmp_path: Path,
) -> None:
    run_id = "demo-run"
    snapshot = _snapshot_with_valid_tracks(
        tmp_path,
        run_id=run_id,
        track_specs=[
            {"track_id": 10, "artist_id": None, "genre": "Hip-Hop"},
            {"track_id": 20, "artist_id": 901, "genre": "Rock"},
            {"track_id": 30, "artist_id": None, "genre": "Ambient"},
            {"track_id": 40, "artist_id": 903, "genre": "Folk"},
        ],
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    split_manifest = _read_json(result.output_dir / "splits" / "split-manifest.json")
    split_rows = [
        row
        for split_name in ("train", "validation", "test")
        for row in pl.read_parquet(result.output_dir / "splits" / f"{split_name}.parquet").to_dicts()
    ]

    assert split_manifest["split_type"] == "track_level_fallback"
    assert split_manifest["artist_leakage_risk"] is True
    assert split_manifest["degradation_reason"] == (
        "artist_id is unavailable for at least one accepted track"
    )
    assert {int(row["track_id"]) for row in split_rows} == {10, 20, 30, 40}
    assert any(row["artist_id"] is None for row in split_rows)


def test_exporter_normalization_stats_use_train_split_only(tmp_path: Path) -> None:
    run_id = "demo-run"
    snapshot = _snapshot_with_valid_tracks(
        tmp_path,
        run_id=run_id,
        track_specs=[
            {"track_id": 10, "artist_id": 900, "rms": -1.0, "processing_ms": 1.0},
            {"track_id": 20, "artist_id": 901, "rms": -10.0, "processing_ms": 2.0},
            {"track_id": 30, "artist_id": 902, "rms": -100.0, "processing_ms": 3.0},
            {"track_id": 40, "artist_id": 903, "rms": -1000.0, "processing_ms": 4.0},
        ],
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    train_rows = pl.read_parquet(result.output_dir / "splits" / "train.parquet").to_dicts()
    stats = _read_json(result.output_dir / "stats" / "normalization-stats.json")
    expected_mean = sum(float(row["rms"]) for row in train_rows) / len(train_rows)
    expected_processing_mean = (
        sum(float(row["processing_ms"]) for row in train_rows) / len(train_rows)
    )
    assert stats["source_file"] == "splits/train.parquet"
    assert stats["row_count"] == len(train_rows)
    assert stats["features"]["rms"]["mean"] == pytest.approx(expected_mean)
    assert stats["features"]["processing_ms"]["mean"] == pytest.approx(
        expected_processing_mean
    )
    assert stats["tensor_stats"]["status"] == "not_available"


def test_exporter_degrades_tiny_artist_split_without_segment_level_leakage(
    tmp_path: Path,
) -> None:
    run_id = "demo-run"
    snapshot = _snapshot_with_valid_tracks(
        tmp_path,
        run_id=run_id,
        track_specs=[
            {"track_id": 10, "artist_id": 900, "segment_count": 2},
        ],
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    split_manifest = _read_json(result.output_dir / "splits" / "split-manifest.json")
    assert split_manifest["split_type"] == "artist_aware_degraded"
    assert split_manifest["degradation_reason"]
    assert pl.read_parquet(result.output_dir / "splits" / "train.parquet").height == 2
    assert pl.read_parquet(result.output_dir / "splits" / "validation.parquet").height == 0
    assert pl.read_parquet(result.output_dir / "splits" / "test.parquet").height == 0


def test_exporter_writes_empty_training_outputs_when_no_segments_are_accepted(
    tmp_path: Path,
) -> None:
    run_id = "demo-run"
    artifact_uri = segment_artifact_uri(tmp_path, run_id, 2, 0)
    checksum = "sha256:missing"
    _write_manifest(
        tmp_path,
        run_id=run_id,
        rows=[
            _manifest_row(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            )
        ],
    )
    snapshot = SourceSnapshot(
        run_id=run_id,
        run_summary=_run_summary(run_id=run_id),
        tracks=(_track(run_id=run_id, track_id=2),),
        features=(
            _feature(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            ),
        ),
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    split_manifest = _read_json(result.output_dir / "splits" / "split-manifest.json")
    stats = _read_json(result.output_dir / "stats" / "normalization-stats.json")
    assert result.accepted_segments == 0
    assert split_manifest["split_type"] == "none_no_accepted_segments"
    assert stats["status"] == "not_available"
    assert stats["reason"] == "train split has no rows"
    assert pl.read_parquet(result.output_dir / "splits" / "train.parquet").height == 0
    assert pl.read_parquet(result.output_dir / "splits" / "validation.parquet").height == 0
    assert pl.read_parquet(result.output_dir / "splits" / "test.parquet").height == 0


def test_exporter_exports_manifest_segments_without_features_as_rejected(tmp_path: Path) -> None:
    run_id = "demo-run"
    artifact_uri, checksum = _write_segment_artifact(
        tmp_path,
        run_id=run_id,
        track_id=2,
        segment_idx=0,
    )
    _write_manifest(
        tmp_path,
        run_id=run_id,
        rows=[
            _manifest_row(
                run_id=run_id,
                track_id=2,
                segment_idx=0,
                artifact_uri=artifact_uri,
                checksum=checksum,
            )
        ],
    )
    snapshot = SourceSnapshot(
        run_id=run_id,
        run_summary=_run_summary(run_id=run_id, segments_persisted=0),
        tracks=(_track(run_id=run_id, track_id=2, segments_persisted=0, has_manifest_uri=True),),
        features=(),
    )

    result = build_dataset_bundle(
        snapshot=snapshot,
        artifacts_root=tmp_path,
        datasets_root=tmp_path / "datasets",
    )

    rejected_segments = _read_csv(result.output_dir / "rejected-segments.csv")
    anomaly_summary = _read_json(result.output_dir / "anomaly-summary.json")
    assert result.quality_verdict == "fail"
    assert rejected_segments[0]["reason"] == "missing_audio_features_row"
    assert rejected_segments[0]["source"] == "segment_manifest"
    assert any(
        item["type"] == "manifest_segment_missing_features"
        for item in anomaly_summary["items"]
    )


def test_load_source_snapshot_maps_db_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cursor = FakeCursor(
        fetchone_results=[
            (
                "demo-run",
                "2026-04-29T01:00:00Z",
                "2026-04-29T01:05:00Z",
                1.0,
                1.0,
                0.0,
                3.5,
                1,
                -9.5,
                5.0,
                0.0,
                0,
                0,
                0.0,
                0.0,
            )
        ],
        fetchall_results=[
            [
                (
                    "demo-run",
                    2,
                    102,
                    "Hip-Hop",
                    "small",
                    "/app/data/local/fma_small/000/000002.mp3",
                    "validated",
                    29.95,
                    "/artifacts/runs/demo-run/manifests/segments.parquet",
                    "sha256:track",
                    1,
                    0,
                    0.0,
                    -9.5,
                    5.0,
                    "persisted",
                )
            ],
            [
                (
                    "demo-run",
                    2,
                    0,
                    "/artifacts/runs/demo-run/segments/2/0.wav",
                    "sha256:segment",
                    "/artifacts/runs/demo-run/manifests/segments.parquet",
                    -9.5,
                    False,
                    128,
                    300,
                    5.0,
                )
            ],
        ],
    )
    monkeypatch.setattr(
        exporter_module,
        "open_database_connection",
        lambda _: FakeConnection(cursor),
    )

    snapshot = load_source_snapshot(
        database=DatabaseSettings(
            host="timescaledb",
            port=5432,
            database="audio_analytics",
            user="audio_analytics",
            password="audio_analytics",
        ),
        run_id="demo-run",
    )

    assert snapshot.run_summary.segments_persisted == 1
    assert snapshot.tracks[0].track_id == 2
    assert snapshot.features[0].mel_frames == 300
    assert "vw_dashboard_run_summary" in cursor.executed[0][0]
    assert "vw_review_tracks" in cursor.executed[1][0]
    assert "audio_features" in cursor.executed[2][0]


def test_load_source_snapshot_allows_missing_artist_id_for_fallback_exports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor(
        fetchone_results=[
            (
                "demo-run",
                "2026-04-29T01:00:00Z",
                "2026-04-29T01:05:00Z",
                1.0,
                1.0,
                0.0,
                3.5,
                1,
                -9.5,
                5.0,
                0.0,
                0,
                0,
                0.0,
                0.0,
            )
        ],
        fetchall_results=[
            [
                (
                    "demo-run",
                    2,
                    None,
                    "Hip-Hop",
                    "small",
                    "/app/data/local/fma_small/000/000002.mp3",
                    "validated",
                    29.95,
                    "/artifacts/runs/demo-run/manifests/segments.parquet",
                    "sha256:track",
                    1,
                    0,
                    0.0,
                    -9.5,
                    5.0,
                    "persisted",
                )
            ],
            [
                (
                    "demo-run",
                    2,
                    0,
                    "/artifacts/runs/demo-run/segments/2/0.wav",
                    "sha256:segment",
                    "/artifacts/runs/demo-run/manifests/segments.parquet",
                    -9.5,
                    False,
                    128,
                    300,
                    5.0,
                )
            ],
        ],
    )
    monkeypatch.setattr(
        exporter_module,
        "open_database_connection",
        lambda _: FakeConnection(cursor),
    )

    snapshot = load_source_snapshot(
        database=DatabaseSettings(
            host="timescaledb",
            port=5432,
            database="audio_analytics",
            user="audio_analytics",
            password="audio_analytics",
        ),
        run_id="demo-run",
    )

    assert snapshot.tracks[0].track_id == 2
    assert snapshot.tracks[0].artist_id is None
    assert snapshot.features[0].track_id == 2


def test_cli_export_invokes_exporter_and_prints_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    database = DatabaseSettings(
        host="timescaledb",
        port=5432,
        database="audio_analytics",
        user="audio_analytics",
        password="audio_analytics",
    )
    monkeypatch.setattr(
        dataset_exporter_app.DatasetExporterSettings,
        "from_env",
        lambda: DatasetExporterSettings(
            database=database,
            artifacts_root=tmp_path / "default-artifacts",
            datasets_root=tmp_path / "default-datasets",
        ),
    )

    def fake_export_dataset_bundle(**kwargs: object) -> DatasetExportResult:
        calls.append(kwargs)
        return DatasetExportResult(
            run_id=str(kwargs["run_id"]),
            output_dir=Path(kwargs["datasets_root"]) / str(kwargs["run_id"]),
            file_count=10,
            quality_verdict="pass",
            accepted_tracks=1,
            rejected_tracks=0,
            accepted_segments=1,
            rejected_segments=0,
        )

    monkeypatch.setattr(
        dataset_exporter_app,
        "export_dataset_bundle",
        fake_export_dataset_bundle,
    )

    dataset_exporter_app.main(
        [
            "export",
            "--run-id",
            "demo-run",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--datasets-root",
            str(tmp_path / "datasets"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["output_dir"] == (tmp_path / "datasets" / "demo-run").as_posix()
    assert calls == [
        {
            "database": database,
            "artifacts_root": tmp_path / "artifacts",
            "datasets_root": tmp_path / "datasets",
            "run_id": "demo-run",
        }
    ]
