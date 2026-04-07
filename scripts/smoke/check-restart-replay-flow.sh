#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../.."

effective_run_id="${RUN_ID:-week8-replay}"
evidence_root_host="artifacts/demo/week8"
baseline_path_host="$evidence_root_host/restart-replay-baseline.json"
summary_path_host="$evidence_root_host/restart-replay-summary.json"
preflight_notes_host="$evidence_root_host/preflight-fail-fast.txt"
baseline_path_container="/app/artifacts/demo/week8/restart-replay-baseline.json"
summary_path_container="/app/artifacts/demo/week8/restart-replay-summary.json"

resolve_run_cleanup_path() {
  run_id="$1"

  if [ -z "$run_id" ] || [ -z "$(printf '%s' "$run_id" | tr -d '[:space:]')" ]; then
    echo "RUN_ID must not be empty or whitespace." >&2
    return 1
  fi
  case "$run_id" in
    "."|".."|*/*|*\\*|*:*)
      echo "RUN_ID must be a single relative path segment for cleanup under artifacts/runs." >&2
      return 1
      ;;
  esac

  mkdir -p artifacts/runs
  artifacts_runs_root="$(cd artifacts/runs && pwd -P)"
  cleanup_target="$artifacts_runs_root/$run_id"

  case "$cleanup_target" in
    "$artifacts_runs_root"/*)
      printf '%s\n' "$cleanup_target"
      ;;
    *)
      echo "Resolved run cleanup path escaped artifacts/runs." >&2
      return 1
      ;;
  esac
}

require_topic() {
  topic_name="$1"

  if ! docker compose exec -T kafka /opt/bitnami/kafka/bin/kafka-topics.sh \
    --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}" \
    --list | grep -qx "$topic_name"; then
    echo "Missing expected Kafka topic: $topic_name" >&2
    exit 1
  fi
}

wait_for_kafka_ready() {
  attempts=0
  while :; do
    if docker compose exec -T kafka /opt/bitnami/kafka/bin/kafka-topics.sh \
      --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}" \
      --list >/dev/null 2>&1; then
      return 0
    fi

    attempts=$((attempts + 1))
    if [ "$attempts" -ge 30 ]; then
      echo "Timed out waiting for Kafka readiness." >&2
      exit 1
    fi
    sleep 2
  done
}

wait_for_db_ready() {
  attempts=0
  while :; do
    if docker compose exec -T timescaledb \
      psql -U "${POSTGRES_USER:-audio_analytics}" \
      -d "${POSTGRES_DB:-audio_analytics}" \
      -tAc "SELECT 1;" >/dev/null 2>&1; then
      return 0
    fi

    attempts=$((attempts + 1))
    if [ "$attempts" -ge 30 ]; then
      echo "Timed out waiting for TimescaleDB readiness." >&2
      exit 1
    fi
    sleep 2
  done
}

assert_running_services() {
  running_services="$(docker compose ps --services --status running)"
  for service_name in "$@"; do
    if ! printf '%s\n' "$running_services" | grep -qx "$service_name"; then
      echo "Service is not running after startup/restart: $service_name" >&2
      docker compose logs "$service_name" >&2 || true
      exit 1
    fi
  done
}

assert_expected_preflight_failure() {
  service_name="$1"
  expected_pattern="$2"

  set +e
  output="$(docker compose run --rm --no-deps "$service_name" preflight 2>&1)"
  exit_code=$?
  set -e

  {
    printf '===== %s preflight before topic bootstrap =====\n' "$service_name"
    printf '%s\n' "$output"
  } >>"$preflight_notes_host"

  printf '%s\n' "$output"

  if [ "$exit_code" -eq 0 ]; then
    echo "Expected $service_name preflight to fail before topic bootstrap." >&2
    exit 1
  fi
  if ! printf '%s\n' "$output" | grep -Eiq "$expected_pattern"; then
    echo "Unexpected $service_name preflight failure output." >&2
    exit 1
  fi
}

echo "Resetting local stack..."
docker compose down --remove-orphans

echo "Cleaning prior restart/replay evidence..."
run_cleanup_host="$(resolve_run_cleanup_path "$effective_run_id")"
rm -rf "$evidence_root_host" "$run_cleanup_host"
mkdir -p "$evidence_root_host"
: >"$preflight_notes_host"

echo "Building ingestion, processing, writer, and pytest images..."
docker compose build ingestion processing writer pytest

echo "Starting Kafka and TimescaleDB without topic bootstrap..."
docker compose up --build -d kafka timescaledb
wait_for_kafka_ready
wait_for_db_ready

echo "Checking fail-fast preflights before topic bootstrap..."
assert_expected_preflight_failure "ingestion" "missing required ingestion topics"
assert_expected_preflight_failure "processing" "missing required processing topics"
assert_expected_preflight_failure "writer" "missing required writer topics"

echo "Bootstrapping Kafka topics..."
sh ./infra/kafka/create-topics.sh
require_topic "audio.metadata"
require_topic "audio.segment.ready"
require_topic "audio.features"
require_topic "system.metrics"

echo "Running healthy preflights after topic bootstrap..."
docker compose run --rm --no-deps ingestion preflight
docker compose run --rm --no-deps processing preflight
docker compose run --rm --no-deps writer preflight

echo "Starting long-lived processing and writer services..."
docker compose up -d --no-deps processing writer
sleep 5
assert_running_services processing writer

echo "Running first bounded ingestion pass for run_id=$effective_run_id..."
docker compose run --rm --no-deps \
  -e RUN_ID="$effective_run_id" \
  ingestion

echo "Capturing healthy baseline verification..."
docker compose run --rm --no-deps \
  -e RUN_ID="$effective_run_id" \
  --entrypoint python \
  pytest \
  -m event_driven_audio_analytics.smoke.verify_writer_flow >/dev/null

echo "Writing restart/replay baseline snapshot..."
docker compose run --rm --no-deps \
  -e RUN_ID="$effective_run_id" \
  --entrypoint python \
  pytest \
  -m event_driven_audio_analytics.smoke.verify_restart_replay_flow \
  capture \
  --output "$baseline_path_container" >/dev/null

echo "Restarting processing and writer before replay..."
docker compose restart processing writer
sleep 5
assert_running_services processing writer

echo "Re-running ingestion with the same run_id=$effective_run_id..."
docker compose run --rm --no-deps \
  -e RUN_ID="$effective_run_id" \
  ingestion

echo "Verifying replay-stable sink rows, metrics, checkpoints, and processing state..."
docker compose run --rm --no-deps \
  -e RUN_ID="$effective_run_id" \
  --entrypoint python \
  pytest \
  -m event_driven_audio_analytics.smoke.verify_restart_replay_flow \
  verify \
  --baseline "$baseline_path_container" \
  --output "$summary_path_container" >/dev/null

assert_running_services processing writer

processing_logs="$(docker compose logs processing)"
writer_logs="$(docker compose logs writer)"
if printf '%s\n' "$processing_logs" | grep -q 'Processing failed'; then
  echo "Unexpected processing failure logs appeared during restart/replay verification." >&2
  exit 1
fi
if printf '%s\n' "$writer_logs" | grep -q 'Writer failed'; then
  echo "Unexpected writer failure logs appeared during restart/replay verification." >&2
  exit 1
fi

test -f "$baseline_path_host"
test -f "$summary_path_host"
test -f "$preflight_notes_host"

echo "Restart / replay smoke flow passed."
echo "Baseline snapshot: $baseline_path_host"
echo "Replay summary: $summary_path_host"
echo "Fail-fast preflight notes: $preflight_notes_host"
