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

$bootstrapServer = if ($env:KAFKA_BOOTSTRAP_SERVERS) {
    $env:KAFKA_BOOTSTRAP_SERVERS
} else {
    "kafka:29092"
}

$kafkaTopics = "/opt/bitnami/kafka/bin/kafka-topics.sh"

function Wait-ForKafkaBroker {
    $attempt = 0

    while ($true) {
        docker compose exec -T kafka $kafkaTopics --bootstrap-server $bootstrapServer --list | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return
        }

        $attempt += 1
        if ($attempt -ge 30) {
            throw "Kafka broker did not become ready in time."
        }

        Start-Sleep -Seconds 2
    }
}

$topics = @(
    "audio.metadata",
    "audio.segment.ready",
    "audio.features",
    "system.metrics",
    "audio.dlq"
)

Wait-ForKafkaBroker

foreach ($topic in $topics) {
    Write-Host "Ensuring topic $topic..."
    docker compose exec -T kafka $kafkaTopics `
        --bootstrap-server $bootstrapServer `
        --create `
        --if-not-exists `
        --topic $topic `
        --partitions 1 `
        --replication-factor 1
    Assert-LastExitCode "Ensuring topic $topic"
}

Write-Host "Current Kafka topics:"
docker compose exec -T kafka $kafkaTopics --bootstrap-server $bootstrapServer --list
Assert-LastExitCode "Listing Kafka topics"

Write-Host "Kafka topics ensured."
