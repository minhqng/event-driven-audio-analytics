Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-LastExitCode {
    param(
        [string]$Context
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$Context failed with exit code $LASTEXITCODE."
    }
}

Write-Host "Starting event-driven-audio-analytics demo stack..."
docker compose up --build -d
Assert-LastExitCode "docker compose up --build -d"

Write-Host "Creating Kafka topics..."
& ".\infra\kafka\create-topics.ps1"

$grafanaPort = if ($env:GRAFANA_PORT) { $env:GRAFANA_PORT } else { "3000" }
$timescalePort = if ($env:TIMESCALEDB_PORT) { $env:TIMESCALEDB_PORT } else { "5432" }
$kafkaHostPort = if ($env:KAFKA_BROKER_PORT) { $env:KAFKA_BROKER_PORT } else { "9092" }
$kafkaInternal = if ($env:KAFKA_BOOTSTRAP_SERVERS) { $env:KAFKA_BOOTSTRAP_SERVERS } else { "kafka:29092" }

Write-Host "Demo bootstrap completed."
Write-Host "Grafana: http://localhost:$grafanaPort"
Write-Host "TimescaleDB: localhost:$timescalePort"
Write-Host "Kafka bootstrap (host): localhost:$kafkaHostPort"
Write-Host "Kafka bootstrap (containers): $kafkaInternal"
Write-Host "Application code executes inside Linux containers; the host only orchestrates Docker Compose."
Write-Host "Scaffold services currently emit startup logs and exit 0 until continuous runtime loops are implemented."
