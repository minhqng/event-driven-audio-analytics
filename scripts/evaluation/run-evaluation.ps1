Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "../..")
Set-Location -LiteralPath $repoRoot

function Assert-LastExitCode {
    param([string]$Context)
    if ($LASTEXITCODE -ne 0) {
        throw "$Context failed with exit code $LASTEXITCODE."
    }
}

$evaluationRootHost = Join-Path $PWD "artifacts\evidence\final-demo\evaluation"
$evaluationRootContainer = "/app/artifacts/evidence/final-demo/evaluation"
$resourceRootHost = Join-Path $evaluationRootHost "resource-samples"
$resourceRootContainer = "$evaluationRootContainer/resource-samples"
$resourceSampleIntervalS = if ($env:EVAL_RESOURCE_SAMPLE_INTERVAL_S) { $env:EVAL_RESOURCE_SAMPLE_INTERVAL_S } else { "2" }
$artifactReadSampleSize = if ($env:EVAL_ARTIFACT_READ_SAMPLE_SIZE) { $env:EVAL_ARTIFACT_READ_SAMPLE_SIZE } else { "20" }

function Invoke-Collect {
    param(
        [string]$Scenario,
        [string]$RunId,
        [string]$Status,
        [string]$DurationS,
        [string]$RequestedTracks,
        [int]$ProcessingReplicas,
        [string]$ResourceSamplesContainer,
        [string]$SkipReason = "",
        [switch]$IncludeScaling
    )

    $collectArgs = @(
        "compose", "run", "--rm", "--no-deps", "--entrypoint", "python", "pytest",
        "-m", "event_driven_audio_analytics.evaluation.collect",
        "--run-id", $RunId,
        "--scenario", $Scenario,
        "--output-root", $evaluationRootContainer,
        "--status", $Status,
        "--processing-replicas", "$ProcessingReplicas",
        "--duration-s", $DurationS,
        "--resource-sample-interval-s", $resourceSampleIntervalS,
        "--artifact-read-sample-size", $artifactReadSampleSize
    )
    if ($RequestedTracks -ne "") {
        $collectArgs += @("--requested-tracks", $RequestedTracks)
    }
    if ($ResourceSamplesContainer -ne "") {
        $collectArgs += @("--resource-samples-jsonl", $ResourceSamplesContainer)
    }
    if ($SkipReason -ne "") {
        $collectArgs += @("--skip-reason", $SkipReason)
    }
    if ($IncludeScaling) {
        $collectArgs += "--include-scaling"
    }

    docker @collectArgs | Out-Null
    Assert-LastExitCode "evaluation collect $Scenario"
}

function Start-ResourceSampler {
    param([string]$OutputPath)

    $intervalS = [Math]::Max([int][Math]::Ceiling([double]$resourceSampleIntervalS), 1)
    Start-Job -ArgumentList @($repoRoot.Path, $OutputPath, $intervalS) -ScriptBlock {
        param(
            [string]$RepoRoot,
            [string]$OutputPath,
            [int]$IntervalS
        )

        Set-Location -LiteralPath $RepoRoot
        while ($true) {
            docker stats --no-stream --format "{{json .}}" | Where-Object { $_ } |
                Add-Content -LiteralPath $OutputPath -Encoding utf8
            Start-Sleep -Seconds $IntervalS
        }
    }
}

function Stop-ResourceSampler {
    param([object]$SamplerJob)

    if ($null -eq $SamplerJob) {
        return
    }
    Stop-Job -Job $SamplerJob -ErrorAction SilentlyContinue
    Receive-Job -Job $SamplerJob -ErrorAction SilentlyContinue | Out-Null
    Remove-Job -Job $SamplerJob -Force -ErrorAction SilentlyContinue
}

function Clear-RunArtifacts {
    param([string]$RunId)

    $cleanupRunArtifactsScript = @'
import os
import shutil
from pathlib import Path
from event_driven_audio_analytics.shared.storage import validate_run_id

run_id = validate_run_id(os.environ["CLEANUP_RUN_ID"])
root = Path("/app/artifacts/runs").resolve()
target = (root / run_id).resolve()
target.relative_to(root)
shutil.rmtree(target, ignore_errors=True)
'@
    $cleanupScriptB64 = [Convert]::ToBase64String(
        [Text.Encoding]::UTF8.GetBytes($cleanupRunArtifactsScript)
    )
    $cleanupEntrypointScript = "import base64, os; exec(base64.b64decode(os.environ['CLEANUP_RUN_ARTIFACTS_SCRIPT_B64']).decode())"
    docker compose run --rm --no-deps `
        -e "CLEANUP_RUN_ID=$RunId" `
        -e "CLEANUP_RUN_ARTIFACTS_SCRIPT_B64=$cleanupScriptB64" `
        --entrypoint python ingestion `
        -c $cleanupEntrypointScript | Out-Null
    Assert-LastExitCode "cleanup run artifacts"
}

function Invoke-BoundedRun {
    param(
        [string]$Scenario,
        [string]$RunId,
        [string]$MetadataCsvContainer,
        [string]$AudioRootContainer,
        [string]$MaxTracks,
        [string]$TrackIdAllowlist,
        [int]$ProcessingReplicas = 1,
        [switch]$IncludeScaling
    )

    $resourceSamplesHost = Join-Path $resourceRootHost "$RunId.jsonl"
    $resourceSamplesContainer = "$resourceRootContainer/$RunId.jsonl"
    if (Test-Path $resourceSamplesHost) {
        Remove-Item -LiteralPath $resourceSamplesHost -Force
    }
    New-Item -ItemType Directory -Path $resourceRootHost -Force | Out-Null

    Write-Host "Running evaluation scenario=$Scenario run_id=$RunId processing_replicas=$ProcessingReplicas..."
    docker compose down --remove-orphans
    Assert-LastExitCode "docker compose down"

    docker compose build ingestion processing writer pytest
    Assert-LastExitCode "docker compose build evaluation services"
    Clear-RunArtifacts -RunId $RunId

    docker compose up --build -d kafka timescaledb
    Assert-LastExitCode "docker compose up kafka timescaledb"
    & (Resolve-Path "infra/kafka/create-topics.ps1")
    Assert-LastExitCode "create topics"

    docker compose run --rm --no-deps writer preflight
    Assert-LastExitCode "writer preflight"
    docker compose run --rm --no-deps processing preflight
    Assert-LastExitCode "processing preflight"
    docker compose run --rm --no-deps ingestion preflight
    Assert-LastExitCode "ingestion preflight"

    docker compose up -d --no-deps --scale "processing=$ProcessingReplicas" processing writer
    Assert-LastExitCode "docker compose up processing writer"
    Start-Sleep -Seconds 5

    $samplerJob = $null
    $endedAt = $null
    $startedAt = Get-Date
    try {
        $samplerJob = Start-ResourceSampler -OutputPath $resourceSamplesHost
        docker compose run --rm --no-deps `
            -e "RUN_ID=$RunId" `
            -e "METADATA_CSV_PATH=$MetadataCsvContainer" `
            -e "AUDIO_ROOT_PATH=$AudioRootContainer" `
            -e "TRACK_ID_ALLOWLIST=$TrackIdAllowlist" `
            -e "INGESTION_MAX_TRACKS=$MaxTracks" `
            ingestion
        Assert-LastExitCode "ingestion $Scenario"

        docker compose run --rm --no-deps `
            -e "RUN_ID=$RunId" `
            --entrypoint python `
            pytest `
            -m event_driven_audio_analytics.smoke.verify_writer_flow | Out-Null
        Assert-LastExitCode "verify writer $Scenario"
        $endedAt = Get-Date
    } finally {
        Stop-ResourceSampler -SamplerJob $samplerJob
        if ($null -eq $endedAt) {
            $endedAt = Get-Date
        }
    }

    $durationS = [Math]::Max(($endedAt - $startedAt).TotalSeconds, 0.001)
    Invoke-Collect `
        -Scenario $Scenario `
        -RunId $RunId `
        -Status "passed" `
        -DurationS ([string]::Format("{0:F6}", $durationS)) `
        -RequestedTracks $MaxTracks `
        -ProcessingReplicas $ProcessingReplicas `
        -ResourceSamplesContainer $resourceSamplesContainer `
        -IncludeScaling:$IncludeScaling
}

function Invoke-SkippedScenario {
    param(
        [string]$Scenario,
        [string]$RunId,
        [string]$RequestedTracks,
        [string]$Reason,
        [int]$ProcessingReplicas = 1,
        [switch]$IncludeScaling
    )

    Invoke-Collect `
        -Scenario $Scenario `
        -RunId $RunId `
        -Status "skipped" `
        -DurationS "0" `
        -RequestedTracks $RequestedTracks `
        -ProcessingReplicas $ProcessingReplicas `
        -ResourceSamplesContainer "" `
        -SkipReason $Reason `
        -IncludeScaling:$IncludeScaling
}

if (Test-Path $evaluationRootHost) {
    Remove-Item -LiteralPath $evaluationRootHost -Recurse -Force
}
New-Item -ItemType Directory -Path $evaluationRootHost -Force | Out-Null

$fixtureMetadata = "/app/tests/fixtures/audio/smoke_tracks.csv"
$fixtureAudioRoot = "/app/tests/fixtures/audio/smoke_fma_small"
Invoke-BoundedRun `
    -Scenario "deterministic-review-demo" `
    -RunId "eval-deterministic-review-demo" `
    -MetadataCsvContainer $fixtureMetadata `
    -AudioRootContainer $fixtureAudioRoot `
    -MaxTracks "2" `
    -TrackIdAllowlist "2,666"

$localMetadataHost = if ($env:LOCAL_FMA_METADATA_CSV_HOST) {
    $env:LOCAL_FMA_METADATA_CSV_HOST
} else {
    Join-Path $PWD "data\local\fma_metadata\tracks.csv"
}
$localAudioRootHost = if ($env:LOCAL_FMA_AUDIO_ROOT_HOST) {
    $env:LOCAL_FMA_AUDIO_ROOT_HOST
} else {
    Join-Path $PWD "data\local\fma_small"
}
$localMetadataContainer = if ($env:LOCAL_FMA_METADATA_CSV) {
    $env:LOCAL_FMA_METADATA_CSV
} else {
    "/app/data/local/fma_metadata/tracks.csv"
}
$localAudioRootContainer = if ($env:LOCAL_FMA_AUDIO_ROOT) {
    $env:LOCAL_FMA_AUDIO_ROOT
} else {
    "/app/data/local/fma_small"
}
$hasLocalFma = (Test-Path $localMetadataHost -PathType Leaf) -and
    (Test-Path $localAudioRootHost -PathType Container)

if ($hasLocalFma) {
    Invoke-BoundedRun `
        -Scenario "fma-small-burst-5" `
        -RunId "eval-fma-5" `
        -MetadataCsvContainer $localMetadataContainer `
        -AudioRootContainer $localAudioRootContainer `
        -MaxTracks "5" `
        -TrackIdAllowlist ""
    Invoke-BoundedRun `
        -Scenario "fma-small-burst-100" `
        -RunId "eval-fma-100" `
        -MetadataCsvContainer $localMetadataContainer `
        -AudioRootContainer $localAudioRootContainer `
        -MaxTracks "100" `
        -TrackIdAllowlist ""
    foreach ($replicaCount in @(1, 2, 3)) {
        Invoke-BoundedRun `
            -Scenario "fma-small-scaling-r$replicaCount" `
            -RunId "eval-scale-r$replicaCount" `
            -MetadataCsvContainer $localMetadataContainer `
            -AudioRootContainer $localAudioRootContainer `
            -MaxTracks "5" `
            -TrackIdAllowlist "" `
            -ProcessingReplicas $replicaCount `
            -IncludeScaling
    }
} else {
    $reason = "local FMA-Small files were not found under data/local"
    Invoke-SkippedScenario -Scenario "fma-small-burst-5" -RunId "eval-fma-5" -RequestedTracks "5" -Reason $reason
    Invoke-SkippedScenario -Scenario "fma-small-burst-100" -RunId "eval-fma-100" -RequestedTracks "100" -Reason $reason
    foreach ($replicaCount in @(1, 2, 3)) {
        Invoke-SkippedScenario `
            -Scenario "fma-small-scaling-r$replicaCount" `
            -RunId "eval-scale-r$replicaCount" `
            -RequestedTracks "5" `
            -Reason $reason `
            -ProcessingReplicas $replicaCount `
            -IncludeScaling
    }
}

if ($env:EVAL_ENABLE_FULL_FMA_SMALL -eq "true") {
    if ($hasLocalFma) {
        Invoke-BoundedRun `
            -Scenario "fma-small-full-local-experiment" `
            -RunId "eval-fma-full-local" `
            -MetadataCsvContainer $localMetadataContainer `
            -AudioRootContainer $localAudioRootContainer `
            -MaxTracks "" `
            -TrackIdAllowlist ""
    } else {
        Invoke-SkippedScenario `
            -Scenario "fma-small-full-local-experiment" `
            -RunId "eval-fma-full-local" `
            -RequestedTracks "" `
            -Reason "full FMA-Small local experiment requested but local files were unavailable"
    }
} else {
    Invoke-SkippedScenario `
        -Scenario "fma-small-full-local-experiment" `
        -RunId "eval-fma-full-local" `
        -RequestedTracks "" `
        -Reason "EVAL_ENABLE_FULL_FMA_SMALL is not true"
}

docker compose run --rm --no-deps --entrypoint python `
    pytest `
    -m event_driven_audio_analytics.evaluation.report `
    --output-root $evaluationRootContainer | Out-Null
Assert-LastExitCode "evaluation report"

$expectedOutputs = @(
    "latency-summary.json",
    "throughput-summary.json",
    "resource-usage-summary.json",
    "scaling-summary.json",
    "evaluation-report.md"
)
foreach ($expectedOutput in $expectedOutputs) {
    $expectedPath = Join-Path $evaluationRootHost $expectedOutput
    if (-not (Test-Path $expectedPath -PathType Leaf)) {
        throw "Expected evaluation output missing: $expectedPath"
    }
}

docker compose down --remove-orphans
Assert-LastExitCode "docker compose down"

Write-Host "Evaluation evidence written to $evaluationRootHost"
