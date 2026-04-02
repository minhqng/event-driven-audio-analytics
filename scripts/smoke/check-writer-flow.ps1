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

function Wait-ForQuery {
    param(
        [string]$Sql,
        [string]$Expected
    )

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $result = docker compose exec -T timescaledb `
            psql -U "${env:POSTGRES_USER}" -d "${env:POSTGRES_DB}" -tAc $Sql
        Assert-LastExitCode "Query execution"

        if (($result | Out-String).Trim() -eq $Expected) {
            return
        }

        Start-Sleep -Seconds 2
    }

    docker compose logs writer --tail=200
    Assert-LastExitCode "Fetching writer logs"
    throw "Timed out waiting for query result. SQL: $Sql"
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

if (-not $env:POSTGRES_USER) {
    $env:POSTGRES_USER = "audio_analytics"
}
if (-not $env:POSTGRES_DB) {
    $env:POSTGRES_DB = "audio_analytics"
}

Write-Host "Resetting local stack..."
docker compose down --remove-orphans
Assert-LastExitCode "docker compose down"

Write-Host "Starting kafka and timescaledb..."
docker compose up --build -d kafka timescaledb
Assert-LastExitCode "docker compose up kafka timescaledb"

Write-Host "Bootstrapping Kafka topics..."
& (Resolve-Path "infra/kafka/create-topics.ps1")

Require-Topic "audio.metadata"
Require-Topic "audio.segment.ready"
Require-Topic "audio.features"
Require-Topic "system.metrics"
Require-Topic "audio.dlq"

Write-Host "Starting writer after topic bootstrap..."
docker compose up --build -d writer
Assert-LastExitCode "docker compose up writer"
Start-Sleep -Seconds 5

Write-Host "Publishing fake metadata and feature events..."
docker compose run --rm --entrypoint python writer -m event_driven_audio_analytics.smoke.publish_fake_events
Assert-LastExitCode "Publishing fake events"

Wait-ForQuery "SELECT COUNT(*) FROM track_metadata WHERE run_id = 'demo-run' AND track_id = 2;" "1"
Wait-ForQuery "SELECT COUNT(*) FROM audio_features WHERE run_id = 'demo-run' AND track_id = 2 AND segment_idx = 0;" "1"
Wait-ForQuery "SELECT COUNT(*) FROM run_checkpoints WHERE consumer_group = 'event-driven-audio-analytics-writer' AND topic_name IN ('audio.metadata', 'audio.features');" "2"

Write-Host "Replaying the same fake events to verify idempotent feature writes..."
docker compose run --rm --entrypoint python writer -m event_driven_audio_analytics.smoke.publish_fake_events
Assert-LastExitCode "Replaying fake events"

Wait-ForQuery "SELECT COUNT(*) FROM track_metadata WHERE run_id = 'demo-run' AND track_id = 2;" "1"
Wait-ForQuery "SELECT COUNT(*) FROM audio_features WHERE run_id = 'demo-run' AND track_id = 2 AND segment_idx = 0;" "1"

Write-Host "Writer smoke flow passed."
