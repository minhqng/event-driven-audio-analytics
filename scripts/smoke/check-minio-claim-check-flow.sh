#!/usr/bin/env sh
set -eu

effective_run_id="${RUN_ID:-minio-smoke}"
export RUN_ID="$effective_run_id"
export STORAGE_BACKEND="${STORAGE_BACKEND:-minio}"
export MINIO_CREATE_BUCKET="${MINIO_CREATE_BUCKET:-true}"
if [ -n "${MINIO_ENDPOINT_URL:-}" ]; then
  export MINIO_ENDPOINT_URL
elif [ -n "${MINIO_ENDPOINT:-}" ]; then
  export MINIO_ENDPOINT_URL="$MINIO_ENDPOINT"
else
  case "$(printf '%s' "${MINIO_SECURE:-false}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on)
      export MINIO_ENDPOINT_URL="https://minio:9000"
      ;;
    *)
      export MINIO_ENDPOINT_URL="http://minio:9000"
      ;;
  esac
fi
export MINIO_BUCKET="${MINIO_BUCKET:-${ARTIFACT_BUCKET:-fma-small-artifacts}}"

if [ "$STORAGE_BACKEND" != "minio" ]; then
  echo "MinIO claim-check smoke requires STORAGE_BACKEND=minio." >&2
  exit 1
fi

cleanup_run_state() {
  run_id="$1"

  docker compose run --rm --no-deps --build \
    -e CLEANUP_RUN_ID="$run_id" \
    --entrypoint python ingestion \
    -c '
import os
import shutil
from pathlib import Path
import boto3
from event_driven_audio_analytics.shared.settings import load_storage_backend_settings
from event_driven_audio_analytics.shared.storage import validate_run_id

run_id = validate_run_id(os.environ["CLEANUP_RUN_ID"])
artifacts_root = Path("/app/artifacts").resolve()
for relative in (Path("runs") / run_id, Path("datasets") / run_id):
    target = (artifacts_root / relative).resolve()
    target.relative_to(artifacts_root)
    shutil.rmtree(target, ignore_errors=True)

storage = load_storage_backend_settings(artifacts_root=artifacts_root)
if storage.normalized_backend() == "minio":
    client = boto3.client(
        "s3",
        endpoint_url=storage.endpoint_url,
        aws_access_key_id=storage.access_key,
        aws_secret_access_key=storage.secret_key,
        region_name=storage.region,
        use_ssl=storage.secure,
    )
    continuation_token = None
    prefix = f"runs/{run_id}/"
    while True:
        request = {"Bucket": storage.bucket, "Prefix": prefix}
        if continuation_token is not None:
            request["ContinuationToken"] = continuation_token
        try:
            response = client.list_objects_v2(**request)
        except Exception as exc:
            error_response = getattr(exc, "response", None)
            error_code = (
                str(error_response.get("Error", {}).get("Code", ""))
                if isinstance(error_response, dict)
                else ""
            )
            if error_code in {"404", "NoSuchBucket", "NotFound"}:
                break
            raise
        objects = response.get("Contents", [])
        if objects:
            client.delete_objects(
                Bucket=storage.bucket,
                Delete={
                    "Objects": [{"Key": str(item["Key"])} for item in objects],
                    "Quiet": True,
                },
            )
        if not response.get("IsTruncated"):
            break
        continuation_token = str(response["NextContinuationToken"])
' >/dev/null
}

require_topic() {
  topic_name="$1"

  if ! docker compose exec -T kafka /opt/bitnami/kafka/bin/kafka-topics.sh \
    --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}" \
    --list | grep -qx "$topic_name"; then
    echo "Missing expected Kafka topic: $topic_name" >&2
    return 1
  fi
}

require_running_service() {
  service_name="$1"
  running_services="$(docker compose ps --services --status running)"
  if ! printf '%s\n' "$running_services" | grep -qx "$service_name"; then
    echo "Service is not running: $service_name" >&2
    docker compose logs "$service_name" >&2 || true
    exit 1
  fi
}

evidence_root_host="artifacts/evidence/minio-claim-check"
summary_path="$evidence_root_host/$effective_run_id-summary.json"
mkdir -p "$evidence_root_host"

echo "Resetting local stack..."
docker compose down --remove-orphans

echo "Starting Kafka, TimescaleDB, and MinIO..."
docker compose up --build -d kafka timescaledb minio minio-init

echo "Cleaning prior run artifacts, dataset bundle, and MinIO objects..."
cleanup_run_state "$effective_run_id"
rm -f "$summary_path"

echo "Bootstrapping Kafka topics..."
sh ./infra/kafka/create-topics.sh

require_topic "audio.metadata"
require_topic "audio.segment.ready"
require_topic "audio.features"
require_topic "system.metrics"

echo "Building ingestion, processing, writer, review, and dataset-exporter images..."
docker compose build ingestion processing writer review dataset-exporter

echo "Running writer preflight..."
docker compose run --rm --no-deps writer preflight

echo "Running processing preflight..."
docker compose run --rm --no-deps processing preflight

echo "Running ingestion preflight..."
docker compose run --rm --no-deps ingestion preflight

echo "Running review preflight..."
docker compose run --rm --no-deps review preflight

echo "Starting processing, writer, and review services in Compose..."
docker compose up -d --no-deps processing writer review
sleep 5

require_running_service "processing"
require_running_service "writer"
require_running_service "review"

echo "Running ingestion one-shot to feed Kafka..."
docker compose run --rm --no-deps ingestion

echo "Verifying current-run writer snapshot..."
writer_summary="$(docker compose run --rm --no-deps -e RUN_ID="$effective_run_id" --entrypoint python pytest \
  -m event_driven_audio_analytics.smoke.verify_writer_flow)"
printf '%s\n' "$writer_summary"

echo "Exporting MinIO-backed dataset bundle..."
docker compose run --rm --no-deps dataset-exporter export --run-id "$effective_run_id" >/dev/null

echo "Verifying MinIO-backed claim-check flow..."
docker compose run --rm --no-deps \
  -e RUN_ID="$effective_run_id" \
  --entrypoint python dataset-exporter \
  -m event_driven_audio_analytics.smoke.verify_minio_claim_check_flow \
  --run-id "$effective_run_id" \
  --base-url "http://review:8080" > "$summary_path"
cat "$summary_path"

echo "Checking service health after MinIO flow..."
require_running_service "processing"
require_running_service "writer"
require_running_service "review"

echo "MinIO claim-check smoke flow passed."
