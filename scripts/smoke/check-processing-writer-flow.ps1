Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot "../.."))
$effectiveRunId = if ($env:RUN_ID) { $env:RUN_ID } else { "demo-run" }

function Assert-LastExitCode {
    param(
        [string]$Context
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$Context failed with exit code $LASTEXITCODE."
    }
}

$cleanupRunArtifactsScript = @'
import os
import shutil
from pathlib import Path
from event_driven_audio_analytics.shared.storage import validate_run_id

run_id = validate_run_id(os.environ["CLEANUP_RUN_ID"])
root = Path("/app/artifacts/runs").resolve()
target = (root / run_id).resolve()
target.relative_to(root)
shutil.rmtree(target, ignore_errors=True)
'@

function Clear-RunArtifactsInContainer {
    param(
        [string]$RunId
    )

    docker compose run --rm --no-deps -e "CLEANUP_RUN_ID=$RunId" --entrypoint python ingestion -c $cleanupRunArtifactsScript | Out-Null
    Assert-LastExitCode "docker compose run cleanup artifacts"
}

function Require-Topic {
    param(
        [string]$TopicName
    )

    $bootstrapServer = if ($env:KAFKA_BOOTSTRAP_SERVERS) {
        $env:KAFKA_BOOTSTRAP_SERVERS
    } else {
        "kafka:29092"
    }

    $topics = docker compose exec -T kafka /opt/bitnami/kafka/bin/kafka-topics.sh `
        --bootstrap-server $bootstrapServer `
        --list
    Assert-LastExitCode "Listing Kafka topics"

    if (-not (($topics -split "\r?\n") -contains $TopicName)) {
        throw "Missing expected Kafka topic: $TopicName"
    }
}

Write-Host "Resetting local stack..."
docker compose down --remove-orphans
Assert-LastExitCode "docker compose down"

Write-Host "Cleaning prior run artifacts..."
Clear-RunArtifactsInContainer -RunId $effectiveRunId

Write-Host "Starting Kafka and TimescaleDB for processing->writer smoke..."
docker compose up --build -d kafka timescaledb
Assert-LastExitCode "docker compose up kafka timescaledb"

Write-Host "Bootstrapping Kafka topics..."
& (Resolve-Path "infra/kafka/create-topics.ps1")

Require-Topic "audio.metadata"
Require-Topic "audio.segment.ready"
Require-Topic "audio.features"
Require-Topic "system.metrics"

Write-Host "Building ingestion, processing, writer, and pytest images..."
docker compose build ingestion processing writer pytest
Assert-LastExitCode "docker compose build ingestion processing writer pytest"

Write-Host "Running writer preflight..."
docker compose run --rm --no-deps writer preflight
Assert-LastExitCode "docker compose run writer preflight"

Write-Host "Running processing preflight..."
docker compose run --rm --no-deps processing preflight
Assert-LastExitCode "docker compose run processing preflight"

Write-Host "Running ingestion preflight..."
docker compose run --rm --no-deps ingestion preflight
Assert-LastExitCode "docker compose run ingestion preflight"

Write-Host "Starting processing and writer services in Compose..."
docker compose up -d --no-deps processing writer
Assert-LastExitCode "docker compose up processing writer"
Start-Sleep -Seconds 5

$runningServices = docker compose ps --services --status running
Assert-LastExitCode "docker compose ps running"
if (-not (($runningServices -split "\r?\n") -contains "processing")) {
    docker compose logs processing
    Assert-LastExitCode "docker compose logs processing"
    throw "Processing service is not running after startup."
}
if (-not (($runningServices -split "\r?\n") -contains "writer")) {
    docker compose logs writer
    Assert-LastExitCode "docker compose logs writer"
    throw "Writer service is not running after startup."
}

Write-Host "Running ingestion one-shot to feed Kafka..."
docker compose run --rm --no-deps ingestion
Assert-LastExitCode "docker compose run ingestion"

Write-Host "Verifying current-run TimescaleDB outputs..."
$verificationSummary = docker compose run --rm --no-deps -e "RUN_ID=$effectiveRunId" --entrypoint python pytest -m event_driven_audio_analytics.smoke.verify_writer_flow
Assert-LastExitCode "docker compose run verify_writer_flow"
$verificationSummary

Write-Host "Checking structured logs..."
$processingLogs = docker compose logs processing
Assert-LastExitCode "docker compose logs processing"
$writerLogs = docker compose logs writer
Assert-LastExitCode "docker compose logs writer"
$processingLogs
$writerLogs

$runningServices = docker compose ps --services --status running
Assert-LastExitCode "docker compose ps running after flow"
if (-not (($runningServices -split "\r?\n") -contains "processing")) {
    throw "Processing service is no longer running after the smoke flow."
}
if (-not (($runningServices -split "\r?\n") -contains "writer")) {
    throw "Writer service is no longer running after the smoke flow."
}

if (@($processingLogs | Where-Object { $_ -match 'Processing failed' }).Count -gt 0) {
    throw "Unexpected processing failure logs appeared during the healthy smoke path."
}
if (@($writerLogs | Where-Object { $_ -match 'Writer failed' }).Count -gt 0) {
    throw "Unexpected writer failure logs appeared during the healthy smoke path."
}

$expectsWriterLogs = $verificationSummary -match '"metadata_count":[1-9][0-9]*'
if ($expectsWriterLogs) {
    $successLog = @($writerLogs | Where-Object {
        $_ -match 'Persisted writer outputs' -and `
        $_ -match ('"trace_id":"run/' + [regex]::Escape($effectiveRunId) + '/track/[0-9]+"')
    })
    if ($successLog.Count -lt 1) {
        throw "Expected a writer success log line with a current-run track trace_id."
    }
}

Write-Host "Processing -> writer smoke flow passed."
