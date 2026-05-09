from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SHELL_SCRIPT = REPO_ROOT / "scripts" / "smoke" / "check-minio-claim-check-flow.sh"
POWERSHELL_SCRIPT = REPO_ROOT / "scripts" / "smoke" / "check-minio-claim-check-flow.ps1"


def test_shell_minio_smoke_script_keeps_live_claim_check_contract() -> None:
    script = SHELL_SCRIPT.read_text(encoding="utf-8")

    assert 'export STORAGE_BACKEND="${STORAGE_BACKEND:-minio}"' in script
    assert 'case "$(printf \'%s\' "${MINIO_SECURE:-false}" | tr \'[:upper:]\' \'[:lower:]\')" in' in script
    assert 'export MINIO_ENDPOINT_URL="https://minio:9000"' in script
    assert "docker compose up --build -d kafka timescaledb minio minio-init" in script
    assert "docker compose run --rm --no-deps --build" in script
    assert "load_storage_backend_settings" in script
    assert "client.list_objects_v2" in script
    assert "client.delete_objects" in script
    assert "docker compose up -d --no-deps processing writer review" in script
    assert 'docker compose run --rm --no-deps dataset-exporter export --run-id "$effective_run_id" >/dev/null' in script
    assert "event_driven_audio_analytics.smoke.verify_minio_claim_check_flow" in script
    assert 'summary_path="$evidence_root_host/$effective_run_id-summary.json"' in script


def test_powershell_minio_smoke_script_keeps_live_claim_check_contract() -> None:
    script = POWERSHELL_SCRIPT.read_text(encoding="utf-8")

    assert '$env:STORAGE_BACKEND = if ($env:STORAGE_BACKEND) { $env:STORAGE_BACKEND } else { "minio" }' in script
    assert '$env:MINIO_SECURE -match "^(?i:1|true|yes|on)$"' in script
    assert '"https://minio:9000"' in script
    assert "docker compose up --build -d kafka timescaledb minio minio-init" in script
    assert "docker compose run --rm --no-deps --build" in script
    assert "load_storage_backend_settings" in script
    assert "client.list_objects_v2" in script
    assert "client.delete_objects" in script
    assert "docker compose up -d --no-deps processing writer review" in script
    assert "docker compose run --rm --no-deps dataset-exporter export --run-id $effectiveRunId | Out-Null" in script
    assert "event_driven_audio_analytics.smoke.verify_minio_claim_check_flow" in script
    assert '$summaryPath = Join-Path $evidenceRoot "$effectiveRunId-summary.json"' in script
