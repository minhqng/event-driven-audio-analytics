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

Write-Host "Starting Kafka for ingestion smoke..."
docker compose up --build -d kafka
Assert-LastExitCode "docker compose up kafka"

Write-Host "Bootstrapping Kafka topics..."
& (Resolve-Path "infra/kafka/create-topics.ps1")

Require-Topic "audio.metadata"
Require-Topic "audio.segment.ready"
Require-Topic "system.metrics"

Write-Host "Building ingestion image..."
docker compose build ingestion
Assert-LastExitCode "docker compose build ingestion"

Write-Host "Running ingestion preflight..."
docker compose run --rm --no-deps ingestion preflight
Assert-LastExitCode "docker compose run ingestion preflight"

Write-Host "Running ingestion service in Compose..."
docker compose up --no-deps ingestion
Assert-LastExitCode "docker compose up ingestion"

Write-Host "Observing Kafka messages for debugging only..."
$metadataMessages = & (Resolve-Path "scripts/smoke/observe-topic.ps1") audio.metadata 2
$segmentMessages = & (Resolve-Path "scripts/smoke/observe-topic.ps1") audio.segment.ready 3
$metricMessages = & (Resolve-Path "scripts/smoke/observe-topic.ps1") system.metrics 4

$metadataMessages
$segmentMessages
$metricMessages

Write-Host "Verifying exact current-run Kafka payloads against the configured input selection..."
$verificationSummary = docker compose run --rm --no-deps --entrypoint python ingestion -m event_driven_audio_analytics.smoke.verify_ingestion_flow
Assert-LastExitCode "docker compose run verify_ingestion_flow"
$verificationSummary

Write-Host "Checking structured ingestion logs..."
$ingestionLogs = docker compose logs ingestion
Assert-LastExitCode "docker compose logs ingestion"
$ingestionLogs

$expectsSuccessLogs = $verificationSummary -match '"validated_track_ids":\[[^\]]*[0-9]'
if ($expectsSuccessLogs) {
    $successLog = @($ingestionLogs | Where-Object {
        $_ -match 'Published track events' -and $_ -match ('"trace_id":"run/' + [regex]::Escape($effectiveRunId) + '/track/[0-9]+"') -and $_ -match '"track_id":[0-9]+'
    })
    if ($successLog.Count -lt 1) {
        throw "Expected a success log line with current-run trace_id and track_id context."
    }
}

$expectsRejectLogs = $verificationSummary -match '"rejected_track_ids":\[[^\]]*[0-9]'
if ($expectsRejectLogs) {
    $rejectLog = @($ingestionLogs | Where-Object {
        $_ -match 'Published metadata only for rejected track' -and $_ -match ('"trace_id":"run/' + [regex]::Escape($effectiveRunId) + '/track/[0-9]+"') -and $_ -match '"validation_status":"'
    })
    if ($rejectLog.Count -lt 1) {
        throw "Expected a reject log line with current-run trace_id and validation_status context."
    }
}

Write-Host "Ingestion smoke flow passed."
