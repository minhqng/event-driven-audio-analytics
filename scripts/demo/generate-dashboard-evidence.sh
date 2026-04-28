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

assert_pinned_run_order() {
  expected="$1"
  actual="$(docker compose exec -T review python -c 'import json; from urllib.request import urlopen; payload=json.load(urlopen("http://127.0.0.1:8080/api/runs?demo_mode=true&limit=10")); print(",".join(item["run_id"] for item in payload["items"][:3]))')"
  if [ "$actual" != "$expected" ]; then
    echo "Pinned demo order mismatch. Expected '$expected' but got '$actual'." >&2
    exit 1
  fi
}

find_browser() {
  for candidate in google-chrome chromium chromium-browser microsoft-edge msedge; do
    if command -v "$candidate" >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  echo "No supported headless browser executable was found for review/Grafana screenshots." >&2
  exit 1
}

dump_page_dom() {
  browser_path="$1"
  url="$2"
  "$browser_path" \
    --headless=new \
    --disable-gpu \
    --hide-scrollbars \
    --window-size=1600,1250 \
    --run-all-compositor-stages-before-draw \
    --virtual-time-budget=15000 \
    --dump-dom \
    "$url" 2>/dev/null
}

capture_page_screenshot() {
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

wait_review_dom_ready() {
  browser_path="$1"
  url="$2"
  expected_run_id="$3"
  expected_track_id="$4"
  timeout_s="${5:-60}"
  deadline=$(( $(date +%s) + timeout_s ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    dom="$(dump_page_dom "$browser_path" "$url" || true)"
    if printf '%s' "$dom" | grep -F 'data-review-ready="true"' >/dev/null 2>&1 \
      && printf '%s' "$dom" | grep -F "data-selected-run-id=\"$expected_run_id\"" >/dev/null 2>&1 \
      && printf '%s' "$dom" | grep -F "data-selected-track-id=\"$expected_track_id\"" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for review DOM readiness: $url" >&2
  exit 1
}

write_demo_artifact_notes() {
  output_path="$1"
  cat >"$output_path" <<'EOF'
# Demo Artifact Notes

## Run Review Console

- `review-console.png` captures the read-only `Run Review Console` in demo mode, pinned to `demo-high-energy`.
- The review console is the primary demo surface: it shows run state, validation outcomes, track summaries, segment artifacts, and secondary runtime proof without forcing the audience into Grafana first.
- `review-api.json` is the authoritative machine-readable verification output from `verify_review_api`.

## Audio Quality Dashboard

- `audio-quality-dashboard.png` captures the `Audio Quality` dashboard with the recent-demo `now-6h` time window.
- `Segment RMS Over Time` proves the high-energy run stays closer to `0 dB` than the silent-oriented run.
- `Silent Segment Ratio By Run` proves the silent-oriented run contains silent segments while the high-energy run does not.
- `Persisted Segment Count By Run` proves validated runs reached `audio_features` persistence and the validation-failure run did not.
- `Validation Outcomes By Run` proves the validation-failure case is an ingestion-side `silent` rejection, not a hidden downstream failure.
- `Run Quality Summary Table` is the compact reporting table for slide and report handoff.

## System Health Dashboard

- `system-health-dashboard.png` captures the `System Health` dashboard with the same recent-demo time window.
- `Persisted Segment Throughput` proves the bounded demo produced real sink-side throughput.
- `Processing Latency Over Time` and `Writer DB Latency By Topic` prove processing and persistence latency stayed observable on real data.
- `Claim-Check Artifact Write Latency` proves the claim-check boundary has measurable artifact-write cost.
- `Track Validation Error Rate By Run` and `Operational Summary Table` prove the validation-failure run is visible as an operational signal instead of disappearing silently.

## Supporting Files

- `review-dashboard-summary.json` is the authoritative machine-readable verification output from `verify_dashboard_demo`.
- `grafana-api.json` proves the dashboards were auto-loaded through Grafana provisioning rather than click-ops.
- `review-api.json` proves the new review surface is reachable and exposes the deterministic demo runs with track/segment detail.
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
review_port="${REVIEW_PORT:-8080}"
grafana_user="${GRAFANA_ADMIN_USER:-admin}"
grafana_password="${GRAFANA_ADMIN_PASSWORD:-admin}"
demo_input_root_host="artifacts/demo-inputs/review-demo"
evidence_root_host="artifacts/evidence/final-demo/review-dashboard"
demo_input_root_container="/app/artifacts/demo-inputs/review-demo"
metadata_csv_container="$demo_input_root_container/metadata.csv"
audio_root_container="$demo_input_root_container/fma_small"

echo "Validating docker compose config..."
docker compose config >/dev/null

echo "Resetting local stack..."
docker compose down --remove-orphans

echo "Cleaning previous dashboard evidence..."
rm -rf "$demo_input_root_host" "$evidence_root_host" artifacts/runs/demo-high-energy artifacts/runs/demo-silent-oriented artifacts/runs/demo-validation-failure
mkdir -p "$evidence_root_host"

echo "Building ingestion, processing, writer, and review images..."
docker compose build ingestion processing writer review

echo "Preparing deterministic review demo inputs inside the ingestion image..."
docker compose run --rm --no-deps --entrypoint python \
  ingestion \
  -m event_driven_audio_analytics.smoke.prepare_review_demo_inputs \
  --output-root "$demo_input_root_container"

echo "Starting Kafka, TimescaleDB, and Grafana..."
docker compose up --build -d kafka timescaledb grafana

echo "Bootstrapping Kafka topics..."
sh ./infra/kafka/create-topics.sh

echo "Starting processing, writer, and review services..."
docker compose up -d --no-deps processing writer review

echo "Waiting for Grafana..."
wait_http_ready "http://localhost:$grafana_port/api/health" 90
echo "Waiting for the review console..."
wait_http_ready "http://localhost:$review_port/healthz" 90
echo "Running review preflight..."
wait_review_preflight 90
echo "Checking vw_review_tracks..."
wait_review_view_ready 60

invoke_demo_run "demo-high-energy" "910001" "$metadata_csv_container" "$audio_root_container"
sleep 3
invoke_demo_run "demo-silent-oriented" "910002" "$metadata_csv_container" "$audio_root_container"
sleep 3
invoke_demo_run "demo-validation-failure" "910003" "$metadata_csv_container" "$audio_root_container"

echo "Verifying dashboard data in TimescaleDB..."
docker compose exec -T writer python -m event_driven_audio_analytics.smoke.verify_dashboard_demo > "$evidence_root_host/review-dashboard-summary.json"

echo "Verifying the review API..."
docker compose exec -T review python -m event_driven_audio_analytics.smoke.verify_review_api \
  --base-url "http://127.0.0.1:8080" > "$evidence_root_host/review-api.json"
echo "Verifying pinned demo ordering..."
assert_pinned_run_order "demo-high-energy,demo-silent-oriented,demo-validation-failure"

echo "Checking provisioned dashboards through the Grafana API..."
audio_dashboard="$(curl -fsS -u "$grafana_user:$grafana_password" "http://localhost:$grafana_port/api/dashboards/uid/audio-quality")"
system_dashboard="$(curl -fsS -u "$grafana_user:$grafana_password" "http://localhost:$grafana_port/api/dashboards/uid/system-health")"
search_snapshot="$(curl -fsS -u "$grafana_user:$grafana_password" "http://localhost:$grafana_port/api/search?query=Quality")"
printf '{\n  "search": %s,\n  "audio_quality": %s,\n  "system_health": %s\n}\n' "$search_snapshot" "$audio_dashboard" "$system_dashboard" > "$evidence_root_host/grafana-api.json"

browser_path="$(find_browser)"
echo "Capturing review and Grafana screenshots with $browser_path..."
review_url="http://localhost:$review_port/?demo=1&run_id=demo-high-energy&track_id=910001"
wait_review_dom_ready "$browser_path" "$review_url" "demo-high-energy" "910001" 90
capture_page_screenshot "$browser_path" "$review_url" "$evidence_root_host/review-console.png"
capture_page_screenshot "$browser_path" "http://localhost:$grafana_port/d/audio-quality/audio-quality?from=now-6h&to=now&kiosk" "$evidence_root_host/audio-quality-dashboard.png"
capture_page_screenshot "$browser_path" "http://localhost:$grafana_port/d/system-health/system-health?from=now-6h&to=now&kiosk" "$evidence_root_host/system-health-dashboard.png"
write_demo_artifact_notes "$evidence_root_host/review-dashboard-notes.md"

assert_file_exists "$evidence_root_host/review-dashboard-summary.json"
assert_file_exists "$evidence_root_host/grafana-api.json"
assert_file_exists "$evidence_root_host/review-api.json"
assert_file_exists "$evidence_root_host/review-console.png"
assert_file_exists "$evidence_root_host/audio-quality-dashboard.png"
assert_file_exists "$evidence_root_host/system-health-dashboard.png"
assert_file_exists "$evidence_root_host/review-dashboard-notes.md"

echo "Review/dashboard evidence is ready."
echo "Summary: $evidence_root_host/review-dashboard-summary.json"
echo "Review API snapshot: $evidence_root_host/review-api.json"
echo "Grafana API snapshot: $evidence_root_host/grafana-api.json"
echo "Screenshots: $evidence_root_host/review-console.png, $evidence_root_host/audio-quality-dashboard.png, and $evidence_root_host/system-health-dashboard.png"
echo "Artifact notes: $evidence_root_host/review-dashboard-notes.md"
