#!/usr/bin/env sh
set -eu

effective_run_id="${RUN_ID:-demo-run}"

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
docker compose run --rm --no-deps --entrypoint sh ingestion \
  -c "rm -rf /app/artifacts/runs/$effective_run_id" >/dev/null

echo "Starting Kafka for processing smoke..."
docker compose up --build -d kafka

echo "Bootstrapping Kafka topics..."
sh ./infra/kafka/create-topics.sh

require_topic "audio.metadata"
require_topic "audio.segment.ready"
require_topic "audio.features"
require_topic "system.metrics"

echo "Building ingestion and processing images..."
docker compose build ingestion processing

echo "Running processing preflight..."
docker compose run --rm --no-deps processing preflight

echo "Running ingestion preflight..."
docker compose run --rm --no-deps ingestion preflight

echo "Starting processing service in Compose..."
docker compose up -d --no-deps processing
sleep 5

if ! docker compose ps --services --status running | grep -qx "processing"; then
  echo "Processing service is not running after startup." >&2
  docker compose logs processing >&2 || true
  exit 1
fi

echo "Running ingestion one-shot to feed Kafka..."
docker compose run --rm --no-deps ingestion

echo "Observing Kafka messages for debugging only..."
feature_messages="$(sh ./scripts/smoke/observe-topic.sh audio.features 10)"
metric_messages="$(sh ./scripts/smoke/observe-topic.sh system.metrics 12)"

printf '%s\n' "$feature_messages"
printf '%s\n' "$metric_messages"

echo "Verifying current-run processing outputs against the configured input selection..."
verification_summary="$(docker compose run --rm --no-deps --entrypoint python processing \
  -m event_driven_audio_analytics.smoke.verify_processing_flow)"
printf '%s\n' "$verification_summary"

echo "Checking structured processing logs..."
processing_logs="$(docker compose logs processing)"
printf '%s\n' "$processing_logs"

if ! docker compose ps --services --status running | grep -qx "processing"; then
  echo "Processing service is no longer running after the smoke flow." >&2
  exit 1
fi

if printf '%s\n' "$processing_logs" | grep -q 'Processing failed'; then
  echo "Unexpected processing failure logs appeared during the healthy smoke path." >&2
  exit 1
fi

if printf '%s\n' "$verification_summary" | grep -Eq '"expected_segment_count":[1-9][0-9]*'; then
  if ! printf '%s\n' "$processing_logs" \
    | grep 'Published processing outputs' \
    | grep -Eq "\"trace_id\":\"run/$effective_run_id/track/[0-9]+\""; then
    echo "Expected a success log line with a current-run track trace_id." >&2
    exit 1
  fi

  if ! printf '%s\n' "$processing_logs" \
    | grep 'Published processing outputs' \
    | grep -Eq '"track_id":[0-9]+'; then
    echo "Expected a success log line with track_id context." >&2
    exit 1
  fi

  if ! printf '%s\n' "$processing_logs" \
    | grep 'Published processing outputs' \
    | grep -Eq '"segment_idx":[0-9]+'; then
    echo "Expected a success log line with segment_idx context." >&2
    exit 1
  fi

  if ! printf '%s\n' "$processing_logs" \
    | grep 'Published processing outputs' \
    | grep -q '"silent_flag":'; then
    echo "Expected a success log line with silent_flag context." >&2
    exit 1
  fi
fi

echo "Processing smoke flow passed."
