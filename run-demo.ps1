Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Assert-LastExitCode {
    param(
        [string]$Context
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$Context failed with exit code $LASTEXITCODE."
    }
}

Write-Host "Starting event-driven-audio-analytics demo stack..."
docker compose up --build -d kafka timescaledb grafana
Assert-LastExitCode "docker compose up --build -d"

Write-Host "Creating Kafka topics..."
& ".\infra\kafka\create-topics.ps1"
Assert-LastExitCode "create-topics.ps1"

Write-Host "Starting processing and writer services..."
docker compose up -d --no-deps processing writer
Assert-LastExitCode "docker compose up -d processing writer"

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
Write-Host "Grafana auto-loads the file-provisioned TimescaleDB datasource and the Week 7 dashboards."
Write-Host "Run '.\\scripts\\demo\\generate-week7-dashboard-evidence.ps1' for the recommended Week 7.5 intermediate-demo path."
Write-Host "Run '.\\scripts\\demo\\run-repo-local-fma-burst.ps1' after placing 'tests\\fixtures\\audio\\tracks.csv' and 'tests\\fixtures\\audio\\fma_small\\...' for a bounded repo-local FMA-small burst."
Write-Host "See '.\\docs\\runbooks\\intermediate-demo.md' for the live demo sequence and panel interpretation."
