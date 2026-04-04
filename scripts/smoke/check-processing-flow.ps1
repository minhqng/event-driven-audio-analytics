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
docker compose run --rm --no-deps --entrypoint sh ingestion -c "rm -rf /app/artifacts/runs/$effectiveRunId" | Out-Null
Assert-LastExitCode "docker compose run cleanup artifacts"

Write-Host "Starting Kafka for processing smoke..."
docker compose up --build -d kafka
Assert-LastExitCode "docker compose up kafka"

Write-Host "Bootstrapping Kafka topics..."
& (Resolve-Path "infra/kafka/create-topics.ps1")

Require-Topic "audio.metadata"
Require-Topic "audio.segment.ready"
Require-Topic "audio.features"
Require-Topic "system.metrics"

Write-Host "Building ingestion and processing images..."
docker compose build ingestion processing
Assert-LastExitCode "docker compose build ingestion processing"

Write-Host "Running processing preflight..."
docker compose run --rm --no-deps processing preflight
Assert-LastExitCode "docker compose run processing preflight"

Write-Host "Running ingestion preflight..."
docker compose run --rm --no-deps ingestion preflight
Assert-LastExitCode "docker compose run ingestion preflight"

Write-Host "Starting processing service in Compose..."
docker compose up -d --no-deps processing
Assert-LastExitCode "docker compose up processing"
Start-Sleep -Seconds 5

$runningServices = docker compose ps --services --status running
Assert-LastExitCode "docker compose ps running"
if (-not (($runningServices -split "\r?\n") -contains "processing")) {
    docker compose logs processing
    Assert-LastExitCode "docker compose logs processing"
    throw "Processing service is not running after startup."
}

Write-Host "Running ingestion one-shot to feed Kafka..."
docker compose run --rm --no-deps ingestion
Assert-LastExitCode "docker compose run ingestion"

Write-Host "Observing Kafka messages for debugging only..."
$featureMessages = & (Resolve-Path "scripts/smoke/observe-topic.ps1") audio.features 10
$metricMessages = & (Resolve-Path "scripts/smoke/observe-topic.ps1") system.metrics 12

$featureMessages
$metricMessages

Write-Host "Verifying current-run processing outputs against the configured input selection..."
$verificationSummary = docker compose run --rm --no-deps --entrypoint python processing -m event_driven_audio_analytics.smoke.verify_processing_flow
Assert-LastExitCode "docker compose run verify_processing_flow"
$verificationSummary

Write-Host "Checking structured processing logs..."
$processingLogs = docker compose logs processing
Assert-LastExitCode "docker compose logs processing"
$processingLogs

$runningServices = docker compose ps --services --status running
Assert-LastExitCode "docker compose ps running after flow"
if (-not (($runningServices -split "\r?\n") -contains "processing")) {
    throw "Processing service is no longer running after the smoke flow."
}

if (@($processingLogs | Where-Object { $_ -match 'Processing failed' }).Count -gt 0) {
    throw "Unexpected processing failure logs appeared during the healthy smoke path."
}

$expectsFeatureLogs = $verificationSummary -match '"expected_segment_count":[1-9][0-9]*'
if ($expectsFeatureLogs) {
    $successLog = @($processingLogs | Where-Object {
        $_ -match 'Published processing outputs' -and `
        $_ -match ('"trace_id":"run/' + [regex]::Escape($effectiveRunId) + '/track/[0-9]+"') -and `
        $_ -match '"track_id":[0-9]+' -and `
        $_ -match '"segment_idx":[0-9]+' -and `
        $_ -match '"silent_flag":'
    })
    if ($successLog.Count -lt 1) {
        throw "Expected a success log line with current-run trace_id, track_id, segment_idx, and silent_flag context."
    }
}

Write-Host "Processing smoke flow passed."
