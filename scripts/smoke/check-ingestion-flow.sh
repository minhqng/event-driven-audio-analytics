#!/usr/bin/env sh
set -eu

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

echo "Starting Kafka for ingestion smoke..."
docker compose up --build -d kafka

echo "Bootstrapping Kafka topics..."
sh ./infra/kafka/create-topics.sh

require_topic "audio.metadata"
require_topic "audio.segment.ready"
require_topic "system.metrics"

echo "Running ingestion service in Compose..."
docker compose up --build --no-deps ingestion

echo "Observing Kafka messages..."
metadata_messages="$(sh ./scripts/smoke/observe-topic.sh audio.metadata 2)"
segment_messages="$(sh ./scripts/smoke/observe-topic.sh audio.segment.ready 3)"
metric_messages="$(sh ./scripts/smoke/observe-topic.sh system.metrics 4)"

printf '%s\n' "$metadata_messages"
printf '%s\n' "$segment_messages"
printf '%s\n' "$metric_messages"

metadata_count="$(printf '%s\n' "$metadata_messages" | grep -c '^[0-9][0-9]*|')"
segment_count="$(printf '%s\n' "$segment_messages" | grep -c '^2|')"
metric_count="$(printf '%s\n' "$metric_messages" | grep -c '^ingestion|')"

if [ "$metadata_count" -lt 2 ]; then
  echo "Expected at least 2 audio.metadata messages with track_id keys." >&2
  exit 1
fi

if [ "$segment_count" -lt 1 ]; then
  echo "Expected at least 1 audio.segment.ready message keyed by track_id=2." >&2
  exit 1
fi

if [ "$metric_count" -lt 4 ]; then
  echo "Expected 4 system.metrics messages keyed by service_name=ingestion." >&2
  exit 1
fi

echo "Ingestion smoke flow passed."
