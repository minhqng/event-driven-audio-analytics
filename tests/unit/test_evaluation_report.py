from __future__ import annotations

import json
from pathlib import Path

from event_driven_audio_analytics.evaluation.report import render_report


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_report_generator_includes_required_sections_and_bounded_caveats(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "latency-summary.json",
        {
            "scenarios": [
                {
                    "scenario": "deterministic-review-demo",
                    "run_id": "eval-demo",
                    "wall_clock_ms": 1000.0,
                    "db_activity_span_ms": 900.0,
                    "artifact_write_ms": {"mean": 10.0},
                    "artifact_read_ms": {"p95": 2.0},
                    "processing_ms": {"p50": 3.0, "p95": 4.0},
                    "writer_write_ms": {"p95": 5.0},
                }
            ]
        },
    )
    _write_json(
        tmp_path / "throughput-summary.json",
        {
            "scenarios": [
                {
                    "scenario": "deterministic-review-demo",
                    "run_id": "eval-demo",
                    "status": "passed",
                    "requested_tracks": 2,
                    "tracks_accepted": 1,
                    "segments_persisted": 3,
                    "storage_backend": "local",
                    "processing_replicas": 1,
                    "tracks_per_minute": 2.0,
                    "segments_per_minute": 3.0,
                    "writer_records_per_minute": 12.0,
                }
            ]
        },
    )
    _write_json(
        tmp_path / "resource-usage-summary.json",
        {
            "scenarios": [
                {
                    "scenario": "deterministic-review-demo",
                    "run_id": "eval-demo",
                    "containers": {},
                }
            ]
        },
    )
    _write_json(
        tmp_path / "scaling-summary.json",
        {
            "topic_partition_note": "audio.segment.ready is currently created with 1 partition",
            "runs": [],
            "verdict": "bounded_partition_limited_evidence",
        },
    )

    report = render_report(tmp_path)

    assert "# FMA-Small Bounded Evaluation Report" in report
    assert "## Scenario Matrix" in report
    assert "## Latency" in report
    assert "## Throughput" in report
    assert "## Resource Usage" in report
    assert "## Scaling Evidence" in report
    assert "## Restart/Replay Evidence" in report
    assert "not benchmark-scale performance evidence" in report
    assert "single-partition Kafka topic setup" in report
