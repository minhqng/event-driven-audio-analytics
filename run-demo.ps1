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

function Wait-HttpReady {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri $Uri -TimeoutSec 5
            if ($null -ne $response) {
                return
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }

    throw "Timed out waiting for HTTP readiness: $Uri"
}

function Wait-ReviewPreflight {
    param(
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        docker compose exec -T review python -m event_driven_audio_analytics.review.app preflight 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 2
    }

    throw "Timed out waiting for review preflight."
}

function Wait-ReviewViewReady {
    param(
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $postgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "audio_analytics" }
    $postgresDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "audio_analytics" }
    while ((Get-Date) -lt $deadline) {
        docker compose exec -T timescaledb `
            psql -U $postgresUser `
            -d $postgresDb `
            -c "SELECT 1 FROM vw_review_tracks LIMIT 1;" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 2
    }

    throw "Timed out waiting for vw_review_tracks to become selectable."
}

Write-Host "Starting event-driven-audio-analytics demo stack..."
docker compose up --build -d kafka timescaledb grafana
Assert-LastExitCode "docker compose up --build -d"

Write-Host "Creating Kafka topics..."
& ".\infra\kafka\create-topics.ps1"
Assert-LastExitCode "create-topics.ps1"

Write-Host "Starting processing, writer, and review services..."
docker compose up -d --no-deps processing writer review
Assert-LastExitCode "docker compose up -d processing writer review"

$grafanaPort = if ($env:GRAFANA_PORT) { $env:GRAFANA_PORT } else { "3000" }
$reviewPort = if ($env:REVIEW_PORT) { $env:REVIEW_PORT } else { "8080" }
$timescalePort = if ($env:TIMESCALEDB_PORT) { $env:TIMESCALEDB_PORT } else { "5432" }
$kafkaHostPort = if ($env:KAFKA_BROKER_PORT) { $env:KAFKA_BROKER_PORT } else { "9092" }
$kafkaInternal = if ($env:KAFKA_BOOTSTRAP_SERVERS) { $env:KAFKA_BOOTSTRAP_SERVERS } else { "kafka:29092" }

Write-Host "Waiting for the review console..."
Wait-HttpReady -Uri "http://localhost:$reviewPort/healthz" -TimeoutSeconds 90
Write-Host "Running review preflight..."
Wait-ReviewPreflight -TimeoutSeconds 90
Write-Host "Checking vw_review_tracks..."
Wait-ReviewViewReady -TimeoutSeconds 60

Write-Host "Demo bootstrap completed."
Write-Host "Grafana: http://localhost:$grafanaPort"
Write-Host "Run Review Console: http://localhost:$reviewPort"
Write-Host "TimescaleDB: localhost:$timescalePort"
Write-Host "Kafka bootstrap (host): localhost:$kafkaHostPort"
Write-Host "Kafka bootstrap (containers): $kafkaInternal"
Write-Host "Application code executes inside Linux containers; the host only orchestrates Docker Compose."
Write-Host "Grafana auto-loads the file-provisioned TimescaleDB datasource and the dashboard JSON."
Write-Host "The review service is read-only and serves run/track/segment inspection from persisted DB rows plus claim-check artifacts."
Write-Host "Run '.\\scripts\\demo\\generate-dashboard-evidence.ps1' for the dashboard demo path."
Write-Host "Run '.\\scripts\\demo\\generate-demo-evidence.ps1' for the full final evidence bundle."
Write-Host "Run '.\\scripts\\demo\\run-local-fma-burst.ps1' after placing 'tests\\fixtures\\audio\\tracks.csv' and 'tests\\fixtures\\audio\\fma_small\\...' for a bounded repo-local FMA-small burst."
Write-Host "See '.\\docs\\runbooks\\dashboard-demo.md' for the live dashboard sequence and panel interpretation."
Write-Host "Run '.\\scripts\\smoke\\check-ingestion-flow.ps1' for the broker-backed ingestion smoke path."
Write-Host "Run '.\\scripts\\smoke\\check-processing-flow.ps1' for the broker-backed processing smoke path."
Write-Host "Run '.\\scripts\\smoke\\check-processing-writer-flow.ps1' for the broker-backed persistence smoke path."
Write-Host "Run '.\\scripts\\smoke\\check-pytest.ps1' for the official containerized pytest path."
