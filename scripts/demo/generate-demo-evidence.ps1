Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot "../.."))

function Assert-LastExitCode {
    param(
        [string]$Context
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$Context failed with exit code $LASTEXITCODE."
    }
}

function Write-DemoEvidenceIndex {
    param(
        [string]$OutputPath
    )

    @'
# Final Demo Evidence Index

This directory is the final handoff anchor for the bounded PoC evidence set.

## Reliability Evidence

- `restart-replay-baseline.json` captures the first bounded broker-backed run before replay.
- `restart-replay-summary.json` captures the same `run_id` after restarting `processing` and `writer`, then rerunning `ingestion`.
- `preflight-fail-fast.txt` records the expected startup failures before Kafka topics are bootstrapped.

## Dashboard Evidence

The dashboard-facing artifacts remain under `artifacts/demo/week7/` because that historical pack name is already stable across the repo:

- `../week7/dashboard-demo-summary.json`
- `../week7/review-api.json`
- `../week7/grafana-api.json`
- `../week7/run_review.png`
- `../week7/audio_quality.png`
- `../week7/system_health.png`
- `../week7/demo-artifact-notes.md`

## Practical Reading Order

- Use the review artifact pack first to explain the run, track, and segment story.
- Use the restart/replay artifacts next to explain startup gating and replay safety.
- Use the dashboard artifacts last to explain TimescaleDB persistence, Grafana provisioning, and panel interpretation.
- Treat this as bounded PoC evidence only; it is not benchmark-scale or production-readiness evidence.
'@ | Set-Content -LiteralPath $OutputPath -Encoding utf8
}

$demoEvidenceRoot = Join-Path $PWD "artifacts\demo\week8"
$evidenceIndexPath = Join-Path $demoEvidenceRoot "evidence-index.md"

Write-Host "Running restart/replay evidence path..."
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-restart-replay-flow.ps1
Assert-LastExitCode "check-restart-replay-flow.ps1"

Write-Host "Running dashboard evidence path..."
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-dashboard-evidence.ps1
Assert-LastExitCode "generate-dashboard-evidence.ps1"

New-Item -ItemType Directory -Path $demoEvidenceRoot -Force | Out-Null
Write-DemoEvidenceIndex -OutputPath $evidenceIndexPath

Write-Host "Final demo evidence is ready."
Write-Host "Reliability artifacts: $demoEvidenceRoot"
Write-Host "Dashboard artifacts: $(Join-Path $PWD 'artifacts\demo\week7')"
Write-Host "Evidence index: $evidenceIndexPath"
