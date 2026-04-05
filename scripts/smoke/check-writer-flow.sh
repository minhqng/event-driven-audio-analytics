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

run_sql() {
  sql="$1"

  docker compose exec -T timescaledb \
    psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-audio_analytics}" -d "${POSTGRES_DB:-audio_analytics}" -tAc "$sql" >/dev/null
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
docker compose build writer
docker compose run --rm --no-deps writer preflight
docker compose up -d --no-deps writer
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

echo "Seeding duplicate run_total system.metrics rows across multiple Timescale chunks..."
run_sql "DELETE FROM system_metrics WHERE run_id = 'demo-run' AND service_name = 'ingestion' AND metric_name = 'tracks_total' AND labels_json = '{\"scope\":\"run_total\"}'::jsonb;"
run_sql "DELETE FROM run_checkpoints WHERE consumer_group = 'event-driven-audio-analytics-writer' AND topic_name = 'system.metrics';"
run_sql "INSERT INTO system_metrics (ts, run_id, service_name, metric_name, metric_value, labels_json, unit) VALUES ('2024-01-01T00:00:00Z', 'demo-run', 'ingestion', 'tracks_total', 1.0, '{\"scope\":\"run_total\"}'::jsonb, 'count');"
run_sql "INSERT INTO system_metrics (ts, run_id, service_name, metric_name, metric_value, labels_json, unit) VALUES ('2025-02-01T00:00:00Z', 'demo-run', 'ingestion', 'tracks_total', 2.0, '{\"scope\":\"run_total\"}'::jsonb, 'count');"

wait_for_query \
  "SELECT COUNT(*) FROM system_metrics WHERE run_id = 'demo-run' AND service_name = 'ingestion' AND metric_name = 'tracks_total' AND labels_json = '{\"scope\":\"run_total\"}'::jsonb;" \
  "2"
wait_for_query \
  "SELECT CASE WHEN COUNT(DISTINCT tableoid) >= 2 THEN 'ok' ELSE 'not-ok' END FROM system_metrics WHERE run_id = 'demo-run' AND service_name = 'ingestion' AND metric_name = 'tracks_total' AND labels_json = '{\"scope\":\"run_total\"}'::jsonb;" \
  "ok"

echo "Publishing run_total system.metrics fixture to trigger duplicate repair..."
docker compose run --rm --entrypoint python writer -m event_driven_audio_analytics.smoke.publish_fake_events --only-run-total-metric

wait_for_query \
  "SELECT COUNT(*) FROM system_metrics WHERE run_id = 'demo-run' AND service_name = 'ingestion' AND metric_name = 'tracks_total' AND labels_json = '{\"scope\":\"run_total\"}'::jsonb;" \
  "1"
wait_for_query \
  "SELECT COUNT(*) FROM system_metrics WHERE run_id = 'demo-run' AND service_name = 'ingestion' AND metric_name = 'tracks_total' AND labels_json = '{\"scope\":\"run_total\"}'::jsonb AND metric_value = 5.0 AND unit = 'count' AND to_char(ts AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') = '2026-04-03T00:00:00Z';" \
  "1"
wait_for_query \
  "SELECT COUNT(*) FROM run_checkpoints WHERE consumer_group = 'event-driven-audio-analytics-writer' AND topic_name = 'system.metrics';" \
  "1"

echo "Writer smoke flow passed."
