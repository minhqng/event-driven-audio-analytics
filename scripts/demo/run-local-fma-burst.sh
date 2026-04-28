#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../.."

require_file() {
  path="$1"
  label="$2"
  if [ ! -f "$path" ]; then
    echo "$label is missing. Expected repo-local path: $path" >&2
    exit 1
  fi
}

require_dir() {
  path="$1"
  label="$2"
  if [ ! -d "$path" ]; then
    echo "$label is missing. Expected repo-local path: $path" >&2
    exit 1
  fi
}

metadata_csv_host="${LOCAL_FMA_METADATA_CSV_HOST:-data/local/fma_metadata/tracks.csv}"
audio_root_host="${LOCAL_FMA_AUDIO_ROOT_HOST:-data/local/fma_small}"
metadata_csv_container="${LOCAL_FMA_METADATA_CSV:-/app/data/local/fma_metadata/tracks.csv}"
audio_root_container="${LOCAL_FMA_AUDIO_ROOT:-/app/data/local/fma_small}"
run_id="${RUN_ID:-fma-small-live}"
max_tracks="${INGESTION_MAX_TRACKS:-100}"
track_id_allowlist="${TRACK_ID_ALLOWLIST-}"

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

require_file "$metadata_csv_host" "Repo-local FMA metadata CSV"
require_dir "$audio_root_host" "Repo-local FMA audio root"

echo "Validating docker compose config..."
docker compose config >/dev/null

echo "Verifying live stack services..."
running_services="$(docker compose ps --services --status running)"
for service in kafka timescaledb grafana processing writer; do
  if ! printf '%s\n' "$running_services" | grep -qx "$service"; then
    echo "Required service '$service' is not running. Start the stack with './run-demo.sh' first." >&2
    exit 1
  fi
done

echo "Ensuring Kafka topics exist..."
sh ./infra/kafka/create-topics.sh

echo "Cleaning prior artifacts for run_id=$run_id..."
cleanup_run_artifacts "$run_id"

echo "Running repo-local FMA burst run_id=$run_id max_tracks=$max_tracks..."
docker compose run --rm --no-deps \
  -e RUN_ID="$run_id" \
  -e METADATA_CSV_PATH="$metadata_csv_container" \
  -e AUDIO_ROOT_PATH="$audio_root_container" \
  -e TRACK_ID_ALLOWLIST="$track_id_allowlist" \
  -e INGESTION_MAX_TRACKS="$max_tracks" \
  ingestion

echo "Repo-local FMA burst completed."
echo "Recommended dashboard URLs:"
echo "  http://localhost:3000/d/audio-quality/audio-quality?from=now-15m&to=now"
echo "  http://localhost:3000/d/system-health/system-health?from=now-15m&to=now"
