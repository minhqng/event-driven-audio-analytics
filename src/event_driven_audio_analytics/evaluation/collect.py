"""Collect bounded FMA-Small evaluation summaries from persisted truth."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from os import replace
from pathlib import Path
from time import perf_counter
from typing import Any

from event_driven_audio_analytics.evaluation.resources import (
    load_resource_samples,
    summarize_resource_samples,
)
from event_driven_audio_analytics.evaluation.stats import (
    rate_per_minute,
    summarize_distribution,
    summarize_total,
)
from event_driven_audio_analytics.shared.checksum import sha256_bytes
from event_driven_audio_analytics.shared.db import open_database_connection
from event_driven_audio_analytics.shared.settings import (
    load_database_settings,
    load_storage_backend_settings,
)
from event_driven_audio_analytics.shared.storage import (
    StorageBackendSettings,
    build_claim_check_store_for_uri,
    validate_run_id,
)


FORMAT_VERSION = 1
DEFAULT_OUTPUT_ROOT = Path("/app/artifacts/evidence/final-demo/evaluation")
TOPIC_PARTITION_NOTE = (
    "audio.segment.ready is currently created with 1 partition; "
    "processing replica scaling is partition-bound."
)


@dataclass(frozen=True, slots=True)
class RunObservation:
    """Persisted run facts needed by the evaluation summaries."""

    tracks_total: int
    tracks_accepted: int
    segments_persisted: int
    writer_record_count: int
    db_activity_span_ms: float | None
    artifact_write_ms_values: tuple[float, ...]
    processing_ms_values: tuple[float, ...]
    writer_write_ms_values: tuple[float, ...]
    artifact_rows: tuple[tuple[str, str], ...]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    replace(tmp_path, path)


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _upsert(items: list[dict[str, Any]], item: dict[str, Any], keys: tuple[str, ...]) -> None:
    for index, existing in enumerate(items):
        if all(existing.get(key) == item.get(key) for key in keys):
            items[index] = item
            return
    items.append(item)


def _activity_span_ms(first_seen_at: object, last_seen_at: object) -> float | None:
    if first_seen_at is None or last_seen_at is None:
        return None
    if not isinstance(first_seen_at, datetime) or not isinstance(last_seen_at, datetime):
        return None
    return max((last_seen_at - first_seen_at).total_seconds() * 1000.0, 0.0)


def query_run_observation(
    *,
    run_id: str,
    artifact_sample_size: int,
) -> RunObservation:
    """Query persisted truth for one completed run."""

    database_settings = load_database_settings()
    with open_database_connection(database_settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*)::int AS tracks_total,
                    COUNT(*) FILTER (WHERE validation_status = 'validated')::int
                        AS tracks_accepted
                FROM track_metadata
                WHERE run_id = %s;
                """,
                (run_id,),
            )
            tracks_total, tracks_accepted = cursor.fetchone() or (0, 0)

            cursor.execute(
                """
                SELECT COUNT(*)::int
                FROM audio_features
                WHERE run_id = %s;
                """,
                (run_id,),
            )
            segments_persisted = int((cursor.fetchone() or (0,))[0])

            cursor.execute(
                """
                SELECT COUNT(*)::int
                FROM system_metrics
                WHERE run_id = %s
                  AND service_name = 'writer'
                  AND metric_name = 'write_ms';
                """,
                (run_id,),
            )
            writer_record_count = int((cursor.fetchone() or (0,))[0])

            cursor.execute(
                """
                WITH observed AS (
                    SELECT created_at AS observed_at FROM track_metadata WHERE run_id = %s
                    UNION ALL
                    SELECT ts AS observed_at FROM audio_features WHERE run_id = %s
                    UNION ALL
                    SELECT ts AS observed_at FROM system_metrics WHERE run_id = %s
                )
                SELECT MIN(observed_at), MAX(observed_at)
                FROM observed;
                """,
                (run_id, run_id, run_id),
            )
            first_seen_at, last_seen_at = cursor.fetchone() or (None, None)

            cursor.execute(
                """
                SELECT metric_value
                FROM system_metrics
                WHERE run_id = %s
                  AND service_name = 'ingestion'
                  AND metric_name = 'artifact_write_ms'
                ORDER BY ts ASC;
                """,
                (run_id,),
            )
            artifact_write_ms_values = tuple(float(row[0]) for row in cursor.fetchall())

            cursor.execute(
                """
                SELECT processing_ms
                FROM audio_features
                WHERE run_id = %s
                ORDER BY track_id ASC, segment_idx ASC, ts ASC;
                """,
                (run_id,),
            )
            processing_ms_values = tuple(float(row[0]) for row in cursor.fetchall())

            cursor.execute(
                """
                SELECT metric_value
                FROM system_metrics
                WHERE run_id = %s
                  AND service_name = 'writer'
                  AND metric_name = 'write_ms'
                ORDER BY ts ASC;
                """,
                (run_id,),
            )
            writer_write_ms_values = tuple(float(row[0]) for row in cursor.fetchall())

            cursor.execute(
                """
                SELECT artifact_uri, checksum
                FROM audio_features
                WHERE run_id = %s
                ORDER BY track_id ASC, segment_idx ASC, ts ASC
                LIMIT %s;
                """,
                (run_id, artifact_sample_size),
            )
            artifact_rows = tuple((str(uri), str(checksum)) for uri, checksum in cursor.fetchall())

    return RunObservation(
        tracks_total=int(tracks_total),
        tracks_accepted=int(tracks_accepted),
        segments_persisted=segments_persisted,
        writer_record_count=writer_record_count,
        db_activity_span_ms=_activity_span_ms(first_seen_at, last_seen_at),
        artifact_write_ms_values=artifact_write_ms_values,
        processing_ms_values=processing_ms_values,
        writer_write_ms_values=writer_write_ms_values,
        artifact_rows=artifact_rows,
    )


def measure_artifact_reads(
    artifact_rows: tuple[tuple[str, str], ...],
    *,
    storage_settings: StorageBackendSettings,
) -> list[float]:
    """Read claim-check artifacts and verify checksum before recording latency."""

    read_latencies_ms: list[float] = []
    for artifact_uri, expected_checksum in artifact_rows:
        store = build_claim_check_store_for_uri(storage_settings, artifact_uri)
        started_at = perf_counter()
        payload = store.read_bytes(artifact_uri)
        read_latencies_ms.append((perf_counter() - started_at) * 1000.0)
        actual_checksum = sha256_bytes(payload)
        if actual_checksum != expected_checksum:
            raise RuntimeError(
                "Artifact checksum mismatch during evaluation read sample "
                f"uri={artifact_uri!r}."
            )
    return read_latencies_ms


def _skipped_observation() -> RunObservation:
    return RunObservation(
        tracks_total=0,
        tracks_accepted=0,
        segments_persisted=0,
        writer_record_count=0,
        db_activity_span_ms=None,
        artifact_write_ms_values=(),
        processing_ms_values=(),
        writer_write_ms_values=(),
        artifact_rows=(),
    )


def build_summary_entries(
    *,
    scenario: str,
    run_id: str,
    status: str,
    skip_reason: str | None,
    requested_tracks: int | None,
    storage_backend: str,
    processing_replicas: int,
    duration_s: float,
    observation: RunObservation,
    artifact_read_ms_values: list[float],
    resource_containers: dict[str, object],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build latency, throughput, resource, and scaling entries for one scenario."""

    base_fields: dict[str, Any] = {
        "scenario": scenario,
        "run_id": run_id,
        "status": status,
        "requested_tracks": requested_tracks,
        "storage_backend": storage_backend,
        "processing_replicas": processing_replicas,
    }
    if skip_reason is not None:
        base_fields["skip_reason"] = skip_reason

    latency_entry = {
        **base_fields,
        "wall_clock_ms": round(duration_s * 1000.0, 6),
        "db_activity_span_ms": (
            None
            if observation.db_activity_span_ms is None
            else round(observation.db_activity_span_ms, 6)
        ),
        "artifact_write_ms": summarize_total(observation.artifact_write_ms_values),
        "artifact_read_ms": summarize_distribution(artifact_read_ms_values),
        "processing_ms": summarize_distribution(observation.processing_ms_values),
        "writer_write_ms": summarize_distribution(observation.writer_write_ms_values),
    }
    throughput_entry = {
        **base_fields,
        "duration_s": round(duration_s, 6),
        "tracks_total": observation.tracks_total,
        "tracks_accepted": observation.tracks_accepted,
        "segments_persisted": observation.segments_persisted,
        "writer_record_count": observation.writer_record_count,
        "tracks_per_minute": rate_per_minute(observation.tracks_total, duration_s),
        "accepted_tracks_per_minute": rate_per_minute(observation.tracks_accepted, duration_s),
        "segments_per_minute": rate_per_minute(observation.segments_persisted, duration_s),
        "writer_records_per_minute": rate_per_minute(observation.writer_record_count, duration_s),
    }
    resource_entry = {
        **base_fields,
        "containers": resource_containers,
    }
    scaling_entry = {
        **base_fields,
        "segments_per_minute": throughput_entry["segments_per_minute"],
        "processing_ms_p95": latency_entry["processing_ms"]["p95"],
        "cpu_processing_mean_percent": (
            resource_containers.get("processing", {})
            .get("cpu_percent", {})
            .get("mean")
            if isinstance(resource_containers.get("processing"), dict)
            else None
        ),
    }
    return latency_entry, throughput_entry, resource_entry, scaling_entry


def _update_output_files(
    *,
    output_root: Path,
    latency_entry: dict[str, Any],
    throughput_entry: dict[str, Any],
    resource_entry: dict[str, Any],
    scaling_entry: dict[str, Any] | None,
    sample_interval_s: float,
) -> None:
    generated_at = _utc_now_iso()

    latency_summary = _load_json(
        output_root / "latency-summary.json",
        {"format_version": FORMAT_VERSION, "generated_at": generated_at, "scenarios": []},
    )
    latency_summary["generated_at"] = generated_at
    _upsert(latency_summary["scenarios"], latency_entry, ("scenario", "run_id"))
    _write_json(output_root / "latency-summary.json", latency_summary)

    throughput_summary = _load_json(
        output_root / "throughput-summary.json",
        {"format_version": FORMAT_VERSION, "generated_at": generated_at, "scenarios": []},
    )
    throughput_summary["generated_at"] = generated_at
    _upsert(throughput_summary["scenarios"], throughput_entry, ("scenario", "run_id"))
    _write_json(output_root / "throughput-summary.json", throughput_summary)

    resource_summary = _load_json(
        output_root / "resource-usage-summary.json",
        {
            "format_version": FORMAT_VERSION,
            "generated_at": generated_at,
            "sample_interval_s": sample_interval_s,
            "scenarios": [],
        },
    )
    resource_summary["generated_at"] = generated_at
    resource_summary["sample_interval_s"] = sample_interval_s
    _upsert(resource_summary["scenarios"], resource_entry, ("scenario", "run_id"))
    _write_json(output_root / "resource-usage-summary.json", resource_summary)

    scaling_summary = _load_json(
        output_root / "scaling-summary.json",
        {
            "format_version": FORMAT_VERSION,
            "generated_at": generated_at,
            "topic_partition_note": TOPIC_PARTITION_NOTE,
            "runs": [],
            "verdict": "bounded_partition_limited_evidence",
        },
    )
    scaling_summary["generated_at"] = generated_at
    scaling_summary["topic_partition_note"] = TOPIC_PARTITION_NOTE
    scaling_summary["verdict"] = "bounded_partition_limited_evidence"
    if scaling_entry is not None:
        _upsert(
            scaling_summary["runs"],
            scaling_entry,
            ("scenario", "run_id", "processing_replicas"),
        )
    _write_json(output_root / "scaling-summary.json", scaling_summary)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--status", choices=("passed", "skipped", "failed"), default="passed")
    parser.add_argument("--skip-reason")
    parser.add_argument("--requested-tracks", type=int)
    parser.add_argument("--processing-replicas", type=int, default=1)
    parser.add_argument("--duration-s", type=float, default=0.0)
    parser.add_argument("--resource-samples-jsonl")
    parser.add_argument("--resource-sample-interval-s", type=float, default=2.0)
    parser.add_argument("--artifact-read-sample-size", type=int, default=20)
    parser.add_argument("--include-scaling", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = validate_run_id(args.run_id)
    output_root = Path(args.output_root)
    artifacts_root = Path(os.getenv("ARTIFACTS_ROOT", "/app/artifacts"))
    storage_settings = load_storage_backend_settings(artifacts_root=artifacts_root)

    if args.status == "skipped":
        observation = _skipped_observation()
        artifact_read_ms_values: list[float] = []
    else:
        observation = query_run_observation(
            run_id=run_id,
            artifact_sample_size=args.artifact_read_sample_size,
        )
        artifact_read_ms_values = measure_artifact_reads(
            observation.artifact_rows,
            storage_settings=storage_settings,
        )

    resource_samples = load_resource_samples(args.resource_samples_jsonl)
    resource_containers = summarize_resource_samples(resource_samples)
    entries = build_summary_entries(
        scenario=args.scenario,
        run_id=run_id,
        status=args.status,
        skip_reason=args.skip_reason,
        requested_tracks=args.requested_tracks,
        storage_backend=storage_settings.normalized_backend(),
        processing_replicas=args.processing_replicas,
        duration_s=max(args.duration_s, 0.0),
        observation=observation,
        artifact_read_ms_values=artifact_read_ms_values,
        resource_containers=resource_containers,
    )
    latency_entry, throughput_entry, resource_entry, scaling_entry = entries
    _update_output_files(
        output_root=output_root,
        latency_entry=latency_entry,
        throughput_entry=throughput_entry,
        resource_entry=resource_entry,
        scaling_entry=scaling_entry if args.include_scaling else None,
        sample_interval_s=args.resource_sample_interval_s,
    )

    print(
        json.dumps(
            {
                "run_id": run_id,
                "scenario": args.scenario,
                "status": args.status,
                "output_root": output_root.as_posix(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
