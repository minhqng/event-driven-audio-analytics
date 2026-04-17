#!/usr/bin/env sh
set -eu

wait_http_ready() {
  uri="$1"
  timeout_s="${2:-60}"
  deadline=$(( $(date +%s) + timeout_s ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if curl -fsS "$uri" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for HTTP readiness: $uri" >&2
  exit 1
}

wait_review_preflight() {
  timeout_s="${1:-60}"
  deadline=$(( $(date +%s) + timeout_s ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if docker compose exec -T review python -m event_driven_audio_analytics.review.app preflight >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for review preflight." >&2
  exit 1
}

wait_review_view_ready() {
  timeout_s="${1:-60}"
  deadline=$(( $(date +%s) + timeout_s ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if docker compose exec -T timescaledb \
      psql -U "${POSTGRES_USER:-audio_analytics}" -d "${POSTGRES_DB:-audio_analytics}" \
      -c "SELECT 1 FROM vw_review_tracks LIMIT 1;" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for vw_review_tracks to become selectable." >&2
  exit 1
}

echo "Starting event-driven-audio-analytics demo stack..."
docker compose up --build -d kafka timescaledb grafana

echo "Creating Kafka topics..."
sh ./infra/kafka/create-topics.sh

echo "Starting processing, writer, and review services..."
docker compose up -d --no-deps processing writer review

echo "Waiting for the review console..."
wait_http_ready "http://localhost:${REVIEW_PORT:-8080}/healthz" 90
echo "Running review preflight..."
wait_review_preflight 90
echo "Checking vw_review_tracks..."
wait_review_view_ready 60

echo "Demo bootstrap completed."
echo "Grafana: http://localhost:${GRAFANA_PORT:-3000}"
echo "Run Review Console: http://localhost:${REVIEW_PORT:-8080}"
echo "TimescaleDB: localhost:${TIMESCALEDB_PORT:-5432}"
echo "Kafka bootstrap (host): localhost:${KAFKA_BROKER_PORT:-9092}"
echo "Kafka bootstrap (containers): ${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}"
echo "Grafana auto-loads the file-provisioned TimescaleDB datasource and the dashboard JSON."
echo "The review service is read-only and serves run/track/segment inspection from persisted DB rows plus claim-check artifacts."
echo "Run 'bash ./scripts/demo/generate-dashboard-evidence.sh' for the dashboard demo path."
echo "Run 'bash ./scripts/demo/generate-demo-evidence.sh' for the full final evidence bundle."
echo "Run 'bash ./scripts/demo/run-local-fma-burst.sh' after placing 'tests/fixtures/audio/tracks.csv' and 'tests/fixtures/audio/fma_small/...' for a bounded repo-local FMA-small burst."
echo "See './docs/runbooks/dashboard-demo.md' for the live dashboard sequence and panel interpretation."
echo "Run 'bash ./scripts/smoke/check-ingestion-flow.sh' for the broker-backed ingestion smoke path."
echo "Run 'bash ./scripts/smoke/check-processing-flow.sh' for the broker-backed processing smoke path."
echo "Run 'bash ./scripts/smoke/check-processing-writer-flow.sh' for the broker-backed persistence smoke path."
echo "Run 'bash ./scripts/smoke/check-pytest.sh' for the official containerized pytest path."
