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

function Get-BrowserExecutable {
    $candidates = @(
        "msedge.exe",
        "msedge",
        "chrome.exe",
        "chrome"
    )

    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            return $command.Source
        }
    }

    $edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if (Test-Path $edgePath) {
        return $edgePath
    }

    $chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    if (Test-Path $chromePath) {
        return $chromePath
    }

    throw "No supported headless browser executable was found for Grafana screenshots."
}

function Capture-DashboardScreenshot {
    param(
        [string]$BrowserPath,
        [string]$Url,
        [string]$OutputPath
    )

    & $BrowserPath `
        "--headless=new" `
        "--disable-gpu" `
        "--hide-scrollbars" `
        "--window-size=1600,1400" `
        "--run-all-compositor-stages-before-draw" `
        "--virtual-time-budget=15000" `
        "--screenshot=$OutputPath" `
        $Url | Out-Null
    Assert-LastExitCode "Capturing screenshot for $Url"
}

function Invoke-DemoRun {
    param(
        [string]$RunId,
        [string]$TrackId,
        [string]$MetadataCsvPath,
        [string]$AudioRootPath
    )

    Write-Host "Running ingestion for $RunId (track_id=$TrackId)..."
    docker compose run --rm --no-deps `
        -e "RUN_ID=$RunId" `
        -e "METADATA_CSV_PATH=$MetadataCsvPath" `
        -e "AUDIO_ROOT_PATH=$AudioRootPath" `
        -e "TRACK_ID_ALLOWLIST=$TrackId" `
        -e "INGESTION_MAX_TRACKS=1" `
        ingestion
    Assert-LastExitCode "docker compose run ingestion for $RunId"
}

$grafanaPort = if ($env:GRAFANA_PORT) { $env:GRAFANA_PORT } else { "3000" }
$demoInputRootHost = Join-Path $PWD "artifacts\demo_inputs\week7"
$evidenceRootHost = Join-Path $PWD "artifacts\demo\week7"
$demoRunsHost = Join-Path $PWD "artifacts\runs"
$demoInputRootContainer = "/app/artifacts/demo_inputs/week7"
$metadataCsvContainer = "$demoInputRootContainer/metadata.csv"
$audioRootContainer = "$demoInputRootContainer/fma_small"

Write-Host "Validating docker compose config..."
docker compose config | Out-Null
Assert-LastExitCode "docker compose config"

Write-Host "Resetting local stack..."
docker compose down --remove-orphans
Assert-LastExitCode "docker compose down"

Write-Host "Cleaning previous Week 7 evidence..."
if (Test-Path $demoInputRootHost) {
    Remove-Item -LiteralPath $demoInputRootHost -Recurse -Force
}
if (Test-Path $evidenceRootHost) {
    Remove-Item -LiteralPath $evidenceRootHost -Recurse -Force
}
Get-ChildItem -Path $demoRunsHost -Directory -ErrorAction SilentlyContinue `
    | Where-Object { $_.Name -like "week7-*" } `
    | Remove-Item -Recurse -Force
New-Item -ItemType Directory -Path $evidenceRootHost -Force | Out-Null

Write-Host "Building ingestion, processing, and writer images..."
docker compose build ingestion processing writer
Assert-LastExitCode "docker compose build ingestion processing writer"

Write-Host "Preparing deterministic Week 7 demo inputs inside the ingestion image..."
docker compose run --rm --no-deps --entrypoint python `
    ingestion `
    -m event_driven_audio_analytics.smoke.prepare_week7_inputs `
    --output-root $demoInputRootContainer
Assert-LastExitCode "containerized prepare_week7_inputs"

Write-Host "Starting Kafka, TimescaleDB, and Grafana..."
docker compose up --build -d kafka timescaledb grafana
Assert-LastExitCode "docker compose up kafka timescaledb grafana"

Write-Host "Bootstrapping Kafka topics..."
& (Resolve-Path ".\infra\kafka\create-topics.ps1")

Write-Host "Starting processing and writer services..."
docker compose up -d --no-deps processing writer
Assert-LastExitCode "docker compose up processing writer"

Write-Host "Waiting for Grafana..."
Wait-HttpReady -Uri "http://localhost:$grafanaPort/api/health" -TimeoutSeconds 90

Invoke-DemoRun `
    -RunId "week7-high-energy" `
    -TrackId "910001" `
    -MetadataCsvPath $metadataCsvContainer `
    -AudioRootPath $audioRootContainer
Start-Sleep -Seconds 3

Invoke-DemoRun `
    -RunId "week7-silent-oriented" `
    -TrackId "910002" `
    -MetadataCsvPath $metadataCsvContainer `
    -AudioRootPath $audioRootContainer
Start-Sleep -Seconds 3

Invoke-DemoRun `
    -RunId "week7-validation-failure" `
    -TrackId "910003" `
    -MetadataCsvPath $metadataCsvContainer `
    -AudioRootPath $audioRootContainer

Write-Host "Verifying Week 7 dashboard data in TimescaleDB..."
$verificationSummary = docker compose exec -T writer python -m event_driven_audio_analytics.smoke.verify_dashboard_demo
Assert-LastExitCode "verify_dashboard_demo"
$verificationSummary | Set-Content -LiteralPath (Join-Path $evidenceRootHost "dashboard-demo-summary.json") -Encoding utf8

Write-Host "Checking provisioned dashboards through the Grafana API..."
$grafanaSearch = Invoke-RestMethod -Uri "http://localhost:$grafanaPort/api/search?query=Quality" -TimeoutSec 15
$audioDashboard = Invoke-RestMethod -Uri "http://localhost:$grafanaPort/api/dashboards/uid/audio-quality" -TimeoutSec 15
$systemDashboard = Invoke-RestMethod -Uri "http://localhost:$grafanaPort/api/dashboards/uid/system-health" -TimeoutSec 15

@{
    search = $grafanaSearch
    audio_quality_uid = $audioDashboard.dashboard.uid
    system_health_uid = $systemDashboard.dashboard.uid
} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $evidenceRootHost "grafana-api.json") -Encoding utf8

$browserPath = Get-BrowserExecutable
Write-Host "Capturing Grafana screenshots with $browserPath..."
Capture-DashboardScreenshot `
    -BrowserPath $browserPath `
    -Url "http://localhost:$grafanaPort/d/audio-quality/audio-quality?kiosk" `
    -OutputPath (Join-Path $evidenceRootHost "audio_quality.png")
Capture-DashboardScreenshot `
    -BrowserPath $browserPath `
    -Url "http://localhost:$grafanaPort/d/system-health/system-health?kiosk" `
    -OutputPath (Join-Path $evidenceRootHost "system_health.png")

Write-Host "Week 7 dashboard evidence is ready."
Write-Host "Summary: $evidenceRootHost\dashboard-demo-summary.json"
Write-Host "Grafana API snapshot: $evidenceRootHost\grafana-api.json"
Write-Host "Screenshots: $evidenceRootHost\audio_quality.png and $evidenceRootHost\system_health.png"
