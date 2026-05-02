Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot "../.."))

$requiredPaths = @(
    "README.md",
    "docs/README.md",
    "docs/architecture/system-overview.md",
    "docs/runbooks/demo.md",
    "docs/runbooks/validation.md",
    "artifacts/README.md",
    "data/README.md",
    "docker-compose.yml",
    "pyproject.toml",
    "infra/kafka/create-topics.sh",
    "infra/kafka/create-topics.ps1",
    "infra/sql/002_core_tables.sql",
    "scripts/smoke/check-writer-flow.ps1",
    "scripts/smoke/check-minio-claim-check-flow.sh",
    "scripts/smoke/check-minio-claim-check-flow.ps1",
    "scripts/smoke/check-processing-writer-flow.sh",
    "scripts/smoke/check-processing-writer-flow.ps1",
    "run-demo.ps1",
    "src/event_driven_audio_analytics/ingestion/app.py",
    "src/event_driven_audio_analytics/processing/app.py",
    "src/event_driven_audio_analytics/writer/app.py",
    "src/event_driven_audio_analytics/smoke/verify_writer_flow.py",
    "src/event_driven_audio_analytics/smoke/verify_minio_claim_check_flow.py"
)

foreach ($path in $requiredPaths) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing required path: $path"
    }
}

Write-Host "Tree sanity check passed."
