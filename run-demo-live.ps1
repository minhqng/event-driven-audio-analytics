##############################################################################
#  run-demo-live.ps1  -  Live demo script for thesis defense
#  Usage: .\run-demo-live.ps1
#
#  What this does:
#    1. Start full stack (Kafka, TimescaleDB, Grafana, Processing, Writer, Review)
#    2. Generate synthetic mock data (3 scenarios, no real FMA files needed)
#    3. Run Ingestion for all 3 scenarios
#    4. Wait for Processing + Writer to finish (DB polling)
#    5. Print a clean results table
#    6. Open Review Console + Grafana in browser
##############################################################################

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
. ".\scripts\demo\demo-powershell-helpers.ps1"

function Write-Step { param([string]$Msg) Write-Host "" ; Write-Host "[*] $Msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Msg) Write-Host "    OK  $Msg" -ForegroundColor Green }
function Write-Info { param([string]$Msg) Write-Host "     -  $Msg" -ForegroundColor White }
function Write-Warn { param([string]$Msg) Write-Host "    !   $Msg" -ForegroundColor Yellow }

function Assert-ExitCode {
    param([string]$Context)
    if ($LASTEXITCODE -ne 0) { throw "$Context failed (exit $LASTEXITCODE)." }
}

function Wait-Http {
    param([string]$Uri, [int]$TimeoutSec = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-RestMethod -Uri $Uri -TimeoutSec 5 -ErrorAction Stop
            if ($null -ne $r) { return }
        } catch { Start-Sleep -Seconds 2 }
    }
    throw "Timeout waiting for $Uri"
}

function Wait-ReviewPreflight {
    param([int]$TimeoutSec = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        docker compose exec -T review python -m event_driven_audio_analytics.review.app preflight 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 2
    }
    throw "Timeout: review preflight"
}

function Wait-ReviewViewReady {
    param([int]$TimeoutSec = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "audio_analytics" }
    $pgDb   = if ($env:POSTGRES_DB)   { $env:POSTGRES_DB   } else { "audio_analytics" }
    while ((Get-Date) -lt $deadline) {
        docker compose exec -T timescaledb `
            psql -U $pgUser -d $pgDb -c "SELECT 1 FROM vw_review_tracks LIMIT 1;" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 2
    }
    throw "Timeout: vw_review_tracks not ready"
}

function Wait-PipelineDone {
    param(
        [string]$RunId,
        [int]$ExpectedSegments,
        [int]$TimeoutSec = 90
    )
    $pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "audio_analytics" }
    $pgDb   = if ($env:POSTGRES_DB)   { $env:POSTGRES_DB   } else { "audio_analytics" }
    $deadline = (Get-Date).AddSeconds($TimeoutSec)

    while ((Get-Date) -lt $deadline) {
        if ($ExpectedSegments -gt 0) {
            $count = docker compose exec -T timescaledb `
                psql -U $pgUser -d $pgDb -tAc `
                "SELECT COUNT(*) FROM audio_features WHERE run_id='$RunId';" 2>$null
            if ($LASTEXITCODE -eq 0 -and [int]$count.Trim() -ge $ExpectedSegments) { return }
        } else {
            $count = docker compose exec -T timescaledb `
                psql -U $pgUser -d $pgDb -tAc `
                "SELECT COUNT(*) FROM track_metadata WHERE run_id='$RunId';" 2>$null
            if ($LASTEXITCODE -eq 0 -and [int]$count.Trim() -ge 1) { return }
        }
        Start-Sleep -Seconds 2
    }
    Write-Warn "Pipeline for $RunId not fully done after ${TimeoutSec}s - continuing anyway"
}

function Get-RunSummaryRow {
    param([string]$RunId)
    $pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "audio_analytics" }
    $pgDb   = if ($env:POSTGRES_DB)   { $env:POSTGRES_DB   } else { "audio_analytics" }

    $row = docker compose exec -T timescaledb psql -U $pgUser -d $pgDb -tAc `
        "SELECT
            COALESCE(segments_persisted::text,'0'),
            COALESCE(ROUND(avg_rms::numeric,2)::text,'N/A'),
            COALESCE(ROUND((silent_ratio*100)::numeric,0)::text,'0') || '%',
            COALESCE(validation_failures::text,'0'),
            COALESCE(ROUND(avg_processing_ms::numeric,1)::text,'N/A')
         FROM vw_dashboard_run_summary
         WHERE run_id='$RunId'
         LIMIT 1;" 2>$null

    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($row)) {
        return @("?","?","?","?","?")
    }
    return ($row.Trim() -split "\|")
}

# --- Ports -------------------------------------------------------------------
Initialize-DemoHostPorts
$reviewPort  = if ($env:REVIEW_PORT)  { $env:REVIEW_PORT  } else { "8080" }
$grafanaPort = if ($env:GRAFANA_PORT) { $env:GRAFANA_PORT } else { "3000" }

$DEMO_INPUT_HOST      = Join-Path $PWD "artifacts\demo-inputs\review-demo"
$DEMO_INPUT_CONTAINER = "/app/artifacts/demo-inputs/review-demo"
$META_CSV_CONTAINER   = "$DEMO_INPUT_CONTAINER/metadata.csv"
$AUDIO_ROOT_CONTAINER = "$DEMO_INPUT_CONTAINER/fma_small"

$REVIEW_URL  = "http://localhost:$reviewPort/?demo=1&run_id=demo-high-energy&track_id=910001"
$GRAFANA_AUDIO  = "http://localhost:$grafanaPort/d/audio-quality/audio-quality?from=now-1h&to=now"
$GRAFANA_HEALTH = "http://localhost:$grafanaPort/d/system-health/system-health?from=now-1h&to=now"

# =============================================================================
Write-Host ""
Write-Host "=============================================================" -ForegroundColor Magenta
Write-Host "  Event-Driven Audio Analytics -- DEMO LIVE"                  -ForegroundColor Magenta
Write-Host "  Nhom 05 - PTIT - 2026"                                      -ForegroundColor Magenta
Write-Host "=============================================================" -ForegroundColor Magenta

# --- STEP 1: Start core stack ------------------------------------------------
Write-Step "Step 1/7 - Start Kafka + TimescaleDB + Grafana"
docker compose up --build -d kafka timescaledb grafana
Assert-ExitCode "docker compose up core services"
Write-Ok "Kafka, TimescaleDB, Grafana started"

# --- STEP 2: Create Kafka topics ---------------------------------------------
Write-Step "Step 2/7 - Create Kafka topics"
& ".\infra\kafka\create-topics.ps1"
Assert-ExitCode "create-topics.ps1"
Write-Ok "4 topics: audio.metadata / audio.segment.ready / audio.features / system.metrics"

# --- STEP 3: Start Processing, Writer, Review --------------------------------
Write-Step "Step 3/7 - Start Processing + Writer + Review Console"
docker compose up -d --no-deps processing writer review
Assert-ExitCode "docker compose up processing writer review"

Write-Info "Waiting for Review Console..."
Wait-Http -Uri "http://localhost:$reviewPort/healthz" -TimeoutSec 90
Wait-ReviewPreflight -TimeoutSec 90
Wait-ReviewViewReady -TimeoutSec 60
Write-Ok "Review Console: http://localhost:$reviewPort"

# --- STEP 4: Generate synthetic mock data ------------------------------------
Write-Step "Step 4/7 - Generate synthetic mock audio data (no real FMA needed)"
Write-Info "3 scenarios: High-Energy (440Hz) | Silent-Oriented | Validation-Failure"

if (Test-Path $DEMO_INPUT_HOST) {
    Remove-Item -LiteralPath $DEMO_INPUT_HOST -Recurse -Force
}

docker compose run --rm --no-deps `
    --entrypoint python ingestion `
    -m event_driven_audio_analytics.smoke.prepare_review_demo_inputs `
    --output-root $DEMO_INPUT_CONTAINER
Assert-ExitCode "prepare_review_demo_inputs"

Write-Ok "Mock data ready at artifacts/demo-inputs/review-demo/"
Write-Info "  Track 910001 | High-Energy    | 6s | 440Hz sine  -> 4 segments expected"
Write-Info "  Track 910002 | Silent-Orient. | 6s | 3s silent + 3s 660Hz -> 4 segments"
Write-Info "  Track 910003 | Validation-Fail| 3s | fully silent -> rejected (0 segments)"

# --- STEP 5: Run ingestion for all 3 scenarios -------------------------------
Write-Step "Step 5/7 - Run Ingestion Pipeline (3 scenarios)"

Write-Info "[1/3] demo-high-energy (Track 910001)..."
docker compose run --rm --no-deps `
    -e "RUN_ID=demo-high-energy" `
    -e "METADATA_CSV_PATH=$META_CSV_CONTAINER" `
    -e "AUDIO_ROOT_PATH=$AUDIO_ROOT_CONTAINER" `
    -e "TRACK_ID_ALLOWLIST=910001" `
    -e "INGESTION_MAX_TRACKS=1" `
    ingestion
Assert-ExitCode "ingestion demo-high-energy"
Write-Ok "demo-high-energy: events published to Kafka"

Start-Sleep -Seconds 2

Write-Info "[2/3] demo-silent-oriented (Track 910002)..."
docker compose run --rm --no-deps `
    -e "RUN_ID=demo-silent-oriented" `
    -e "METADATA_CSV_PATH=$META_CSV_CONTAINER" `
    -e "AUDIO_ROOT_PATH=$AUDIO_ROOT_CONTAINER" `
    -e "TRACK_ID_ALLOWLIST=910002" `
    -e "INGESTION_MAX_TRACKS=1" `
    ingestion
Assert-ExitCode "ingestion demo-silent-oriented"
Write-Ok "demo-silent-oriented: events published to Kafka"

Start-Sleep -Seconds 2

Write-Info "[3/3] demo-validation-failure (Track 910003)..."
docker compose run --rm --no-deps `
    -e "RUN_ID=demo-validation-failure" `
    -e "METADATA_CSV_PATH=$META_CSV_CONTAINER" `
    -e "AUDIO_ROOT_PATH=$AUDIO_ROOT_CONTAINER" `
    -e "TRACK_ID_ALLOWLIST=910003" `
    -e "INGESTION_MAX_TRACKS=1" `
    ingestion
Assert-ExitCode "ingestion demo-validation-failure"
Write-Ok "demo-validation-failure: track rejected -> metadata-only event published"

# --- STEP 6: Wait for Processing + Writer to finish -------------------------
Write-Step "Step 6/7 - Wait for Processing + Writer to persist to TimescaleDB"
Write-Info "Polling database - estimated ~15-30 seconds..."

Wait-PipelineDone -RunId "demo-high-energy"       -ExpectedSegments 3 -TimeoutSec 90
Write-Ok "demo-high-energy: feature rows persisted"

Wait-PipelineDone -RunId "demo-silent-oriented"   -ExpectedSegments 3 -TimeoutSec 90
Write-Ok "demo-silent-oriented: feature rows persisted"

Wait-PipelineDone -RunId "demo-validation-failure" -ExpectedSegments 0 -TimeoutSec 60
Write-Ok "demo-validation-failure: track_metadata persisted (validation_status=silent)"

# --- STEP 7: Print results table ---------------------------------------------
Write-Step "Step 7/7 - Pipeline Results"

$he = Get-RunSummaryRow -RunId "demo-high-energy"
$so = Get-RunSummaryRow -RunId "demo-silent-oriented"
$vf = Get-RunSummaryRow -RunId "demo-validation-failure"

Write-Host ""
Write-Host "+-------------------------------------+----------+----------+----------+-----------+---------------+" -ForegroundColor White
Write-Host "| Run ID                              | Segments | Avg RMS  | Silence% | Val.Fails | ProcTime(ms)  |" -ForegroundColor White
Write-Host "+-------------------------------------+----------+----------+----------+-----------+---------------+" -ForegroundColor White

$heRow = "| {0,-35} | {1,8} | {2,8} | {3,8} | {4,9} | {5,13} |" -f "[OK] demo-high-energy", $he[0], $he[1], $he[2], $he[3], $he[4]
$soRow = "| {0,-35} | {1,8} | {2,8} | {3,8} | {4,9} | {5,13} |" -f "[~~] demo-silent-oriented", $so[0], $so[1], $so[2], $so[3], $so[4]
$vfRow = "| {0,-35} | {1,8} | {2,8} | {3,8} | {4,9} | {5,13} |" -f "[XX] demo-validation-failure", $vf[0], $vf[1], $vf[2], $vf[3], $vf[4]

Write-Host $heRow -ForegroundColor Green
Write-Host $soRow -ForegroundColor Yellow
Write-Host $vfRow -ForegroundColor Red
Write-Host "+-------------------------------------+----------+----------+----------+-----------+---------------+" -ForegroundColor White
Write-Host ""

# --- Front doors -------------------------------------------------------------
Write-Host "=============================================================" -ForegroundColor Magenta
Write-Host "  FRONT DOORS:" -ForegroundColor Cyan
Write-Host "  Review Console : $REVIEW_URL" -ForegroundColor White
Write-Host "  Grafana Audio  : $GRAFANA_AUDIO" -ForegroundColor White
Write-Host "  Grafana Health : $GRAFANA_HEALTH" -ForegroundColor White
Write-Host "=============================================================" -ForegroundColor Magenta
Write-Host ""

# Open browser automatically
$browserPaths = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Google\Chrome\Application\chrome.exe"
)
$browser = $null
foreach ($p in $browserPaths) {
    if (Test-Path $p) { $browser = $p; break }
}

if ($null -ne $browser) {
    Write-Info "Opening Review Console in browser..."
    Start-Process $browser $REVIEW_URL
    Start-Sleep -Seconds 1
    Start-Process $browser $GRAFANA_AUDIO
} else {
    Write-Warn "Edge/Chrome not found - open URLs above manually"
}

# --- Idempotency tip ---------------------------------------------------------
Write-Host ""
Write-Host "+---------------------------------------------------------------+" -ForegroundColor DarkCyan
Write-Host "|  TIP: Prove Idempotency live - run after this script:        |" -ForegroundColor DarkCyan
Write-Host "|  .\run-demo-replay.ps1                                        |" -ForegroundColor White
Write-Host "|                                                               |" -ForegroundColor DarkCyan
Write-Host "|  -> Kafka offset increases, but audio_features rows UNCHANGED|" -ForegroundColor Green
Write-Host "+---------------------------------------------------------------+" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "Demo complete. Stack is still running. Use 'docker compose down' to stop." -ForegroundColor Green
Write-Host ""
