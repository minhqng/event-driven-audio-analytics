from __future__ import annotations

from pathlib import Path


EXPECTED_OUTPUTS = (
    "latency-summary.json",
    "throughput-summary.json",
    "resource-usage-summary.json",
    "scaling-summary.json",
    "evaluation-report.md",
)


def test_powershell_evaluation_script_contract() -> None:
    script = Path("scripts/evaluation/run-evaluation.ps1").read_text(encoding="utf-8")

    for expected_output in EXPECTED_OUTPUTS:
        assert expected_output in script or expected_output == "evaluation-report.md"
    assert "event_driven_audio_analytics.evaluation.collect" in script
    assert "event_driven_audio_analytics.evaluation.report" in script
    assert "deterministic-review-demo" in script
    assert "fma-small-burst-5" in script
    assert "fma-small-burst-100" in script
    assert "fma-small-full-local-experiment" in script
    assert "docker stats --no-stream" in script
    assert "docker compose ps --quiet" in script
    assert "if ($containerIds.Count -gt 0)" in script
    assert 'docker stats --no-stream --format "{{json .}}" @containerIds' in script
    assert "Start-ResourceSampler" in script
    assert "Stop-ResourceSampler" in script
    assert "Start-Job" in script
    assert "function Get-EffectiveStorageBackend" in script
    assert "function Wait-MinioBucketReady" in script
    assert '--entrypoint python pytest' in script
    assert '$infraServices = @("kafka", "timescaledb")' in script
    assert '$infraServices += @("minio", "minio-init")' in script
    assert '$effectiveStorageBackend = Get-EffectiveStorageBackend' in script
    assert 'if ($effectiveStorageBackend -eq "minio") {' in script
    assert 'Wait-MinioBucketReady' in script
    assert "check_bucket = getattr(store, \"check_bucket\")" in script
    assert "check_bucket()" in script
    assert '-e "METADATA_CSV_PATH=$MetadataCsvContainer"' in script
    assert '-e "AUDIO_ROOT_PATH=$AudioRootContainer"' in script
    assert '-e "INGESTION_MAX_TRACKS=$MaxTracks"' in script
    assert "DELETE FROM track_metadata WHERE run_id = %s;" in script
    assert "DELETE FROM audio_features WHERE run_id = %s;" in script
    assert "DELETE FROM system_metrics WHERE run_id = %s;" in script
    assert "DELETE FROM welford_snapshots WHERE run_id = %s;" in script
    assert "DELETE FROM run_checkpoints WHERE run_id = %s;" in script
    assert "--include-scaling" in script
    assert script.rindex('Wait-MinioBucketReady') < script.index('docker compose run --rm --no-deps writer preflight')
    assert script.index('docker compose run --rm --no-deps writer preflight') < script.index('Clear-RunState -RunId $RunId')


def test_bash_evaluation_script_contract() -> None:
    script = Path("scripts/evaluation/run-evaluation.sh").read_text(encoding="utf-8")

    for expected_output in EXPECTED_OUTPUTS:
        assert expected_output in script or expected_output == "evaluation-report.md"
    assert "event_driven_audio_analytics.evaluation.collect" in script
    assert "event_driven_audio_analytics.evaluation.report" in script
    assert "deterministic-review-demo" in script
    assert "fma-small-burst-5" in script
    assert "fma-small-burst-100" in script
    assert "fma-small-full-local-experiment" in script
    assert "docker stats --no-stream" in script
    assert 'container_ids="$(docker compose ps --quiet 2>/dev/null || true)"' in script
    assert 'if [ -n "$container_ids" ]; then' in script
    assert 'docker stats --no-stream --format "{{json .}}" $container_ids' in script
    assert "start_resource_sampler" in script
    assert "stop_active_resource_sampler" in script
    assert "active_sampler_pid" in script
    assert "get_effective_storage_backend()" in script
    assert "wait_minio_bucket_ready()" in script
    assert '--entrypoint python pytest' in script
    assert 'infra_services="kafka timescaledb"' in script
    assert 'infra_services="$infra_services minio minio-init"' in script
    assert 'backend_output="$(' in script
    assert "printf '%s\\n' \"$backend_output\" | tail -n 1 | tr '[:upper:]' '[:lower:]'" in script
    assert 'effective_storage_backend="$(get_effective_storage_backend)"' in script
    assert 'if [ "$effective_storage_backend" = "minio" ]; then' in script
    assert "check_bucket = getattr(store, \"check_bucket\")" in script
    assert "check_bucket()" in script
    assert '-e METADATA_CSV_PATH="$metadata_csv_container"' in script
    assert '-e AUDIO_ROOT_PATH="$audio_root_container"' in script
    assert '-e INGESTION_MAX_TRACKS="$max_tracks"' in script
    assert "DELETE FROM track_metadata WHERE run_id = %s;" in script
    assert "DELETE FROM audio_features WHERE run_id = %s;" in script
    assert "DELETE FROM system_metrics WHERE run_id = %s;" in script
    assert "DELETE FROM welford_snapshots WHERE run_id = %s;" in script
    assert "DELETE FROM run_checkpoints WHERE run_id = %s;" in script
    assert "--include-scaling" in script
    assert script.rindex('wait_minio_bucket_ready') < script.index('docker compose run --rm --no-deps writer preflight')
    assert script.index('docker compose run --rm --no-deps writer preflight') < script.index('cleanup_run_state "$run_id"')
