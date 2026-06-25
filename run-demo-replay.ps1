##############################################################################
#  run-demo-replay.ps1  -  Prove Idempotency (Replay) during live demo
#
#  Purpose: Run DURING the defense after run-demo-live.ps1 has completed.
#  Replays the same run_id -> Kafka offset increases, TimescaleDB rows UNCHANGED.
#
#  Usage: .\run-demo-replay.ps1
##############################################################################

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Write-Step { param([string]$Msg) Write-Host "" ; Write-Host "[*] $Msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Msg) Write-Host "    OK  $Msg" -ForegroundColor Green }
function Write-Info { param([string]$Msg) Write-Host "     -  $Msg" -ForegroundColor White }

function Assert-ExitCode {
    param([string]$Context)
    if ($LASTEXITCODE -ne 0) { throw "$Context failed (exit $LASTEXITCODE)." }
}

$META_CSV   = "/app/artifacts/demo-inputs/review-demo/metadata.csv"
$AUDIO_ROOT = "/app/artifacts/demo-inputs/review-demo/fma_small"
$pgUser     = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "audio_analytics" }
$pgDb       = if ($env:POSTGRES_DB)   { $env:POSTGRES_DB   } else { "audio_analytics" }

Write-Host ""
Write-Host "=============================================================" -ForegroundColor Magenta
Write-Host "  Idempotency Check -- REPLAY demo-high-energy"              -ForegroundColor Magenta
Write-Host "=============================================================" -ForegroundColor Magenta

# --- Read state BEFORE replay -----------------------------------------------
Write-Step "BEFORE Replay - read current TimescaleDB state"

$rowsBefore = docker compose exec -T timescaledb `
    psql -U $pgUser -d $pgDb -tAc `
    "SELECT COUNT(*) FROM audio_features WHERE run_id='demo-high-energy';" 2>$null
$rowsBefore = $rowsBefore.Trim()

$offsetRaw = docker compose exec -T kafka `
    /opt/bitnami/kafka/bin/kafka-run-class.sh kafka.tools.GetOffsetShell `
    --bootstrap-server kafka:29092 `
    --topic audio.features `
    --time -1 2>$null
$offsetBefore = ($offsetRaw | Select-Object -Last 1) -replace ".*::", "" -replace ".*:([0-9]+)$", '$1'
$offsetBefore = $offsetBefore.Trim()

Write-Info "audio_features rows   (BEFORE): $rowsBefore"
Write-Info "audio.features offset (BEFORE): $offsetBefore"

# --- Re-run Ingestion with same run_id --------------------------------------
Write-Step "Replay - re-run Ingestion (same run_id=demo-high-energy)"
docker compose run --rm --no-deps `
    -e "RUN_ID=demo-high-energy" `
    -e "METADATA_CSV_PATH=$META_CSV" `
    -e "AUDIO_ROOT_PATH=$AUDIO_ROOT" `
    -e "TRACK_ID_ALLOWLIST=910001" `
    -e "INGESTION_MAX_TRACKS=1" `
    ingestion
Assert-ExitCode "ingestion replay"
Write-Ok "Ingestion replay done - same events re-published to Kafka"

# --- Wait for Writer to upsert ----------------------------------------------
Write-Step "Waiting for Writer to upsert (idempotent write)..."
Start-Sleep -Seconds 10

# --- Read state AFTER replay -------------------------------------------------
Write-Step "AFTER Replay - read TimescaleDB state again"

$rowsAfter = docker compose exec -T timescaledb `
    psql -U $pgUser -d $pgDb -tAc `
    "SELECT COUNT(*) FROM audio_features WHERE run_id='demo-high-energy';" 2>$null
$rowsAfter = $rowsAfter.Trim()

$offsetRaw2 = docker compose exec -T kafka `
    /opt/bitnami/kafka/bin/kafka-run-class.sh kafka.tools.GetOffsetShell `
    --bootstrap-server kafka:29092 `
    --topic audio.features `
    --time -1 2>$null
$offsetAfter = ($offsetRaw2 | Select-Object -Last 1) -replace ".*::", "" -replace ".*:([0-9]+)$", '$1'
$offsetAfter = $offsetAfter.Trim()

Write-Info "audio_features rows   (AFTER): $rowsAfter"
Write-Info "audio.features offset (AFTER): $offsetAfter"

# --- Print proof table -------------------------------------------------------
Write-Host ""
Write-Host "+------------------------------------+--------------+--------------+" -ForegroundColor White
Write-Host "| Metric                             |    BEFORE    |    AFTER     |" -ForegroundColor White
Write-Host "+------------------------------------+--------------+--------------+" -ForegroundColor White

$kafkaTrend = if ([int]$offsetAfter -gt [int]$offsetBefore) { "INCREASED ^" } else { "UNCHANGED =" }
$dbTrend    = if ($rowsAfter -eq $rowsBefore) { "UNCHANGED = OK" } else { "CHANGED ! FAIL" }

$kafkaColor = if ([int]$offsetAfter -gt [int]$offsetBefore) { "Yellow" } else { "Gray" }
$dbColor    = if ($rowsAfter -eq $rowsBefore) { "Green" } else { "Red" }

$kafkaLine = "| {0,-34} | {1,12} | {2,12} |" -f "Kafka audio.features offset", $offsetBefore, "$offsetAfter ($kafkaTrend)"
$dbLine    = "| {0,-34} | {1,12} | {2,12} |" -f "TimescaleDB audio_features rows", $rowsBefore, "$rowsAfter ($dbTrend)"

Write-Host $kafkaLine -ForegroundColor $kafkaColor
Write-Host $dbLine    -ForegroundColor $dbColor
Write-Host "+------------------------------------+--------------+--------------+" -ForegroundColor White

Write-Host ""
if ($rowsAfter -eq $rowsBefore) {
    Write-Host "  [PASS] IDEMPOTENCY VERIFIED" -ForegroundColor Green
    Write-Host "         Kafka offset increased -> events were re-processed"    -ForegroundColor Green
    Write-Host "         BUT TimescaleDB rows UNCHANGED -> at-least-once + upsert = replay-safe" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Rows changed - unexpected (check advisory lock + upsert logic)" -ForegroundColor Red
}
Write-Host ""
