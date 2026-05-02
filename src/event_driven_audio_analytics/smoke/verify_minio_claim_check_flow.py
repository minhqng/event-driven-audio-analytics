"""Verify one MinIO-backed claim-check smoke run end to end."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from event_driven_audio_analytics.shared.db import open_database_connection
from event_driven_audio_analytics.shared.settings import (
    load_database_settings,
    load_storage_backend_settings,
)
from event_driven_audio_analytics.shared.storage import (
    build_claim_check_store_for_uri,
    validate_run_id,
)


DEFAULT_BASE_URL = "http://review:8080"
DEFAULT_DATASETS_ROOT = Path("/app/artifacts/datasets")


@dataclass(frozen=True, slots=True)
class PersistedFeatureArtifact:
    track_id: int
    segment_idx: int
    artifact_uri: str
    checksum: str
    manifest_uri: str


def _read_json(url: str) -> dict[str, object]:
    with urlopen(url) as response:  # noqa: S310 - trusted local Compose service
        return json.loads(response.read().decode("utf-8"))


def _verify_wav_stream(url: str, *, label: str) -> dict[str, object]:
    try:
        with urlopen(url) as response:  # noqa: S310 - trusted local Compose service
            if response.status != 200:
                raise RuntimeError(f"{label} did not stream successfully.")
            content_type = response.headers.get_content_type()
            if content_type not in {"audio/wav", "audio/x-wav"}:
                raise RuntimeError(
                    f"{label} returned unexpected content-type {content_type!r}."
                )
            payload = response.read(32)
            if not payload:
                raise RuntimeError(f"{label} returned an empty body.")
            return {
                "content_type": content_type,
                "preview_size": len(payload),
            }
    except HTTPError as exc:  # pragma: no cover - defensive path
        raise RuntimeError(f"{label} did not stream successfully.") from exc


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _assert_minio_uri(uri: str, *, bucket: str, run_id: str, field_name: str) -> None:
    expected_prefix = f"s3://{bucket}/runs/{run_id}/"
    if not uri.startswith(expected_prefix):
        raise RuntimeError(
            f"{field_name} must stay under the MinIO run namespace "
            f"expected_prefix={expected_prefix!r} actual={uri!r}."
        )


def _query_persisted_feature_artifacts(run_id: str) -> tuple[PersistedFeatureArtifact, ...]:
    database_settings = load_database_settings()
    with open_database_connection(database_settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT ON (track_id, segment_idx)
                    track_id,
                    segment_idx,
                    artifact_uri,
                    checksum,
                    manifest_uri
                FROM audio_features
                WHERE run_id = %s
                ORDER BY track_id ASC, segment_idx ASC, ts DESC;
                """,
                (run_id,),
            )
            rows = cursor.fetchall()

    artifacts = tuple(
        PersistedFeatureArtifact(
            track_id=int(track_id),
            segment_idx=int(segment_idx),
            artifact_uri=str(artifact_uri),
            checksum=str(checksum),
            manifest_uri=str(manifest_uri),
        )
        for track_id, segment_idx, artifact_uri, checksum, manifest_uri in rows
        if manifest_uri is not None
    )
    if not artifacts:
        raise RuntimeError(
            f"Run {run_id!r} did not persist any feature artifacts for MinIO verification."
        )
    return artifacts


def _verify_feature_artifacts(
    *,
    run_id: str,
    bucket: str,
    artifacts_root: Path,
    persisted_features: tuple[PersistedFeatureArtifact, ...],
) -> dict[str, object]:
    storage_settings = load_storage_backend_settings(artifacts_root=artifacts_root)
    manifest_uris = {feature.manifest_uri for feature in persisted_features}
    manifest_rows: dict[str, int] = {}

    for feature in persisted_features:
        _assert_minio_uri(
            feature.artifact_uri,
            bucket=bucket,
            run_id=run_id,
            field_name="audio_features.artifact_uri",
        )
        _assert_minio_uri(
            feature.manifest_uri,
            bucket=bucket,
            run_id=run_id,
            field_name="audio_features.manifest_uri",
        )
        store = build_claim_check_store_for_uri(storage_settings, feature.artifact_uri)
        if not store.exists(feature.artifact_uri):
            raise RuntimeError(f"Persisted artifact does not exist in MinIO: {feature.artifact_uri}")
        observed_checksum = store.checksum(feature.artifact_uri)
        if observed_checksum != feature.checksum:
            raise RuntimeError(
                "Persisted artifact checksum mismatch "
                f"uri={feature.artifact_uri!r} expected={feature.checksum!r} "
                f"actual={observed_checksum!r}."
            )

    for manifest_uri in sorted(manifest_uris):
        store = build_claim_check_store_for_uri(storage_settings, manifest_uri)
        if not store.exists(manifest_uri):
            raise RuntimeError(f"Persisted manifest does not exist in MinIO: {manifest_uri}")
        frame = store.read_parquet(manifest_uri)
        manifest_artifacts = {str(value) for value in frame["artifact_uri"].to_list()}
        expected_artifacts = [
            feature.artifact_uri
            for feature in persisted_features
            if feature.manifest_uri == manifest_uri
        ]
        missing_artifacts = [
            artifact_uri
            for artifact_uri in expected_artifacts
            if artifact_uri not in manifest_artifacts
        ]
        if missing_artifacts:
            raise RuntimeError(
                "Manifest rows drifted from persisted feature artifacts "
                f"manifest_uri={manifest_uri!r} missing={missing_artifacts!r}."
            )
        manifest_rows[manifest_uri] = int(frame.height)

    return {
        "artifact_count": len(persisted_features),
        "manifest_count": len(manifest_rows),
        "manifest_rows": manifest_rows,
    }


def _verify_review_media(*, base_url: str, run_id: str) -> dict[str, object]:
    run_detail = _read_json(f"{base_url}/api/runs/{run_id}")
    if int(run_detail["run"]["segments_persisted"]) < 1:
        raise RuntimeError(f"Review API did not expose persisted segments for run_id={run_id}.")

    tracks_payload = _read_json(f"{base_url}/api/runs/{run_id}/tracks?limit=10")
    persisted_tracks = [
        item
        for item in tracks_payload["items"]
        if item["track_state"]["value"] == "persisted"
    ]
    if not persisted_tracks:
        raise RuntimeError(f"Review API did not expose any persisted tracks for run_id={run_id}.")

    track_id = int(persisted_tracks[0]["track_id"])
    track_detail = _read_json(f"{base_url}/api/runs/{run_id}/tracks/{track_id}?segments_limit=10")
    segment_items = track_detail["segments"]["items"]
    if not segment_items:
        raise RuntimeError(
            f"Review API track detail did not expose persisted segments for track_id={track_id}."
        )

    segment_idx = int(segment_items[0]["segment_idx"])
    stream_summary = _verify_wav_stream(
        f"{base_url}/media/runs/{run_id}/segments/{track_id}/{segment_idx}.wav",
        label=f"Review media stream for run_id={run_id} track_id={track_id}",
    )
    return {
        "track_id": track_id,
        "segment_idx": segment_idx,
        "segment_count": int(track_detail["segments"]["total"]),
        "stream": stream_summary,
    }


def _verify_dataset_bundle(*, datasets_root: Path, run_id: str, bucket: str) -> dict[str, object]:
    output_dir = datasets_root / run_id
    if not output_dir.exists():
        raise RuntimeError(f"Dataset bundle output does not exist: {output_dir.as_posix()}")

    accepted_segments = _read_csv_rows(output_dir / "accepted-segments.csv")
    if not accepted_segments:
        raise RuntimeError("Dataset bundle accepted-segments.csv must contain persisted rows.")

    for row in accepted_segments:
        _assert_minio_uri(
            row["artifact_uri"],
            bucket=bucket,
            run_id=run_id,
            field_name="accepted-segments.csv artifact_uri",
        )
        _assert_minio_uri(
            row["manifest_uri"],
            bucket=bucket,
            run_id=run_id,
            field_name="accepted-segments.csv manifest_uri",
        )

    build_manifest = json.loads((output_dir / "dataset-build-manifest.json").read_text())
    manifest_reference = str(build_manifest["source_truth"]["segment_manifest"])
    _assert_minio_uri(
        manifest_reference,
        bucket=bucket,
        run_id=run_id,
        field_name="dataset-build-manifest.json source_truth.segment_manifest",
    )

    dataset_card = (output_dir / "dataset-card.md").read_text(encoding="utf-8")
    if manifest_reference not in dataset_card:
        raise RuntimeError(
            "dataset-card.md must mention the MinIO-backed claim-check manifest reference."
        )

    return {
        "output_dir": output_dir.as_posix(),
        "accepted_segment_count": len(accepted_segments),
        "manifest_reference": manifest_reference,
    }


def verify_minio_claim_check_flow(
    *,
    run_id: str,
    base_url: str,
    datasets_root: Path,
    artifacts_root: Path,
) -> dict[str, object]:
    validated_run_id = validate_run_id(run_id)
    storage_settings = load_storage_backend_settings(artifacts_root=artifacts_root)
    if storage_settings.normalized_backend() != "minio":
        raise RuntimeError(
            "MinIO claim-check verification requires STORAGE_BACKEND=minio."
        )

    persisted_features = _query_persisted_feature_artifacts(validated_run_id)
    artifact_summary = _verify_feature_artifacts(
        run_id=validated_run_id,
        bucket=storage_settings.bucket,
        artifacts_root=artifacts_root,
        persisted_features=persisted_features,
    )
    review_summary = _verify_review_media(base_url=base_url, run_id=validated_run_id)
    bundle_summary = _verify_dataset_bundle(
        datasets_root=datasets_root,
        run_id=validated_run_id,
        bucket=storage_settings.bucket,
    )

    return {
        "run_id": validated_run_id,
        "storage_backend": storage_settings.normalized_backend(),
        "bucket": storage_settings.bucket,
        "feature_artifacts": artifact_summary,
        "review_media": review_summary,
        "dataset_bundle": bundle_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--datasets-root", type=Path, default=DEFAULT_DATASETS_ROOT)
    parser.add_argument("--artifacts-root", type=Path, default=Path("/app/artifacts"))
    args = parser.parse_args()
    print(  # noqa: T201 - smoke verification CLI
        json.dumps(
            verify_minio_claim_check_flow(
                run_id=args.run_id,
                base_url=args.base_url,
                datasets_root=args.datasets_root,
                artifacts_root=args.artifacts_root,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
