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

function Get-MatchingCount {
    param(
        [string[]]$Lines,
        [string]$Pattern
    )

    return @($Lines | Where-Object { $_ -match $Pattern }).Count
}

Write-Host "Resetting local stack..."
docker compose down --remove-orphans
Assert-LastExitCode "docker compose down"

Write-Host "Starting Kafka for ingestion smoke..."
docker compose up --build -d kafka
Assert-LastExitCode "docker compose up kafka"

Write-Host "Bootstrapping Kafka topics..."
& (Resolve-Path "infra/kafka/create-topics.ps1")

Require-Topic "audio.metadata"
Require-Topic "audio.segment.ready"
Require-Topic "system.metrics"

Write-Host "Running ingestion service in Compose..."
docker compose up --build --no-deps ingestion
Assert-LastExitCode "docker compose up ingestion"

Write-Host "Observing Kafka messages..."
$metadataMessages = & (Resolve-Path "scripts/smoke/observe-topic.ps1") audio.metadata 2
$segmentMessages = & (Resolve-Path "scripts/smoke/observe-topic.ps1") audio.segment.ready 3
$metricMessages = & (Resolve-Path "scripts/smoke/observe-topic.ps1") system.metrics 4

$metadataMessages
$segmentMessages
$metricMessages

$metadataCount = Get-MatchingCount -Lines $metadataMessages -Pattern '^[0-9][0-9]*\|'
$segmentCount = Get-MatchingCount -Lines $segmentMessages -Pattern '^2\|'
$metricCount = Get-MatchingCount -Lines $metricMessages -Pattern '^ingestion\|'

if ($metadataCount -lt 2) {
    throw "Expected at least 2 audio.metadata messages with track_id keys."
}

if ($segmentCount -lt 1) {
    throw "Expected at least 1 audio.segment.ready message keyed by track_id=2."
}

if ($metricCount -lt 4) {
    throw "Expected 4 system.metrics messages keyed by service_name=ingestion."
}

Write-Host "Ingestion smoke flow passed."
