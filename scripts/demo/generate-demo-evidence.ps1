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

## Review/Dashboard Evidence

The review/dashboard artifacts are generated under `artifacts/evidence/final-demo/review-dashboard/`:

- `review-dashboard/review-dashboard-summary.json`
- `review-dashboard/review-api.json`
- `review-dashboard/grafana-api.json`
- `review-dashboard/review-console.png`
- `review-dashboard/audio-quality-dashboard.png`
- `review-dashboard/system-health-dashboard.png`
- `review-dashboard/review-dashboard-notes.md`

## Dataset Export Evidence

- `dataset-exports/dataset-export-summary.json` verifies the deterministic dataset bundles for all demo runs.
- `artifacts/datasets/demo-high-energy/` is the accepted high-energy dataset bundle.
- `artifacts/datasets/demo-silent-oriented/` is the accepted silent-oriented dataset bundle.
- `artifacts/datasets/demo-validation-failure/` is the rejected-track validation-failure dataset bundle.

## Restart/Replay Evidence

- `restart-replay/restart-replay-baseline.json` captures the first bounded broker-backed run before replay.
- `restart-replay/restart-replay-summary.json` captures the same `run_id` after restarting `processing` and `writer`, then rerunning `ingestion`.
- `restart-replay/preflight-fail-fast.txt` records the expected startup failures before Kafka topics are bootstrapped.

## Practical Reading Order

- Use the review artifact pack first to explain the run, track, and segment story.
- Use the Grafana artifacts next to corroborate TimescaleDB persistence and panel interpretation.
- Use the dataset export summary and run bundles third to show the final FMA-Small analytics/dataset outputs.
- Use the restart/replay artifacts last to explain startup gating and replay safety.
- Treat this as bounded PoC evidence only; it is not benchmark-scale or production-readiness evidence.
'@ | Set-Content -LiteralPath $OutputPath -Encoding utf8
}

$demoEvidenceRoot = Join-Path $PWD "artifacts\evidence\final-demo"
$evidenceIndexPath = Join-Path $demoEvidenceRoot "evidence-index.md"
$datasetEvidenceRoot = Join-Path $demoEvidenceRoot "dataset-exports"
$datasetSummaryPath = Join-Path $datasetEvidenceRoot "dataset-export-summary.json"
$datasetRunIds = @("demo-high-energy", "demo-silent-oriented", "demo-validation-failure")

Write-Host "Cleaning prior dataset export evidence..."
if (Test-Path $datasetEvidenceRoot) {
    Remove-Item -LiteralPath $datasetEvidenceRoot -Recurse -Force
}
foreach ($runId in $datasetRunIds) {
    $datasetRunPath = Join-Path $PWD "artifacts\datasets\$runId"
    if (Test-Path $datasetRunPath) {
        Remove-Item -LiteralPath $datasetRunPath -Recurse -Force
    }
}
New-Item -ItemType Directory -Path $datasetEvidenceRoot -Force | Out-Null

Write-Host "Running restart/replay evidence path..."
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-restart-replay-flow.ps1
Assert-LastExitCode "check-restart-replay-flow.ps1"

Write-Host "Running dashboard evidence path..."
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-dashboard-evidence.ps1
Assert-LastExitCode "generate-dashboard-evidence.ps1"

Write-Host "Building dataset-exporter image..."
docker compose build dataset-exporter
Assert-LastExitCode "docker compose build dataset-exporter"

foreach ($runId in $datasetRunIds) {
    Write-Host "Exporting dataset bundle for $runId..."
    docker compose run --rm --no-deps dataset-exporter export --run-id $runId | Out-Null
    Assert-LastExitCode "docker compose run dataset-exporter export --run-id $runId"
}

Write-Host "Verifying exported dataset bundles..."
$datasetSummary = docker compose run --rm --no-deps --entrypoint python `
    dataset-exporter `
    -m event_driven_audio_analytics.smoke.verify_dataset_demo_outputs
Assert-LastExitCode "verify_dataset_demo_outputs"
$datasetSummary | Set-Content -LiteralPath $datasetSummaryPath -Encoding utf8

foreach ($path in @($datasetSummaryPath)) {
    if (-not (Test-Path $path)) {
        throw "Expected path missing: $path"
    }
}
foreach ($runId in $datasetRunIds) {
    $datasetRunPath = Join-Path $PWD "artifacts\datasets\$runId"
    if (-not (Test-Path $datasetRunPath)) {
        throw "Expected path missing: $datasetRunPath"
    }
}

New-Item -ItemType Directory -Path $demoEvidenceRoot -Force | Out-Null
Write-DemoEvidenceIndex -OutputPath $evidenceIndexPath

Write-Host "Final demo evidence is ready."
Write-Host "Restart/replay artifacts: $(Join-Path $demoEvidenceRoot 'restart-replay')"
Write-Host "Review/dashboard artifacts: $(Join-Path $PWD 'artifacts\evidence\final-demo\review-dashboard')"
Write-Host "Dataset export summary: $datasetSummaryPath"
Write-Host "Dataset bundles: $(Join-Path $PWD 'artifacts\datasets\demo-high-energy'), $(Join-Path $PWD 'artifacts\datasets\demo-silent-oriented'), $(Join-Path $PWD 'artifacts\datasets\demo-validation-failure')"
Write-Host "Evidence index: $evidenceIndexPath"
