#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../.."

assert_file_exists() {
  if [ ! -f "$1" ]; then
    echo "Expected file missing: $1" >&2
    exit 1
  fi
}

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

find_browser() {
  for candidate in google-chrome chromium chromium-browser microsoft-edge msedge; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  echo "No supported headless browser executable was found for Grafana screenshots." >&2
  exit 1
}

capture_dashboard_screenshot() {
  browser_path="$1"
  url="$2"
  output_path="$3"
  "$browser_path" \
    --headless=new \
    --disable-gpu \
    --hide-scrollbars \
    --window-size=1600,1250 \
    --run-all-compositor-stages-before-draw \
    --virtual-time-budget=15000 \
    "--screenshot=$output_path" \
    "$url" >/dev/null 2>&1
}

write_demo_artifact_notes() {
  output_path="$1"
  cat >"$output_path" <<'EOF'
# Dashboard Demo Artifact Notes

## Audio Quality Dashboard

- `audio_quality.png` captures the `Audio Quality` dashboard with the recent-demo `now-6h` time window.
- `Segment RMS Over Time` proves the high-energy run stays closer to `0 dB` than the silent-oriented run.
- `Silent Segment Ratio By Run` proves the silent-oriented run contains silent segments while the high-energy run does not.
- `Persisted Segment Count By Run` proves validated runs reached `audio_features` persistence and the validation-failure run did not.
- `Validation Outcomes By Run` proves the validation-failure case is an ingestion-side `silent` rejection, not a hidden downstream failure.
- `Run Quality Summary Table` is the compact reporting table for slide and report handoff.

## System Health Dashboard

- `system_health.png` captures the `System Health` dashboard with the same recent-demo time window.
- `Persisted Segment Throughput` proves the bounded demo produced real sink-side throughput.
- `Processing Latency Over Time` and `Writer DB Latency By Topic` prove processing and persistence latency stayed observable on real data.
- `Claim-Check Artifact Write Latency` proves the claim-check boundary has measurable artifact-write cost.
- `Track Validation Error Rate By Run` and `Operational Summary Table` prove the validation-failure run is visible as an operational signal instead of disappearing silently.

## Supporting Files

- `dashboard-demo-summary.json` is the authoritative machine-readable verification output from `verify_dashboard_demo`.
- `grafana-api.json` proves the dashboards were auto-loaded through Grafana provisioning rather than click-ops.
EOF
}

invoke_demo_run() {
  run_id="$1"
  track_id="$2"
  metadata_csv_path="$3"
  audio_root_path="$4"

  echo "Running ingestion for $run_id (track_id=$track_id)..."
  docker compose run --rm --no-deps \
    -e RUN_ID="$run_id" \
    -e METADATA_CSV_PATH="$metadata_csv_path" \
    -e AUDIO_ROOT_PATH="$audio_root_path" \
    -e TRACK_ID_ALLOWLIST="$track_id" \
    -e INGESTION_MAX_TRACKS=1 \
    ingestion
}

grafana_port="${GRAFANA_PORT:-3000}"
demo_input_root_host="artifacts/demo_inputs/week7"
evidence_root_host="artifacts/demo/week7"
demo_input_root_container="/app/artifacts/demo_inputs/week7"
metadata_csv_container="$demo_input_root_container/metadata.csv"
audio_root_container="$demo_input_root_container/fma_small"

echo "Validating docker compose config..."
docker compose config >/dev/null

echo "Resetting local stack..."
docker compose down --remove-orphans

echo "Cleaning previous dashboard evidence..."
rm -rf "$demo_input_root_host" "$evidence_root_host" artifacts/runs/week7-high-energy artifacts/runs/week7-silent-oriented artifacts/runs/week7-validation-failure
mkdir -p "$evidence_root_host"

echo "Building ingestion, processing, and writer images..."
docker compose build ingestion processing writer

echo "Preparing deterministic dashboard demo inputs inside the ingestion image..."
docker compose run --rm --no-deps --entrypoint python \
  ingestion \
  -m event_driven_audio_analytics.smoke.prepare_week7_inputs \
  --output-root "$demo_input_root_container"

echo "Starting Kafka, TimescaleDB, and Grafana..."
docker compose up --build -d kafka timescaledb grafana

echo "Bootstrapping Kafka topics..."
sh ./infra/kafka/create-topics.sh

echo "Starting processing and writer services..."
docker compose up -d --no-deps processing writer

echo "Waiting for Grafana..."
wait_http_ready "http://localhost:$grafana_port/api/health" 90

invoke_demo_run "week7-high-energy" "910001" "$metadata_csv_container" "$audio_root_container"
sleep 3
invoke_demo_run "week7-silent-oriented" "910002" "$metadata_csv_container" "$audio_root_container"
sleep 3
invoke_demo_run "week7-validation-failure" "910003" "$metadata_csv_container" "$audio_root_container"

echo "Verifying dashboard data in TimescaleDB..."
docker compose exec -T writer python -m event_driven_audio_analytics.smoke.verify_dashboard_demo > "$evidence_root_host/dashboard-demo-summary.json"

echo "Checking provisioned dashboards through the Grafana API..."
audio_dashboard="$(curl -fsS "http://localhost:$grafana_port/api/dashboards/uid/audio-quality")"
system_dashboard="$(curl -fsS "http://localhost:$grafana_port/api/dashboards/uid/system-health")"
search_snapshot="$(curl -fsS "http://localhost:$grafana_port/api/search?query=Quality")"
printf '{\n  "search": %s,\n  "audio_quality": %s,\n  "system_health": %s\n}\n' "$search_snapshot" "$audio_dashboard" "$system_dashboard" > "$evidence_root_host/grafana-api.json"

browser_path="$(find_browser)"
echo "Capturing Grafana screenshots with $browser_path..."
capture_dashboard_screenshot "$browser_path" "http://localhost:$grafana_port/d/audio-quality/audio-quality?from=now-6h&to=now&kiosk" "$evidence_root_host/audio_quality.png"
capture_dashboard_screenshot "$browser_path" "http://localhost:$grafana_port/d/system-health/system-health?from=now-6h&to=now&kiosk" "$evidence_root_host/system_health.png"
write_demo_artifact_notes "$evidence_root_host/demo-artifact-notes.md"

assert_file_exists "$evidence_root_host/dashboard-demo-summary.json"
assert_file_exists "$evidence_root_host/grafana-api.json"
assert_file_exists "$evidence_root_host/audio_quality.png"
assert_file_exists "$evidence_root_host/system_health.png"
assert_file_exists "$evidence_root_host/demo-artifact-notes.md"

echo "Dashboard demo evidence is ready."
echo "Summary: $evidence_root_host/dashboard-demo-summary.json"
echo "Grafana API snapshot: $evidence_root_host/grafana-api.json"
echo "Screenshots: $evidence_root_host/audio_quality.png and $evidence_root_host/system_health.png"
echo "Artifact notes: $evidence_root_host/demo-artifact-notes.md"
