Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot "../.."))

$requiredPaths = @(
    "README.md",
    "docker-compose.yml",
    "pyproject.toml",
    "infra/kafka/create-topics.sh",
    "infra/kafka/create-topics.ps1",
    "infra/sql/002_core_tables.sql",
    "scripts/smoke/check-writer-flow.sh",
    "run-demo.ps1",
    "src/event_driven_audio_analytics/smoke/publish_fake_events.py",
    "src/event_driven_audio_analytics/ingestion/app.py",
    "src/event_driven_audio_analytics/processing/app.py",
    "src/event_driven_audio_analytics/writer/app.py"
)

foreach ($path in $requiredPaths) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing required path: $path"
    }
}

Write-Host "Tree sanity check passed."
