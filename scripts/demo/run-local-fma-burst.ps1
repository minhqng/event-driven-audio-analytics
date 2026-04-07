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

function Require-Path {
    param(
        [string]$Path,
        [string]$Label,
        [ValidateSet("File", "Directory")]
        [string]$Kind
    )

    if ($Kind -eq "File" -and -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label is missing. Expected repo-local path: $Path"
    }
    if ($Kind -eq "Directory" -and -not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Label is missing. Expected repo-local path: $Path"
    }
}

$metadataCsvHost = Join-Path $PWD "tests\fixtures\audio\tracks.csv"
$audioRootHost = Join-Path $PWD "tests\fixtures\audio\fma_small"
$metadataCsvContainer = "/app/tests/fixtures/audio/tracks.csv"
$audioRootContainer = "/app/tests/fixtures/audio/fma_small"
$runId = if ($env:RUN_ID) { $env:RUN_ID } else { "fma-small-live" }
$maxTracks = if ($env:INGESTION_MAX_TRACKS) { $env:INGESTION_MAX_TRACKS } else { "100" }
$trackIdAllowlist = if (Test-Path env:TRACK_ID_ALLOWLIST) { $env:TRACK_ID_ALLOWLIST } else { "" }

Require-Path -Path $metadataCsvHost -Label "Repo-local FMA metadata CSV" -Kind File
Require-Path -Path $audioRootHost -Label "Repo-local FMA audio root" -Kind Directory

Write-Host "Validating docker compose config..."
docker compose config | Out-Null
Assert-LastExitCode "docker compose config"

Write-Host "Verifying live stack services..."
$runningServices = docker compose ps --services --status running
Assert-LastExitCode "docker compose ps"
$requiredServices = @("kafka", "timescaledb", "grafana", "processing", "writer")
foreach ($service in $requiredServices) {
    if (-not (($runningServices -split "\r?\n") -contains $service)) {
        throw "Required service '$service' is not running. Start the stack with '.\run-demo.ps1' first."
    }
}

Write-Host "Ensuring Kafka topics exist..."
& ".\infra\kafka\create-topics.ps1"
Assert-LastExitCode "create-topics.ps1"

Write-Host "Cleaning prior artifacts for run_id=$runId..."
docker compose run --rm --no-deps --entrypoint sh ingestion -c "rm -rf /app/artifacts/runs/$runId" | Out-Null
Assert-LastExitCode "docker compose run cleanup artifacts"

Write-Host "Running repo-local FMA burst run_id=$runId max_tracks=$maxTracks..."
docker compose run --rm --no-deps `
    -e "RUN_ID=$runId" `
    -e "METADATA_CSV_PATH=$metadataCsvContainer" `
    -e "AUDIO_ROOT_PATH=$audioRootContainer" `
    -e "TRACK_ID_ALLOWLIST=$trackIdAllowlist" `
    -e "INGESTION_MAX_TRACKS=$maxTracks" `
    ingestion
Assert-LastExitCode "docker compose run ingestion"

Write-Host "Repo-local FMA burst completed."
Write-Host "Recommended dashboard URLs:"
Write-Host "  http://localhost:3000/d/audio-quality/audio-quality?from=now-15m&to=now"
Write-Host "  http://localhost:3000/d/system-health/system-health?from=now-15m&to=now"
