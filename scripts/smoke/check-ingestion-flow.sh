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

echo "Starting Kafka for ingestion smoke..."
docker compose up --build -d kafka

echo "Bootstrapping Kafka topics..."
sh ./infra/kafka/create-topics.sh

require_topic "audio.metadata"
require_topic "audio.segment.ready"
require_topic "system.metrics"

echo "Building ingestion image..."
docker compose build ingestion

echo "Running ingestion preflight..."
docker compose run --rm --no-deps ingestion preflight

echo "Running ingestion service in Compose..."
docker compose up --build --no-deps ingestion

echo "Observing Kafka messages for debugging only..."
metadata_messages="$(sh ./scripts/smoke/observe-topic.sh audio.metadata 2)"
segment_messages="$(sh ./scripts/smoke/observe-topic.sh audio.segment.ready 3)"
metric_messages="$(sh ./scripts/smoke/observe-topic.sh system.metrics 4)"

printf '%s\n' "$metadata_messages"
printf '%s\n' "$segment_messages"
printf '%s\n' "$metric_messages"

echo "Verifying exact current-run Kafka payloads against the configured input selection..."
verification_summary="$(docker compose run --rm --no-deps --entrypoint python ingestion \
  -m event_driven_audio_analytics.smoke.verify_ingestion_flow)"
printf '%s\n' "$verification_summary"

echo "Checking structured ingestion logs..."
ingestion_logs="$(docker compose logs ingestion)"
printf '%s\n' "$ingestion_logs"

if printf '%s\n' "$verification_summary" | grep -Eq '"validated_track_ids":\[[^]]*[0-9]'; then
  if ! printf '%s\n' "$ingestion_logs" \
    | grep 'Published track events' \
    | grep -Eq "\"trace_id\":\"run/$effective_run_id/track/[0-9]+\""; then
    echo "Expected a success log line with a current-run track trace_id." >&2
    exit 1
  fi

  if ! printf '%s\n' "$ingestion_logs" \
    | grep 'Published track events' \
    | grep -Eq '"track_id":[0-9]+'; then
    echo "Expected a success log line with track_id context." >&2
    exit 1
  fi
fi

if printf '%s\n' "$verification_summary" | grep -Eq '"rejected_track_ids":\[[^]]*[0-9]'; then
  if ! printf '%s\n' "$ingestion_logs" \
    | grep 'Published metadata only for rejected track' \
    | grep -Eq "\"trace_id\":\"run/$effective_run_id/track/[0-9]+\""; then
    echo "Expected a reject log line with a current-run track trace_id." >&2
    exit 1
  fi

  if ! printf '%s\n' "$ingestion_logs" \
    | grep 'Published metadata only for rejected track' \
    | grep -q '"validation_status":"'; then
    echo "Expected a reject log line with validation_status context." >&2
    exit 1
  fi
fi

echo "Ingestion smoke flow passed."
