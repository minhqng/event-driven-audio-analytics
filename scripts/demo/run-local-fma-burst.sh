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

metadata_csv_host="tests/fixtures/audio/tracks.csv"
audio_root_host="tests/fixtures/audio/fma_small"
metadata_csv_container="/app/tests/fixtures/audio/tracks.csv"
audio_root_container="/app/tests/fixtures/audio/fma_small"
run_id="${RUN_ID:-fma-small-live}"
max_tracks="${INGESTION_MAX_TRACKS:-100}"
track_id_allowlist="${TRACK_ID_ALLOWLIST-}"

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
docker compose run --rm --no-deps --entrypoint sh ingestion \
  -c "rm -rf /app/artifacts/runs/$run_id" >/dev/null

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
