#!/usr/bin/env sh
set -eu

effective_run_id="${RUN_ID:-demo-run}"

cleanup_run_artifacts() {
  run_id="$1"

  docker compose run --rm --no-deps \
    -e CLEANUP_RUN_ID="$run_id" \
    --entrypoint python ingestion \
    -c '
import os
import shutil
from pathlib import Path
from event_driven_audio_analytics.shared.storage import validate_run_id

run_id = validate_run_id(os.environ["CLEANUP_RUN_ID"])
root = Path("/app/artifacts/runs").resolve()
target = (root / run_id).resolve()
target.relative_to(root)
shutil.rmtree(target, ignore_errors=True)
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

echo "Resetting local stack..."
docker compose down --remove-orphans

echo "Cleaning prior run artifacts..."
cleanup_run_artifacts "$effective_run_id"

echo "Starting Kafka and TimescaleDB for processing->writer smoke..."
docker compose up --build -d kafka timescaledb

echo "Bootstrapping Kafka topics..."
sh ./infra/kafka/create-topics.sh

require_topic "audio.metadata"
require_topic "audio.segment.ready"
require_topic "audio.features"
require_topic "system.metrics"

echo "Building ingestion, processing, writer, and pytest images..."
docker compose build ingestion processing writer pytest

echo "Running writer preflight..."
docker compose run --rm --no-deps writer preflight

echo "Running processing preflight..."
docker compose run --rm --no-deps processing preflight

echo "Running ingestion preflight..."
docker compose run --rm --no-deps ingestion preflight

echo "Starting processing and writer services in Compose..."
docker compose up -d --no-deps processing writer
sleep 5

running_services="$(docker compose ps --services --status running)"
if ! printf '%s\n' "$running_services" | grep -qx "processing"; then
  echo "Processing service is not running after startup." >&2
  docker compose logs processing >&2 || true
  exit 1
fi
if ! printf '%s\n' "$running_services" | grep -qx "writer"; then
  echo "Writer service is not running after startup." >&2
  docker compose logs writer >&2 || true
  exit 1
fi

echo "Running ingestion one-shot to feed Kafka..."
docker compose run --rm --no-deps ingestion

echo "Verifying current-run TimescaleDB outputs..."
verification_summary="$(docker compose run --rm --no-deps -e RUN_ID="$effective_run_id" --entrypoint python pytest \
  -m event_driven_audio_analytics.smoke.verify_writer_flow)"
printf '%s\n' "$verification_summary"

echo "Checking structured logs..."
processing_logs="$(docker compose logs processing)"
writer_logs="$(docker compose logs writer)"
printf '%s\n' "$processing_logs"
printf '%s\n' "$writer_logs"

running_services="$(docker compose ps --services --status running)"
if ! printf '%s\n' "$running_services" | grep -qx "processing"; then
  echo "Processing service is no longer running after the smoke flow." >&2
  exit 1
fi
if ! printf '%s\n' "$running_services" | grep -qx "writer"; then
  echo "Writer service is no longer running after the smoke flow." >&2
  exit 1
fi

if printf '%s\n' "$processing_logs" | grep -q 'Processing failed'; then
  echo "Unexpected processing failure logs appeared during the healthy smoke path." >&2
  exit 1
fi
if printf '%s\n' "$writer_logs" | grep -q 'Writer failed'; then
  echo "Unexpected writer failure logs appeared during the healthy smoke path." >&2
  exit 1
fi

if printf '%s\n' "$verification_summary" | grep -Eq '"metadata_count":[1-9][0-9]*'; then
  if ! printf '%s\n' "$writer_logs" | grep 'Persisted writer outputs' | grep -Eq "\"trace_id\":\"run/$effective_run_id/track/[0-9]+\""; then
    echo "Expected a writer success log line with a current-run track trace_id." >&2
    exit 1
  fi
fi

echo "Processing -> writer smoke flow passed."
