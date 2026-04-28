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

## Restart/Replay Evidence

- `restart-replay/restart-replay-baseline.json` captures the first bounded broker-backed run before replay.
- `restart-replay/restart-replay-summary.json` captures the same `run_id` after restarting `processing` and `writer`, then rerunning `ingestion`.
- `restart-replay/preflight-fail-fast.txt` records the expected startup failures before Kafka topics are bootstrapped.

## Review/Dashboard Evidence

The review/dashboard artifacts are generated under `artifacts/evidence/final-demo/review-dashboard/`:

- `review-dashboard/review-dashboard-summary.json`
- `review-dashboard/review-api.json`
- `review-dashboard/grafana-api.json`
- `review-dashboard/review-console.png`
- `review-dashboard/audio-quality-dashboard.png`
- `review-dashboard/system-health-dashboard.png`
- `review-dashboard/review-dashboard-notes.md`

## Practical Reading Order

- Use the review artifact pack first to explain the run, track, and segment story.
- Use the restart/replay artifacts next to explain startup gating and replay safety.
- Use the review/dashboard artifacts last to explain TimescaleDB persistence, Grafana provisioning, and panel interpretation.
- Treat this as bounded PoC evidence only; it is not benchmark-scale or production-readiness evidence.
'@ | Set-Content -LiteralPath $OutputPath -Encoding utf8
}

$demoEvidenceRoot = Join-Path $PWD "artifacts\evidence\final-demo"
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
Write-Host "Restart/replay artifacts: $(Join-Path $demoEvidenceRoot 'restart-replay')"
Write-Host "Review/dashboard artifacts: $(Join-Path $PWD 'artifacts\evidence\final-demo\review-dashboard')"
Write-Host "Evidence index: $evidenceIndexPath"
