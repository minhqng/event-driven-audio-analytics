from __future__ import annotations

from io import BytesIO
from pathlib import Path

import polars as pl
import pytest

from event_driven_audio_analytics.shared.storage import (
    S3ClaimCheckStore,
    StorageBackendSettings,
    build_claim_check_store,
    build_claim_check_store_for_uri,
    parse_artifact_uri,
    validate_manifest_artifact_uri,
    validate_segment_artifact_uri,
)


class FakeS3Error(Exception):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}
        super().__init__(code)


class FakeS3Client:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}

    def head_bucket(self, *, Bucket: str) -> None:
        if Bucket not in self.buckets:
            raise FakeS3Error("404")

    def create_bucket(self, *, Bucket: str) -> None:
        self.buckets.add(Bucket)

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.buckets.add(Bucket)
        self.objects[(Bucket, Key)] = bytes(Body)

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        try:
            payload = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise FakeS3Error("NoSuchKey") from exc
        return {"Body": BytesIO(payload)}

    def head_object(self, *, Bucket: str, Key: str) -> None:
        if (Bucket, Key) not in self.objects:
            raise FakeS3Error("404")

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)


def test_uri_policy_accepts_run_scoped_local_and_s3_uris() -> None:
    local = validate_segment_artifact_uri(
        "/artifacts/runs/demo-run/segments/2/0.wav",
        run_id="demo-run",
        track_id=2,
        segment_idx=0,
    )
    s3 = validate_manifest_artifact_uri(
        "s3://fma-small-artifacts/runs/demo-run/manifests/segments.parquet",
        run_id="demo-run",
        bucket="fma-small-artifacts",
    )

    assert local.scheme == "local"
    assert local.key == "runs/demo-run/segments/2/0.wav"
    assert s3.scheme == "s3"
    assert s3.key == "runs/demo-run/manifests/segments.parquet"


@pytest.mark.parametrize(
    "uri",
    [
        "file:///tmp/outside.wav",
        "/tmp/outside.wav",
        "relative/path.wav",
        "gs://bucket/runs/demo-run/segments/2/0.wav",
        "/artifacts/runs/../segments/2/0.wav",
        "s3://other-bucket/runs/demo-run/segments/2/0.wav",
    ],
)
def test_uri_policy_rejects_unsupported_or_unsafe_uris(uri: str) -> None:
    with pytest.raises(ValueError):
        parse_artifact_uri(uri, bucket="fma-small-artifacts")


def test_s3_store_round_trips_bytes_and_parquet_manifest() -> None:
    client = FakeS3Client()
    settings = StorageBackendSettings(
        backend="minio",
        bucket="fma-small-artifacts",
        create_bucket=True,
    )
    store = S3ClaimCheckStore(settings, client=client)
    store.ensure_bucket()

    segment_uri = store.segment_uri("demo-run", 2, 0)
    checksum = store.write_bytes(segment_uri, b"payload", content_type="audio/wav")
    manifest_uri = store.manifest_uri("demo-run")
    frame = pl.DataFrame(
        [
            {
                "run_id": "demo-run",
                "track_id": 2,
                "segment_idx": 0,
                "artifact_uri": segment_uri,
                "checksum": checksum,
                "manifest_uri": manifest_uri,
                "sample_rate": 32000,
                "duration_s": 3.0,
                "is_last_segment": True,
            }
        ]
    )

    store.write_parquet(manifest_uri, frame)

    assert store.exists(segment_uri)
    assert store.read_bytes(segment_uri) == b"payload"
    assert store.checksum(segment_uri) == checksum
    assert store.read_parquet(manifest_uri).to_dicts() == frame.to_dicts()
    assert store.local_path(segment_uri) is None


def test_local_store_preserves_existing_logical_uri_layout(tmp_path: Path) -> None:
    store = build_claim_check_store(
        StorageBackendSettings(backend="local", artifacts_root=tmp_path)
    )
    uri = store.segment_uri("demo-run", 2, 0)

    checksum = store.write_bytes(uri, b"payload", content_type="audio/wav")

    assert uri == "/artifacts/runs/demo-run/segments/2/0.wav"
    assert store.exists(uri)
    assert store.checksum(uri) == checksum
    assert store.local_path(uri) == tmp_path / "runs" / "demo-run" / "segments" / "2" / "0.wav"


def test_backend_stores_reject_foreign_uri_families(tmp_path: Path) -> None:
    local_store = build_claim_check_store(
        StorageBackendSettings(backend="local", artifacts_root=tmp_path)
    )
    s3_store = S3ClaimCheckStore(
        StorageBackendSettings(backend="minio", bucket="fma-small-artifacts"),
        client=FakeS3Client(),
    )

    with pytest.raises(ValueError):
        local_store.local_path("s3://fma-small-artifacts/runs/demo-run/segments/2/0.wav")
    with pytest.raises(ValueError):
        s3_store.exists("/artifacts/runs/demo-run/segments/2/0.wav")


def test_store_factory_selects_backend_from_persisted_uri(tmp_path: Path) -> None:
    settings = StorageBackendSettings(
        backend="minio",
        artifacts_root=tmp_path,
        bucket="fma-small-artifacts",
    )

    local_store = build_claim_check_store_for_uri(
        settings,
        "/artifacts/runs/demo-run/segments/2/0.wav",
    )
    s3_store = build_claim_check_store_for_uri(
        settings,
        "s3://fma-small-artifacts/runs/demo-run/segments/2/0.wav",
        s3_client=FakeS3Client(),
    )

    assert local_store.settings.normalized_backend() == "local"
    assert s3_store.settings.normalized_backend() == "minio"
