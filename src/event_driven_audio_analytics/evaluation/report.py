"""Render the bounded FMA-Small evaluation report."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from event_driven_audio_analytics.evaluation.collect import DEFAULT_OUTPUT_ROOT


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt(value: object, *, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}{suffix}"
    return f"{value}{suffix}"


def _scenario_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("scenario", "")), str(row.get("run_id", ""))


def _index(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {_scenario_key(row): row for row in rows}


def _table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def _restart_replay_lines(output_root: Path) -> list[str]:
    restart_root = output_root.parent / "restart-replay"
    summary_path = restart_root / "restart-replay-summary.json"
    baseline_path = restart_root / "restart-replay-baseline.json"
    if not summary_path.exists() or not baseline_path.exists():
        return [
            "Restart/replay artifacts were not present when the evaluation report was generated.",
        ]

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    return [
        f"- Summary: `{summary_path.as_posix()}`",
        f"- Baseline: `{baseline_path.as_posix()}`",
        f"- Run ID: `{summary.get('run_id', baseline.get('run_id', 'unknown'))}`",
        f"- Metadata rows: {_fmt(summary.get('metadata_count'))}",
        f"- Feature rows: {_fmt(summary.get('feature_count'))}",
        f"- Processing metric rows: {_fmt(summary.get('processing_ms_count'))}",
        f"- Writer write metric rows: {_fmt(summary.get('writer_write_ms_count'))}",
    ]


def render_report(output_root: Path) -> str:
    """Render markdown from evaluation summary files."""

    latency_summary = _load_json(output_root / "latency-summary.json", {"scenarios": []})
    throughput_summary = _load_json(output_root / "throughput-summary.json", {"scenarios": []})
    resource_summary = _load_json(output_root / "resource-usage-summary.json", {"scenarios": []})
    scaling_summary = _load_json(output_root / "scaling-summary.json", {"runs": []})

    latency_rows = _index(list(latency_summary.get("scenarios", [])))
    throughput_rows = list(throughput_summary.get("scenarios", []))
    resource_rows = _index(list(resource_summary.get("scenarios", [])))

    scenario_table = _table(
        (
            "scenario",
            "run_id",
            "status",
            "requested_tracks",
            "accepted_tracks",
            "segments",
            "storage_backend",
            "processing_replicas",
        ),
        [
            (
                row.get("scenario"),
                row.get("run_id"),
                row.get("status"),
                _fmt(row.get("requested_tracks")),
                _fmt(row.get("tracks_accepted")),
                _fmt(row.get("segments_persisted")),
                row.get("storage_backend"),
                row.get("processing_replicas"),
            )
            for row in throughput_rows
        ],
    )

    latency_table = _table(
        (
            "scenario",
            "wall_clock_ms",
            "db_span_ms",
            "artifact_write_mean_ms",
            "artifact_read_p95_ms",
            "processing_p50_ms",
            "processing_p95_ms",
            "writer_p95_ms",
        ),
        [
            (
                key[0],
                _fmt(row.get("wall_clock_ms")),
                _fmt(row.get("db_activity_span_ms")),
                _fmt(row.get("artifact_write_ms", {}).get("mean")),
                _fmt(row.get("artifact_read_ms", {}).get("p95")),
                _fmt(row.get("processing_ms", {}).get("p50")),
                _fmt(row.get("processing_ms", {}).get("p95")),
                _fmt(row.get("writer_write_ms", {}).get("p95")),
            )
            for key, row in sorted(latency_rows.items())
        ],
    )

    throughput_table = _table(
        ("scenario", "tracks_per_minute", "segments_per_minute", "writer_records_per_minute"),
        [
            (
                row.get("scenario"),
                _fmt(row.get("tracks_per_minute")),
                _fmt(row.get("segments_per_minute")),
                _fmt(row.get("writer_records_per_minute")),
            )
            for row in throughput_rows
        ],
    )

    resource_table_rows: list[tuple[object, ...]] = []
    for key, row in sorted(resource_rows.items()):
        containers = row.get("containers", {})
        if not isinstance(containers, dict) or not containers:
            resource_table_rows.append((key[0], "n/a", "n/a", "n/a", "n/a"))
            continue
        for service_name, summary in sorted(containers.items()):
            if not isinstance(summary, dict):
                continue
            resource_table_rows.append(
                (
                    key[0],
                    service_name,
                    _fmt(summary.get("cpu_percent", {}).get("mean")),
                    _fmt(summary.get("cpu_percent", {}).get("max")),
                    _fmt(summary.get("memory_mb", {}).get("max")),
                )
            )
    resource_table = _table(
        ("scenario", "container", "cpu_mean_pct", "cpu_max_pct", "memory_max_mb"),
        resource_table_rows,
    )

    scaling_table = _table(
        (
            "scenario",
            "processing_replicas",
            "segments_per_minute",
            "processing_ms_p95",
            "processing_cpu_mean_pct",
        ),
        [
            (
                row.get("scenario"),
                row.get("processing_replicas"),
                _fmt(row.get("segments_per_minute")),
                _fmt(row.get("processing_ms_p95")),
                _fmt(row.get("cpu_processing_mean_percent")),
            )
            for row in scaling_summary.get("runs", [])
        ],
    )

    lines = [
        "# FMA-Small Bounded Evaluation Report",
        "",
        f"Generated at: `{_utc_now_iso()}`",
        "",
        "## Summary",
        "",
        (
            "This report is bounded local FMA-Small evidence for the PoC. "
            "It is not benchmark-scale performance evidence and does not claim "
            "production-ready throughput."
        ),
        "",
        "## Scenario Matrix",
        "",
        *scenario_table,
        "",
        "## Latency",
        "",
        *latency_table,
        "",
        "## Throughput",
        "",
        *throughput_table,
        "",
        "## Resource Usage",
        "",
        *resource_table,
        "",
        "## Scaling Evidence",
        "",
        str(scaling_summary.get("topic_partition_note", "")),
        "",
        *scaling_table,
        "",
        f"Verdict: `{scaling_summary.get('verdict', 'bounded_partition_limited_evidence')}`",
        "",
        "## Restart/Replay Evidence",
        "",
        *_restart_replay_lines(output_root),
        "",
        "## Limitations",
        "",
        "- Measurements are bounded local PoC evidence only.",
        "- End-to-end latency uses script wall-clock timing and DB activity span.",
        "- Per-segment ingestion-created timestamps are not persisted through the full pipeline.",
        "- CPU and memory are Docker container samples, not kernel-level profiling.",
        "- Scaling is limited by the current single-partition Kafka topic setup.",
        "- Full FMA-Small runs are optional local experiments only.",
        "- No model training, model serving, Flink, Spark, or additional datasets are included.",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    report = render_report(output_root)
    report_path = output_root / "evaluation-report.md"
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps({"report_path": report_path.as_posix()}, sort_keys=True))


if __name__ == "__main__":
    main()
