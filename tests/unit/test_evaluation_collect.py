from __future__ import annotations

import json
from pathlib import Path

import pytest

from event_driven_audio_analytics.evaluation.collect import (
    RunObservation,
    _update_output_files,
    build_summary_entries,
    measure_artifact_reads,
)
from event_driven_audio_analytics.shared.checksum import sha256_bytes
from event_driven_audio_analytics.shared.storage import StorageBackendSettings


class FakeStore:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read_bytes(self, uri: str) -> bytes:
        return self.payload


def _observation() -> RunObservation:
    return RunObservation(
        tracks_total=5,
        tracks_accepted=4,
        segments_persisted=12,
        writer_record_count=24,
        db_activity_span_ms=1500.0,
        artifact_write_ms_values=(10.0,),
        processing_ms_values=(1.0, 2.0, 3.0),
        writer_write_ms_values=(4.0, 5.0),
        artifact_rows=(),
    )


def test_build_summary_entries_maps_observation_to_expected_shapes() -> None:
    latency, throughput, resource, scaling = build_summary_entries(
        scenario="fma-small-burst-5",
        run_id="eval-fma-5",
        status="passed",
        skip_reason=None,
        requested_tracks=5,
        storage_backend="local",
        processing_replicas=1,
        duration_s=60.0,
        observation=_observation(),
        artifact_read_ms_values=[7.0, 9.0],
        resource_containers={
            "processing": {
                "cpu_percent": {"mean": 12.5},
            }
        },
    )

    assert latency["processing_ms"]["count"] == 3
    assert latency["artifact_write_ms"]["mean"] == 10.0
    assert throughput["tracks_per_minute"] == 5.0
    assert throughput["segments_per_minute"] == 12.0
    assert resource["containers"]["processing"]["cpu_percent"]["mean"] == 12.5
    assert scaling["cpu_processing_mean_percent"] == 12.5


def test_update_output_files_writes_all_required_json_outputs(tmp_path: Path) -> None:
    latency, throughput, resource, scaling = build_summary_entries(
        scenario="fma-small-scaling-r1",
        run_id="eval-scale-r1",
        status="skipped",
        skip_reason="local FMA-Small files were unavailable",
        requested_tracks=5,
        storage_backend="local",
        processing_replicas=1,
        duration_s=0.0,
        observation=RunObservation(
            tracks_total=0,
            tracks_accepted=0,
            segments_persisted=0,
            writer_record_count=0,
            db_activity_span_ms=None,
            artifact_write_ms_values=(),
            processing_ms_values=(),
            writer_write_ms_values=(),
            artifact_rows=(),
        ),
        artifact_read_ms_values=[],
        resource_containers={},
    )

    _update_output_files(
        output_root=tmp_path,
        latency_entry=latency,
        throughput_entry=throughput,
        resource_entry=resource,
        scaling_entry=scaling,
        sample_interval_s=2.0,
    )

    assert (tmp_path / "latency-summary.json").is_file()
    assert (tmp_path / "throughput-summary.json").is_file()
    assert (tmp_path / "resource-usage-summary.json").is_file()
    assert (tmp_path / "scaling-summary.json").is_file()
    scaling_payload = json.loads((tmp_path / "scaling-summary.json").read_text(encoding="utf-8"))
    assert scaling_payload["runs"][0]["status"] == "skipped"
    assert "1 partition" in scaling_payload["topic_partition_note"]


def test_artifact_read_sampler_verifies_checksum(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"audio-bytes"
    monkeypatch.setattr(
        "event_driven_audio_analytics.evaluation.collect.build_claim_check_store_for_uri",
        lambda settings, uri: FakeStore(payload),
    )

    latencies = measure_artifact_reads(
        (("/artifacts/runs/demo-run/segments/2/0.wav", sha256_bytes(payload)),),
        storage_settings=StorageBackendSettings(),
    )

    assert len(latencies) == 1
    assert latencies[0] >= 0.0


def test_artifact_read_sampler_rejects_checksum_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "event_driven_audio_analytics.evaluation.collect.build_claim_check_store_for_uri",
        lambda settings, uri: FakeStore(b"wrong-bytes"),
    )

    with pytest.raises(RuntimeError, match="Artifact checksum mismatch"):
        measure_artifact_reads(
            (("/artifacts/runs/demo-run/segments/2/0.wav", sha256_bytes(b"expected")),),
            storage_settings=StorageBackendSettings(),
        )
