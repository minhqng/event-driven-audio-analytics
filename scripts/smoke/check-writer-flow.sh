#!/usr/bin/env sh
set -eu

wait_for_query() {
  sql="$1"
  expected="$2"
  attempts=0

  while [ "$attempts" -lt 30 ]; do
    result="$(
      docker compose exec -T timescaledb \
        psql -U "${POSTGRES_USER:-audio_analytics}" -d "${POSTGRES_DB:-audio_analytics}" -tAc "$sql"
    )"
    if [ "$result" = "$expected" ]; then
      return 0
    fi

    attempts=$((attempts + 1))
    sleep 2
  done

  echo "Timed out waiting for query result. SQL: $sql" >&2
  docker compose logs writer --tail=200 >&2 || true
  return 1
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

echo "Starting kafka, timescaledb, and writer..."
docker compose up --build -d kafka timescaledb

echo "Bootstrapping Kafka topics..."
sh ./infra/kafka/create-topics.sh

require_topic "audio.metadata"
require_topic "audio.segment.ready"
require_topic "audio.features"
require_topic "system.metrics"
require_topic "audio.dlq"

echo "Starting writer after topic bootstrap..."
docker compose up --build -d writer
sleep 5

echo "Publishing fake metadata and features..."
docker compose run --rm --entrypoint python writer -m event_driven_audio_analytics.smoke.publish_fake_events

wait_for_query \
  "SELECT COUNT(*) FROM track_metadata WHERE run_id = 'demo-run' AND track_id = 2;" \
  "1"
wait_for_query \
  "SELECT COUNT(*) FROM audio_features WHERE run_id = 'demo-run' AND track_id = 2 AND segment_idx = 0;" \
  "1"
wait_for_query \
  "SELECT COUNT(*) FROM run_checkpoints WHERE consumer_group = 'event-driven-audio-analytics-writer' AND topic_name IN ('audio.metadata', 'audio.features');" \
  "2"

echo "Replaying the same fake events to verify idempotent feature writes..."
docker compose run --rm --entrypoint python writer -m event_driven_audio_analytics.smoke.publish_fake_events

wait_for_query \
  "SELECT COUNT(*) FROM track_metadata WHERE run_id = 'demo-run' AND track_id = 2;" \
  "1"
wait_for_query \
  "SELECT COUNT(*) FROM audio_features WHERE run_id = 'demo-run' AND track_id = 2 AND segment_idx = 0;" \
  "1"

echo "Writer smoke flow passed."
