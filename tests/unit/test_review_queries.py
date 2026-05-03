from __future__ import annotations

import json
from pathlib import Path

import pytest

from event_driven_audio_analytics.review.config import ReviewSettings
from event_driven_audio_analytics.review.queries import (
    get_run_detail,
    get_track_detail,
    list_runs,
    lookup_segment_artifact_ref,
    lookup_segment_artifact_path,
)
from event_driven_audio_analytics.review.schemas import (
    derive_run_state,
    derive_track_state,
    normalize_limit,
    validate_run_id,
)
from event_driven_audio_analytics.shared.settings import BaseServiceSettings, DatabaseSettings
from event_driven_audio_analytics.shared.storage import StorageBackendSettings


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


def build_settings(tmp_path: Path) -> ReviewSettings:
    return ReviewSettings(
        base=BaseServiceSettings(
            service_name="review",
            run_id="demo-run",
            kafka_bootstrap_servers="kafka:29092",
            artifacts_root=tmp_path,
        ),
        database=DatabaseSettings(
            host="timescaledb",
            port=5432,
            database="audio_analytics",
            user="audio_analytics",
            password="audio_analytics",
        ),
        host="0.0.0.0",
        port=8080,
        default_limit=8,
        max_limit=25,
        pinned_run_ids=("demo-high-energy", "demo-silent-oriented"),
    )


def build_minio_settings(tmp_path: Path) -> ReviewSettings:
    return ReviewSettings(
        base=BaseServiceSettings(
            service_name="review",
            run_id="demo-run",
            kafka_bootstrap_servers="kafka:29092",
            artifacts_root=tmp_path,
            storage=StorageBackendSettings(
                backend="minio",
                artifacts_root=tmp_path,
                bucket="fma-small-artifacts",
            ),
        ),
        database=DatabaseSettings(
            host="timescaledb",
            port=5432,
            database="audio_analytics",
            user="audio_analytics",
            password="audio_analytics",
        ),
        host="0.0.0.0",
        port=8080,
        default_limit=8,
        max_limit=25,
        pinned_run_ids=("demo-high-energy", "demo-silent-oriented"),
    )


def test_validate_run_id_rejects_path_escape() -> None:
    with pytest.raises(ValueError, match="single relative path segment"):
        validate_run_id("../escape")


def test_normalize_limit_caps_at_maximum() -> None:
    assert normalize_limit(200, default_limit=8, max_limit=25) == 25


def test_derive_run_state_marks_metadata_only() -> None:
    state = derive_run_state(
        {
            "segments_persisted": 0,
            "validation_failures": 1.0,
            "processing_error_count": 0,
            "writer_error_count": 0,
            "tracks_total": 1.0,
        }
    )

    assert state["value"] == "metadata_only"


def test_derive_track_state_marks_metadata_only() -> None:
    state = derive_track_state(
        {
            "validation_status": "silent",
            "segments_persisted": 0,
        }
    )

    assert state["value"] == "metadata_only"
    assert "validation_status=silent" in state["reason"]


def test_list_runs_uses_demo_mode_query_when_pinned_runs_are_requested(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cursor = FakeCursor(
        fetchall_results=[
            [
                (
                    "demo-high-energy",
                    None,
                    None,
                    1.0,
                    4.0,
                    0.0,
                    14.0,
                    4,
                    -8.4,
                    6.2,
                    0.0,
                    0,
                    0,
                    0.0,
                    0.0,
                    3,
                )
            ]
        ]
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.review.queries.open_database_connection",
        lambda _: FakeConnection(cursor),
    )

    payload = list_runs(build_settings(tmp_path), limit=8, offset=0, demo_mode=True)

    assert payload["total"] == 3
    assert payload["has_more"] is True
    assert payload["items"][0]["run_id"] == "demo-high-energy"
    assert "array_position" in cursor.executed[0][0]


def test_get_run_detail_reads_processing_state_from_fs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    manifest_path = tmp_path / "runs" / "demo-run" / "manifests" / "segments.parquet"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(b"PAR1")
    processing_state_path = tmp_path / "runs" / "demo-run" / "state" / "processing_metrics.json"
    processing_state_path.parent.mkdir(parents=True, exist_ok=True)
    processing_state_path.write_text(
        json.dumps(
            {
                "run_id": "demo-run",
                "segments": [
                    {"track_id": 2, "segment_idx": 0, "silent_flag": False},
                    {"track_id": 2, "segment_idx": 1, "silent_flag": True},
                ],
            }
        ),
        encoding="utf-8",
    )

    cursor = FakeCursor(
        fetchone_results=[
            (
                "demo-run",
                None,
                None,
                1.0,
                2.0,
                0.0,
                11.0,
                2,
                -9.9,
                4.2,
                0.5,
                0,
                0,
                0.0,
                0.0,
            )
        ],
        fetchall_results=[
            [("validated", 1)],
            [("audio.features", 0, 8, None)],
        ],
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.review.queries.open_database_connection",
        lambda _: FakeConnection(cursor),
    )

    payload = get_run_detail(settings, "demo-run")

    assert payload is not None
    assert payload["runtime_proof"]["manifest"]["exists"] is True
    assert payload["runtime_proof"]["processing_state"]["state"]["segment_count"] == 2
    assert payload["runtime_proof"]["processing_state"]["state"]["silent_ratio"] == 0.5


def test_get_run_detail_reports_malformed_processing_state_as_read_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    processing_state_path = tmp_path / "runs" / "demo-run" / "state" / "processing_metrics.json"
    processing_state_path.parent.mkdir(parents=True, exist_ok=True)
    processing_state_path.write_text("[]", encoding="utf-8")

    cursor = FakeCursor(
        fetchone_results=[
            (
                "demo-run",
                None,
                None,
                1.0,
                2.0,
                0.0,
                11.0,
                2,
                -9.9,
                4.2,
                0.5,
                0,
                0,
                0.0,
                0.0,
            )
        ],
        fetchall_results=[
            [("validated", 1)],
            [("audio.features", 0, 8, None)],
        ],
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.review.queries.open_database_connection",
        lambda _: FakeConnection(cursor),
    )

    payload = get_run_detail(settings, "demo-run")

    assert payload is not None
    processing_state = payload["runtime_proof"]["processing_state"]
    assert processing_state["state"] is None
    assert "decode to an object" in processing_state["read_error"]


def test_get_track_detail_marks_artifact_existence_from_persisted_uri(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    artifact_uri = "/artifacts/runs/demo-run/segments/42/0.wav"
    artifact_path = tmp_path / "runs" / "demo-run" / "segments" / "42" / "0.wav"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"RIFF")

    cursor = FakeCursor(
        fetchone_results=[
            (
                "demo-run",
                42,
                9,
                "Synthetic",
                "small",
                "data/source.mp3",
                "validated",
                6.0,
                "/artifacts/runs/demo-run/manifests/segments.parquet",
                "sha256:track",
                1,
                0,
                0.0,
                -7.1,
                3.2,
                "persisted",
            )
        ],
        fetchall_results=[
            [
                (
                    None,
                    0,
                    -7.1,
                    False,
                    3.2,
                    artifact_uri,
                    "sha256:segment",
                    "/artifacts/runs/demo-run/manifests/segments.parquet",
                    1,
                )
            ]
        ],
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.review.queries.open_database_connection",
        lambda _: FakeConnection(cursor),
    )

    payload = get_track_detail(
        settings,
        run_id="demo-run",
        track_id=42,
        segments_limit=8,
        segments_offset=0,
    )

    assert payload is not None
    assert payload["track"]["track_state"]["value"] == "persisted"
    assert payload["segments"]["items"][0]["artifact"]["exists"] is True
    assert payload["segments"]["items"][0]["artifact"]["uri"] == artifact_uri
    assert payload["segments"]["items"][0]["artifact"]["provenance"]["exists"] == "fs"


def test_get_track_detail_uses_uri_family_for_artifact_exists_provenance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = build_minio_settings(tmp_path)
    artifact_path = tmp_path / "runs" / "demo-run" / "review-media" / "segment-0.wav"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"RIFF")

    cursor = FakeCursor(
        fetchone_results=[
            (
                "demo-run",
                42,
                9,
                "Synthetic",
                "small",
                "data/source.mp3",
                "validated",
                6.0,
                "/artifacts/runs/demo-run/manifests/segments.parquet",
                "sha256:track",
                1,
                0,
                0.0,
                -7.1,
                3.2,
                "persisted",
            )
        ],
        fetchall_results=[
            [
                (
                    None,
                    0,
                    -7.1,
                    False,
                    3.2,
                    "/artifacts/runs/demo-run/segments/42/0.wav",
                    "sha256:segment",
                    "/artifacts/runs/demo-run/manifests/segments.parquet",
                    1,
                )
            ]
        ],
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.review.queries.open_database_connection",
        lambda _: FakeConnection(cursor),
    )

    payload = get_track_detail(
        settings,
        run_id="demo-run",
        track_id=42,
        segments_limit=8,
        segments_offset=0,
    )

    assert payload is not None
    assert payload["segments"]["items"][0]["artifact"]["exists"] is False
    assert payload["segments"]["items"][0]["artifact"]["provenance"]["exists"] == "fs"


def test_get_track_detail_rejects_cross_run_artifact_uri(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    artifact_path = tmp_path / "runs" / "other-run" / "segments" / "42" / "0.wav"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"RIFF")

    cursor = FakeCursor(
        fetchone_results=[
            (
                "demo-run",
                42,
                9,
                "Synthetic",
                "small",
                "data/source.mp3",
                "validated",
                6.0,
                "/artifacts/runs/demo-run/manifests/segments.parquet",
                "sha256:track",
                1,
                0,
                0.0,
                -7.1,
                3.2,
                "persisted",
            )
        ],
        fetchall_results=[
            [
                (
                    None,
                    0,
                    -7.1,
                    False,
                    3.2,
                    "/artifacts/runs/other-run/segments/42/0.wav",
                    "sha256:segment",
                    "/artifacts/runs/demo-run/manifests/segments.parquet",
                    1,
                )
            ]
        ],
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.review.queries.open_database_connection",
        lambda _: FakeConnection(cursor),
    )

    payload = get_track_detail(
        settings,
        run_id="demo-run",
        track_id=42,
        segments_limit=8,
        segments_offset=0,
    )

    assert payload is not None
    assert payload["segments"]["items"][0]["artifact"]["exists"] is False


def test_lookup_segment_artifact_ref_rejects_cross_run_media_uri(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    artifact_path = tmp_path / "runs" / "other-run" / "segments" / "42" / "0.wav"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"RIFF")
    cursor = FakeCursor(
        fetchone_results=[("/artifacts/runs/other-run/segments/42/0.wav", "sha256:segment")]
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.review.queries.open_database_connection",
        lambda _: FakeConnection(cursor),
    )

    artifact_ref = lookup_segment_artifact_ref(
        settings,
        run_id="demo-run",
        track_id=42,
        segment_idx=0,
    )

    assert artifact_ref is None


def test_get_run_detail_prefers_persisted_manifest_uri_for_runtime_proof(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = build_minio_settings(tmp_path)
    manifest_path = tmp_path / "runs" / "demo-run" / "manifests" / "segments.parquet"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(b"PAR1")

    cursor = FakeCursor(
        fetchone_results=[
            (
                "demo-run",
                None,
                None,
                1.0,
                2.0,
                0.0,
                11.0,
                2,
                -9.9,
                4.2,
                0.5,
                0,
                0,
                0.0,
                0.0,
            ),
            ("/artifacts/runs/demo-run/manifests/segments.parquet",),
        ],
        fetchall_results=[
            [("validated", 1)],
            [("audio.features", 0, 8, None)],
        ],
    )
    monkeypatch.setattr(
        "event_driven_audio_analytics.review.queries.open_database_connection",
        lambda _: FakeConnection(cursor),
    )

    payload = get_run_detail(settings, "demo-run")

    assert payload is not None
    manifest = payload["runtime_proof"]["manifest"]
    assert manifest["path"] == "/artifacts/runs/demo-run/manifests/segments.parquet"
    assert manifest["exists"] is True
    assert manifest["provenance"]["exists"] == "fs"


def test_lookup_segment_artifact_path_rejects_uri_outside_artifacts_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = build_settings(tmp_path)
    outside_path = tmp_path.parent / "escape.wav"
    outside_path.write_bytes(b"RIFF")
    cursor = FakeCursor(fetchone_results=[(outside_path.as_posix(),)])
    monkeypatch.setattr(
        "event_driven_audio_analytics.review.queries.open_database_connection",
        lambda _: FakeConnection(cursor),
    )

    resolved = lookup_segment_artifact_path(
        settings,
        run_id="demo-run",
        track_id=42,
        segment_idx=0,
    )

    assert resolved is None
