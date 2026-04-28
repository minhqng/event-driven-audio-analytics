Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot "../.."))

$effectiveRunId = if ($env:RUN_ID) { $env:RUN_ID } else { "replay-smoke" }
$evidenceRootHost = Join-Path $PWD "artifacts\evidence\final-demo\restart-replay"
$baselinePathHost = Join-Path $evidenceRootHost "restart-replay-baseline.json"
$summaryPathHost = Join-Path $evidenceRootHost "restart-replay-summary.json"
$preflightNotesHost = Join-Path $evidenceRootHost "preflight-fail-fast.txt"
$baselinePathContainer = "/app/artifacts/evidence/final-demo/restart-replay/restart-replay-baseline.json"
$summaryPathContainer = "/app/artifacts/evidence/final-demo/restart-replay/restart-replay-summary.json"
$kafkaBootstrapServer = if ($env:KAFKA_BOOTSTRAP_SERVERS) { $env:KAFKA_BOOTSTRAP_SERVERS } else { "kafka:29092" }

function Assert-LastExitCode {
    param(
        [string]$Context
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$Context failed with exit code $LASTEXITCODE."
    }
}

function Resolve-RunCleanupPath {
    param(
        [string]$RunId
    )

    if ([string]::IsNullOrWhiteSpace($RunId)) {
        throw "RUN_ID must not be empty or whitespace."
    }
    if ($RunId -in @(".", "..") -or $RunId.Contains("/") -or $RunId.Contains("\") -or $RunId.Contains(":") -or $RunId.Contains(".") -or $RunId -match "\s") {
        throw "RUN_ID must be a single relative path segment without whitespace or reserved path characters for cleanup under artifacts/runs."
    }

    $runsRoot = [System.IO.Path]::GetFullPath((Join-Path $PWD "artifacts\runs"))
    $cleanupTarget = [System.IO.Path]::GetFullPath((Join-Path $runsRoot $RunId))
    $directorySeparator = [System.IO.Path]::DirectorySeparatorChar
    $runsRootPrefix = if ($runsRoot.EndsWith($directorySeparator)) {
        $runsRoot
    } else {
        "$runsRoot$directorySeparator"
    }

    if (-not $cleanupTarget.StartsWith($runsRootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Resolved run cleanup path escaped artifacts/runs."
    }

    return $cleanupTarget
}

function Require-Topic {
    param(
        [string]$TopicName
    )

    $topics = docker compose exec -T kafka /opt/bitnami/kafka/bin/kafka-topics.sh `
        --bootstrap-server $kafkaBootstrapServer `
        --list
    Assert-LastExitCode "Listing Kafka topics"

    if (-not (($topics -split "\r?\n") -contains $TopicName)) {
        throw "Missing expected Kafka topic: $TopicName"
    }
}

function Wait-ForKafkaReady {
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        docker compose exec -T kafka /opt/bitnami/kafka/bin/kafka-topics.sh `
            --bootstrap-server $kafkaBootstrapServer `
            --list | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 2
    }

    throw "Timed out waiting for Kafka readiness."
}

function Wait-ForDbReady {
    $dbUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "audio_analytics" }
    $dbName = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "audio_analytics" }

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        docker compose exec -T timescaledb `
            psql -U $dbUser -d $dbName -tAc "SELECT 1;" | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 2
    }

    throw "Timed out waiting for TimescaleDB readiness."
}

function Assert-RunningServices {
    param(
        [string[]]$ServiceNames
    )

    $runningServices = docker compose ps --services --status running
    Assert-LastExitCode "docker compose ps running"

    foreach ($serviceName in $ServiceNames) {
        if (-not (($runningServices -split "\r?\n") -contains $serviceName)) {
            docker compose logs $serviceName
            Assert-LastExitCode "docker compose logs $serviceName"
            throw "Service is not running after startup/restart: $serviceName"
        }
    }
}

function Assert-ExpectedPreflightFailure {
    param(
        [string]$ServiceName,
        [string]$ExpectedPattern
    )

    $output = & cmd.exe /d /c "docker compose run --rm --no-deps $ServiceName preflight 2>&1"
    $exitCode = $LASTEXITCODE
    $outputText = ($output | Out-String)
    Add-Content -LiteralPath $preflightNotesHost -Value "===== $ServiceName preflight before topic bootstrap ====="
    Add-Content -LiteralPath $preflightNotesHost -Value $outputText
    $outputText

    if ($exitCode -eq 0) {
        throw "Expected $ServiceName preflight to fail before topic bootstrap."
    }
    if ($outputText -notmatch $ExpectedPattern) {
        throw "Unexpected $ServiceName preflight failure output."
    }
}

Write-Host "Resetting local stack..."
docker compose down --remove-orphans
Assert-LastExitCode "docker compose down"

Write-Host "Cleaning prior restart/replay evidence..."
$runArtifactsPathHost = Resolve-RunCleanupPath -RunId $effectiveRunId
if (Test-Path $evidenceRootHost) {
    Remove-Item -LiteralPath $evidenceRootHost -Recurse -Force
}
if (Test-Path $runArtifactsPathHost) {
    Remove-Item -LiteralPath $runArtifactsPathHost -Recurse -Force
}
New-Item -ItemType Directory -Path $evidenceRootHost -Force | Out-Null
Set-Content -LiteralPath $preflightNotesHost -Value "" -Encoding utf8

Write-Host "Building ingestion, processing, writer, and pytest images..."
docker compose build ingestion processing writer pytest
Assert-LastExitCode "docker compose build ingestion processing writer pytest"

Write-Host "Starting Kafka and TimescaleDB without topic bootstrap..."
docker compose up --build -d kafka timescaledb
Assert-LastExitCode "docker compose up kafka timescaledb"
Wait-ForKafkaReady
Wait-ForDbReady

Write-Host "Checking fail-fast preflights before topic bootstrap..."
Assert-ExpectedPreflightFailure -ServiceName "ingestion" -ExpectedPattern "missing required ingestion topics"
Assert-ExpectedPreflightFailure -ServiceName "processing" -ExpectedPattern "missing required processing topics"
Assert-ExpectedPreflightFailure -ServiceName "writer" -ExpectedPattern "missing required writer topics"

Write-Host "Bootstrapping Kafka topics..."
& (Resolve-Path "infra/kafka/create-topics.ps1")
Require-Topic "audio.metadata"
Require-Topic "audio.segment.ready"
Require-Topic "audio.features"
Require-Topic "system.metrics"

Write-Host "Running healthy preflights after topic bootstrap..."
docker compose run --rm --no-deps ingestion preflight
Assert-LastExitCode "docker compose run ingestion preflight"
docker compose run --rm --no-deps processing preflight
Assert-LastExitCode "docker compose run processing preflight"
docker compose run --rm --no-deps writer preflight
Assert-LastExitCode "docker compose run writer preflight"

Write-Host "Starting long-lived processing and writer services..."
docker compose up -d --no-deps processing writer
Assert-LastExitCode "docker compose up processing writer"
Start-Sleep -Seconds 5
Assert-RunningServices -ServiceNames @("processing", "writer")

Write-Host "Running first bounded ingestion pass for run_id=$effectiveRunId..."
docker compose run --rm --no-deps -e "RUN_ID=$effectiveRunId" ingestion
Assert-LastExitCode "docker compose run ingestion first pass"

Write-Host "Capturing healthy baseline verification..."
docker compose run --rm --no-deps `
    -e "RUN_ID=$effectiveRunId" `
    --entrypoint python `
    pytest `
    -m event_driven_audio_analytics.smoke.verify_writer_flow | Out-Null
Assert-LastExitCode "docker compose run verify_writer_flow"

Write-Host "Writing restart/replay baseline snapshot..."
docker compose run --rm --no-deps `
    -e "RUN_ID=$effectiveRunId" `
    --entrypoint python `
    pytest `
    -m event_driven_audio_analytics.smoke.verify_restart_replay_flow `
    capture `
    --output $baselinePathContainer | Out-Null
Assert-LastExitCode "docker compose run restart_replay capture"

Write-Host "Restarting processing and writer before replay..."
docker compose restart processing writer
Assert-LastExitCode "docker compose restart processing writer"
Start-Sleep -Seconds 5
Assert-RunningServices -ServiceNames @("processing", "writer")

Write-Host "Re-running ingestion with the same run_id=$effectiveRunId..."
docker compose run --rm --no-deps -e "RUN_ID=$effectiveRunId" ingestion
Assert-LastExitCode "docker compose run ingestion replay pass"

Write-Host "Verifying replay-stable sink rows, metrics, checkpoints, and processing state..."
docker compose run --rm --no-deps `
    -e "RUN_ID=$effectiveRunId" `
    --entrypoint python `
    pytest `
    -m event_driven_audio_analytics.smoke.verify_restart_replay_flow `
    verify `
    --baseline $baselinePathContainer `
    --output $summaryPathContainer | Out-Null
Assert-LastExitCode "docker compose run restart_replay verify"

Assert-RunningServices -ServiceNames @("processing", "writer")

$processingLogs = docker compose logs processing
Assert-LastExitCode "docker compose logs processing"
$writerLogs = docker compose logs writer
Assert-LastExitCode "docker compose logs writer"
if (@($processingLogs | Where-Object { $_ -match 'Processing failed' }).Count -gt 0) {
    throw "Unexpected processing failure logs appeared during restart/replay verification."
}
if (@($writerLogs | Where-Object { $_ -match 'Writer failed' }).Count -gt 0) {
    throw "Unexpected writer failure logs appeared during restart/replay verification."
}

if (-not (Test-Path $baselinePathHost)) {
    throw "Expected baseline artifact missing: $baselinePathHost"
}
if (-not (Test-Path $summaryPathHost)) {
    throw "Expected replay summary missing: $summaryPathHost"
}
if (-not (Test-Path $preflightNotesHost)) {
    throw "Expected preflight notes missing: $preflightNotesHost"
}

Write-Host "Restart / replay smoke flow passed."
Write-Host "Baseline snapshot: $baselinePathHost"
Write-Host "Replay summary: $summaryPathHost"
Write-Host "Fail-fast preflight notes: $preflightNotesHost"
