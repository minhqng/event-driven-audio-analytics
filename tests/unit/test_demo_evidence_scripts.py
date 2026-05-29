from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SHELL_SCRIPT = REPO_ROOT / "scripts" / "demo" / "generate-demo-evidence.sh"
POWERSHELL_SCRIPT = REPO_ROOT / "scripts" / "demo" / "generate-demo-evidence.ps1"
POWERSHELL_DASHBOARD_SCRIPT = REPO_ROOT / "scripts" / "demo" / "generate-dashboard-evidence.ps1"


def test_shell_demo_script_keeps_dataset_export_contract() -> None:
    script = SHELL_SCRIPT.read_text(encoding="utf-8")

    assert 'dataset_run_ids="demo-high-energy demo-silent-oriented demo-validation-failure"' in script
    assert "docker compose build dataset-exporter" in script
    assert 'docker compose run --rm --no-deps dataset-exporter export --run-id "$run_id" >/dev/null' in script
    assert "event_driven_audio_analytics.smoke.verify_dataset_demo_outputs" in script
    assert 'mv "$dataset_summary_tmp" "$dataset_summary_path"' in script
    assert 'assert_path_exists "artifacts/datasets/$run_id"' in script
    assert "thesis-aligned bounded FMA-Small evidence set" in script
    assert "MinIO/private-cloud, K3s, and evaluation evidence paths" in script


def test_powershell_demo_script_keeps_dataset_export_contract() -> None:
    script = POWERSHELL_SCRIPT.read_text(encoding="utf-8")

    assert '$datasetRunIds = @("demo-high-energy", "demo-silent-oriented", "demo-validation-failure")' in script
    assert "docker compose build dataset-exporter" in script
    assert "docker compose run --rm --no-deps dataset-exporter export --run-id $runId | Out-Null" in script
    assert "event_driven_audio_analytics.smoke.verify_dataset_demo_outputs" in script
    assert "$datasetSummary | Set-Content -LiteralPath $datasetSummaryPath -Encoding utf8" in script
    assert '$datasetRunPath = Join-Path $PWD "artifacts\\datasets\\$runId"' in script
    assert "thesis-aligned bounded FMA-Small evidence set" in script
    assert "MinIO/private-cloud, K3s, and evaluation evidence paths" in script


def test_powershell_dashboard_script_suppresses_browser_stderr() -> None:
    script = POWERSHELL_DASHBOARD_SCRIPT.read_text(encoding="utf-8")

    assert "$previousErrorActionPreference = $ErrorActionPreference" in script
    assert '$ErrorActionPreference = "Continue"' in script
    assert "$Url 2>$null | Out-Null" in script
    assert "$Url 2>$null | Out-String" in script


def test_dashboard_evidence_scripts_keep_stable_grafana_contract() -> None:
    shell_script = (REPO_ROOT / "scripts" / "demo" / "generate-dashboard-evidence.sh").read_text(
        encoding="utf-8"
    )
    powershell_script = POWERSHELL_DASHBOARD_SCRIPT.read_text(encoding="utf-8")

    for script in (shell_script, powershell_script):
        assert "/d/audio-quality/audio-quality?from=now-6h&to=now&kiosk" in script
        assert "/d/system-health/system-health?from=now-6h&to=now&kiosk" in script
        assert "api/dashboards/uid/audio-quality" in script
        assert "api/dashboards/uid/system-health" in script
        assert "audio-quality-dashboard.png" in script
        assert "system-health-dashboard.png" in script
