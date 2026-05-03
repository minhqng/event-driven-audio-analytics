#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../.."

evaluation_root_host="artifacts/evidence/final-demo/evaluation"
evaluation_root_container="/app/artifacts/evidence/final-demo/evaluation"
resource_root_host="$evaluation_root_host/resource-samples"
resource_root_container="$evaluation_root_container/resource-samples"
resource_sample_interval_s="${EVAL_RESOURCE_SAMPLE_INTERVAL_S:-2}"
artifact_read_sample_size="${EVAL_ARTIFACT_READ_SAMPLE_SIZE:-20}"
active_sampler_pid=""

stop_active_resource_sampler() {
  if [ -n "$active_sampler_pid" ]; then
    kill "$active_sampler_pid" 2>/dev/null || true
    wait "$active_sampler_pid" 2>/dev/null || true
    active_sampler_pid=""
  fi
}

trap stop_active_resource_sampler EXIT INT TERM

collect_summary() {
  scenario="$1"
  run_id="$2"
  status="$3"
  duration_s="$4"
  requested_tracks="$5"
  processing_replicas="$6"
  resource_samples_container="$7"
  skip_reason="$8"
  include_scaling="$9"

  set -- \
    --run-id "$run_id" \
    --scenario "$scenario" \
    --output-root "$evaluation_root_container" \
    --status "$status" \
    --processing-replicas "$processing_replicas" \
    --duration-s "$duration_s" \
    --resource-sample-interval-s "$resource_sample_interval_s" \
    --artifact-read-sample-size "$artifact_read_sample_size"
  if [ -n "$requested_tracks" ]; then
    set -- "$@" --requested-tracks "$requested_tracks"
  fi
  if [ -n "$resource_samples_container" ]; then
    set -- "$@" --resource-samples-jsonl "$resource_samples_container"
  fi
  if [ -n "$skip_reason" ]; then
    set -- "$@" --skip-reason "$skip_reason"
  fi
  if [ "$include_scaling" = "true" ]; then
    set -- "$@" --include-scaling
  fi

  docker compose run --rm --no-deps --entrypoint python pytest \
    -m event_driven_audio_analytics.evaluation.collect "$@" >/dev/null
}

start_resource_sampler() {
  output_path="$1"
  (
    while :; do
      docker stats --no-stream --format "{{json .}}" >> "$output_path"
      sleep "$resource_sample_interval_s"
    done
  ) &
  active_sampler_pid="$!"
}

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

run_bounded_scenario() {
  scenario="$1"
  run_id="$2"
  metadata_csv_container="$3"
  audio_root_container="$4"
  max_tracks="$5"
  track_id_allowlist="$6"
  processing_replicas="${7:-1}"
  include_scaling="${8:-false}"

  resource_samples_host="$resource_root_host/$run_id.jsonl"
  resource_samples_container="$resource_root_container/$run_id.jsonl"
  mkdir -p "$resource_root_host"
  rm -f "$resource_samples_host"

  echo "Running evaluation scenario=$scenario run_id=$run_id processing_replicas=$processing_replicas..."
  docker compose down --remove-orphans
  docker compose build ingestion processing writer pytest
  cleanup_run_artifacts "$run_id"
  docker compose up --build -d kafka timescaledb
  sh ./infra/kafka/create-topics.sh

  docker compose run --rm --no-deps writer preflight
  docker compose run --rm --no-deps processing preflight
  docker compose run --rm --no-deps ingestion preflight

  docker compose up -d --no-deps --scale "processing=$processing_replicas" processing writer
  sleep 5

  start_epoch="$(date +%s)"
  start_resource_sampler "$resource_samples_host"
  docker compose run --rm --no-deps \
    -e RUN_ID="$run_id" \
    -e METADATA_CSV_PATH="$metadata_csv_container" \
    -e AUDIO_ROOT_PATH="$audio_root_container" \
    -e TRACK_ID_ALLOWLIST="$track_id_allowlist" \
    -e INGESTION_MAX_TRACKS="$max_tracks" \
    ingestion

  docker compose run --rm --no-deps \
    -e RUN_ID="$run_id" \
    --entrypoint python \
    pytest \
    -m event_driven_audio_analytics.smoke.verify_writer_flow >/dev/null
  end_epoch="$(date +%s)"
  stop_active_resource_sampler

  duration_s="$(( end_epoch - start_epoch ))"
  if [ "$duration_s" -le 0 ]; then
    duration_s="1"
  fi
  collect_summary \
    "$scenario" \
    "$run_id" \
    "passed" \
    "$duration_s" \
    "$max_tracks" \
    "$processing_replicas" \
    "$resource_samples_container" \
    "" \
    "$include_scaling"
}

skip_scenario() {
  scenario="$1"
  run_id="$2"
  requested_tracks="$3"
  reason="$4"
  processing_replicas="${5:-1}"
  include_scaling="${6:-false}"
  collect_summary "$scenario" "$run_id" "skipped" "0" "$requested_tracks" "$processing_replicas" "" "$reason" "$include_scaling"
}

rm -rf "$evaluation_root_host"
mkdir -p "$evaluation_root_host"

fixture_metadata="/app/tests/fixtures/audio/smoke_tracks.csv"
fixture_audio_root="/app/tests/fixtures/audio/smoke_fma_small"
run_bounded_scenario \
  "deterministic-review-demo" \
  "eval-deterministic-review-demo" \
  "$fixture_metadata" \
  "$fixture_audio_root" \
  "2" \
  "2,666"

local_metadata_host="${LOCAL_FMA_METADATA_CSV_HOST:-data/local/fma_metadata/tracks.csv}"
local_audio_root_host="${LOCAL_FMA_AUDIO_ROOT_HOST:-data/local/fma_small}"
local_metadata_container="${LOCAL_FMA_METADATA_CSV:-/app/data/local/fma_metadata/tracks.csv}"
local_audio_root_container="${LOCAL_FMA_AUDIO_ROOT:-/app/data/local/fma_small}"

if [ -f "$local_metadata_host" ] && [ -d "$local_audio_root_host" ]; then
  run_bounded_scenario "fma-small-burst-5" "eval-fma-5" "$local_metadata_container" "$local_audio_root_container" "5" ""
  run_bounded_scenario "fma-small-burst-100" "eval-fma-100" "$local_metadata_container" "$local_audio_root_container" "100" ""
  for replicas in 1 2 3; do
    run_bounded_scenario "fma-small-scaling-r$replicas" "eval-scale-r$replicas" "$local_metadata_container" "$local_audio_root_container" "5" "" "$replicas" "true"
  done
else
  reason="local FMA-Small files were not found under data/local"
  skip_scenario "fma-small-burst-5" "eval-fma-5" "5" "$reason"
  skip_scenario "fma-small-burst-100" "eval-fma-100" "100" "$reason"
  for replicas in 1 2 3; do
    skip_scenario "fma-small-scaling-r$replicas" "eval-scale-r$replicas" "5" "$reason" "$replicas" "true"
  done
fi

if [ "${EVAL_ENABLE_FULL_FMA_SMALL:-false}" = "true" ]; then
  if [ -f "$local_metadata_host" ] && [ -d "$local_audio_root_host" ]; then
    run_bounded_scenario "fma-small-full-local-experiment" "eval-fma-full-local" "$local_metadata_container" "$local_audio_root_container" "" ""
  else
    skip_scenario "fma-small-full-local-experiment" "eval-fma-full-local" "" "full FMA-Small local experiment requested but local files were unavailable"
  fi
else
  skip_scenario "fma-small-full-local-experiment" "eval-fma-full-local" "" "EVAL_ENABLE_FULL_FMA_SMALL is not true"
fi

docker compose run --rm --no-deps --entrypoint python pytest \
  -m event_driven_audio_analytics.evaluation.report \
  --output-root "$evaluation_root_container" >/dev/null

for expected_output in \
  latency-summary.json \
  throughput-summary.json \
  resource-usage-summary.json \
  scaling-summary.json \
  evaluation-report.md; do
  if [ ! -f "$evaluation_root_host/$expected_output" ]; then
    echo "Expected evaluation output missing: $evaluation_root_host/$expected_output" >&2
    exit 1
  fi
done

docker compose down --remove-orphans
echo "Evaluation evidence written to $evaluation_root_host"
