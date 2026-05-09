Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot "../.."))

$effectiveRunId = if ($env:RUN_ID) { $env:RUN_ID } else { "minio-smoke" }
$env:RUN_ID = $effectiveRunId
$env:STORAGE_BACKEND = if ($env:STORAGE_BACKEND) { $env:STORAGE_BACKEND } else { "minio" }
$env:MINIO_CREATE_BUCKET = if ($env:MINIO_CREATE_BUCKET) { $env:MINIO_CREATE_BUCKET } else { "true" }
$env:MINIO_ENDPOINT_URL = if ($env:MINIO_ENDPOINT_URL) {
    $env:MINIO_ENDPOINT_URL
} elseif ($env:MINIO_ENDPOINT) {
    $env:MINIO_ENDPOINT
} elseif ($env:MINIO_SECURE -match "^(?i:1|true|yes|on)$") {
    "https://minio:9000"
} else {
    "http://minio:9000"
}
$env:MINIO_BUCKET = if ($env:MINIO_BUCKET) {
    $env:MINIO_BUCKET
} elseif ($env:ARTIFACT_BUCKET) {
    $env:ARTIFACT_BUCKET
} else {
    "fma-small-artifacts"
}

if ($env:STORAGE_BACKEND -ne "minio") {
    throw "MinIO claim-check smoke requires STORAGE_BACKEND=minio."
}

function Assert-LastExitCode {
    param(
        [string]$Context
    )

    if ($LASTEXITCODE -ne 0) {
        throw "$Context failed with exit code $LASTEXITCODE."
    }
}

$cleanupRunStateScript = @'
import os
import shutil
from pathlib import Path
import boto3
from event_driven_audio_analytics.shared.settings import load_storage_backend_settings
from event_driven_audio_analytics.shared.storage import validate_run_id

run_id = validate_run_id(os.environ['CLEANUP_RUN_ID'])
artifacts_root = Path('/app/artifacts').resolve()
for relative in (Path('runs') / run_id, Path('datasets') / run_id):
    target = (artifacts_root / relative).resolve()
    target.relative_to(artifacts_root)
    shutil.rmtree(target, ignore_errors=True)

storage = load_storage_backend_settings(artifacts_root=artifacts_root)
if storage.normalized_backend() == 'minio':
    client = boto3.client(
        's3',
        endpoint_url=storage.endpoint_url,
        aws_access_key_id=storage.access_key,
        aws_secret_access_key=storage.secret_key,
        region_name=storage.region,
        use_ssl=storage.secure,
    )
    continuation_token = None
    prefix = f'runs/{run_id}/'
    while True:
        request = {'Bucket': storage.bucket, 'Prefix': prefix}
        if continuation_token is not None:
            request['ContinuationToken'] = continuation_token
        try:
            response = client.list_objects_v2(**request)
        except Exception as exc:
            error_response = getattr(exc, 'response', None)
            error_code = (
                str(error_response.get('Error', {}).get('Code', ''))
                if isinstance(error_response, dict)
                else ''
            )
            if error_code in {'404', 'NoSuchBucket', 'NotFound'}:
                break
            raise
        objects = response.get('Contents', [])
        if objects:
            client.delete_objects(
                Bucket=storage.bucket,
                Delete={
                    'Objects': [{'Key': str(item['Key'])} for item in objects],
                    'Quiet': True,
                },
            )
        if not response.get('IsTruncated'):
            break
        continuation_token = str(response['NextContinuationToken'])
'@

function Clear-RunStateInContainer {
    param(
        [string]$RunId
    )

    docker compose run --rm --no-deps --build -e "CLEANUP_RUN_ID=$RunId" --entrypoint python ingestion -c $cleanupRunStateScript | Out-Null
    Assert-LastExitCode "docker compose run cleanup run state"
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

function Require-RunningService {
    param(
        [string]$ServiceName
    )

    $runningServices = docker compose ps --services --status running
    Assert-LastExitCode "docker compose ps running"
    if (-not (($runningServices -split "\r?\n") -contains $ServiceName)) {
        docker compose logs $ServiceName
        Assert-LastExitCode "docker compose logs $ServiceName"
        throw "Service is not running: $ServiceName"
    }
}

$evidenceRoot = Join-Path $PWD "artifacts\evidence\minio-claim-check"
$summaryPath = Join-Path $evidenceRoot "$effectiveRunId-summary.json"
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null

Write-Host "Resetting local stack..."
docker compose down --remove-orphans
Assert-LastExitCode "docker compose down"

Write-Host "Starting Kafka, TimescaleDB, and MinIO..."
docker compose up --build -d kafka timescaledb minio minio-init
Assert-LastExitCode "docker compose up kafka timescaledb minio minio-init"

Write-Host "Cleaning prior run artifacts, dataset bundle, and MinIO objects..."
Clear-RunStateInContainer -RunId $effectiveRunId
if (Test-Path -LiteralPath $summaryPath) {
    Remove-Item -LiteralPath $summaryPath -Force
}

Write-Host "Bootstrapping Kafka topics..."
& (Resolve-Path "infra/kafka/create-topics.ps1")

Require-Topic "audio.metadata"
Require-Topic "audio.segment.ready"
Require-Topic "audio.features"
Require-Topic "system.metrics"

Write-Host "Building ingestion, processing, writer, review, and dataset-exporter images..."
docker compose build ingestion processing writer review dataset-exporter
Assert-LastExitCode "docker compose build ingestion processing writer review dataset-exporter"

Write-Host "Running writer preflight..."
docker compose run --rm --no-deps writer preflight
Assert-LastExitCode "docker compose run writer preflight"

Write-Host "Running processing preflight..."
docker compose run --rm --no-deps processing preflight
Assert-LastExitCode "docker compose run processing preflight"

Write-Host "Running ingestion preflight..."
docker compose run --rm --no-deps ingestion preflight
Assert-LastExitCode "docker compose run ingestion preflight"

Write-Host "Running review preflight..."
docker compose run --rm --no-deps review preflight
Assert-LastExitCode "docker compose run review preflight"

Write-Host "Starting processing, writer, and review services in Compose..."
docker compose up -d --no-deps processing writer review
Assert-LastExitCode "docker compose up processing writer review"
Start-Sleep -Seconds 5

Require-RunningService "processing"
Require-RunningService "writer"
Require-RunningService "review"

Write-Host "Running ingestion one-shot to feed Kafka..."
docker compose run --rm --no-deps ingestion
Assert-LastExitCode "docker compose run ingestion"

Write-Host "Verifying current-run writer snapshot..."
$writerSummary = docker compose run --rm --no-deps -e "RUN_ID=$effectiveRunId" --entrypoint python pytest -m event_driven_audio_analytics.smoke.verify_writer_flow
Assert-LastExitCode "docker compose run verify_writer_flow"
$writerSummary

Write-Host "Exporting MinIO-backed dataset bundle..."
docker compose run --rm --no-deps dataset-exporter export --run-id $effectiveRunId | Out-Null
Assert-LastExitCode "docker compose run dataset-exporter export"

Write-Host "Verifying MinIO-backed claim-check flow..."
$summary = docker compose run --rm --no-deps `
    -e "RUN_ID=$effectiveRunId" `
    --entrypoint python dataset-exporter `
    -m event_driven_audio_analytics.smoke.verify_minio_claim_check_flow `
    --run-id $effectiveRunId `
    --base-url "http://review:8080"
Assert-LastExitCode "docker compose run verify_minio_claim_check_flow"
$summary | Set-Content -LiteralPath $summaryPath -Encoding utf8
$summary

Write-Host "Checking service health after MinIO flow..."
Require-RunningService "processing"
Require-RunningService "writer"
Require-RunningService "review"

Write-Host "MinIO claim-check smoke flow passed."
