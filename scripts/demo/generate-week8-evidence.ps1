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

function Write-Week8EvidenceIndex {
    param(
        [string]$OutputPath
    )

    @'
# Week 8 Evidence Index

This directory is the final Week 8 handoff anchor for the bounded PoC evidence set.

## Reliability Hardening

- `restart-replay-baseline.json` captures the first bounded broker-backed run before replay.
- `restart-replay-summary.json` captures the same `run_id` after restarting `processing` and `writer`, then rerunning `ingestion`.
- `preflight-fail-fast.txt` records the expected startup failures before Kafka topics are bootstrapped.

## Dashboard And Demo Evidence

The dashboard-facing artifacts remain under `artifacts/demo/week7/` because the existing deterministic dashboard demo pack and screenshot names are already stable in docs and slides:

- `../week7/dashboard-demo-summary.json`
- `../week7/grafana-api.json`
- `../week7/audio_quality.png`
- `../week7/system_health.png`
- `../week7/demo-artifact-notes.md`

## Practical Week 8 Reading

- Use the Week 8 replay artifacts to explain restart/replay behavior and fail-fast startup checks.
- Use the Week 7 dashboard artifacts to explain TimescaleDB persistence, Grafana provisioning, and panel interpretation.
- Treat this as bounded PoC evidence only; it is not benchmark-scale or production-readiness evidence.
'@ | Set-Content -LiteralPath $OutputPath -Encoding utf8
}

$week8EvidenceRoot = Join-Path $PWD "artifacts\demo\week8"
$evidenceIndexPath = Join-Path $week8EvidenceRoot "evidence-index.md"

Write-Host "Running Week 8 restart/replay evidence path..."
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-restart-replay-flow.ps1
Assert-LastExitCode "check-restart-replay-flow.ps1"

Write-Host "Running Week 7 dashboard evidence path..."
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-week7-dashboard-evidence.ps1
Assert-LastExitCode "generate-week7-dashboard-evidence.ps1"

New-Item -ItemType Directory -Path $week8EvidenceRoot -Force | Out-Null
Write-Week8EvidenceIndex -OutputPath $evidenceIndexPath

Write-Host "Week 8 evidence generation is ready."
Write-Host "Reliability artifacts: $week8EvidenceRoot"
Write-Host "Dashboard artifacts: $(Join-Path $PWD 'artifacts\demo\week7')"
Write-Host "Evidence index: $evidenceIndexPath"
