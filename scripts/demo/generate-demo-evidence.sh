#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../.."

demo_evidence_root="artifacts/evidence/final-demo"
evidence_index_path="$demo_evidence_root/evidence-index.md"
dataset_evidence_root="$demo_evidence_root/dataset-exports"
dataset_summary_path="$dataset_evidence_root/dataset-export-summary.json"
dataset_summary_tmp="$dataset_summary_path.tmp"
dataset_run_ids="demo-high-energy demo-silent-oriented demo-validation-failure"

assert_path_exists() {
  if [ ! -e "$1" ]; then
    echo "Expected path missing: $1" >&2
    exit 1
  fi
}

write_demo_evidence_index() {
  cat >"$evidence_index_path" <<'EOF'
# Final Demo Evidence Index

This directory is the final handoff anchor for the bounded PoC evidence set.

## Review/Dashboard Evidence

The review/dashboard artifacts are generated under `artifacts/evidence/final-demo/review-dashboard/`:

- `review-dashboard/review-dashboard-summary.json`
- `review-dashboard/review-api.json`
- `review-dashboard/grafana-api.json`
- `review-dashboard/review-console.png`
- `review-dashboard/audio-quality-dashboard.png`
- `review-dashboard/system-health-dashboard.png`
- `review-dashboard/review-dashboard-notes.md`

## Dataset Export Evidence

- `dataset-exports/dataset-export-summary.json` verifies the deterministic dataset bundles for all demo runs.
- `artifacts/datasets/demo-high-energy/` is the accepted high-energy dataset bundle.
- `artifacts/datasets/demo-silent-oriented/` is the accepted silent-oriented dataset bundle.
- `artifacts/datasets/demo-validation-failure/` is the rejected-track validation-failure dataset bundle.

## Restart/Replay Evidence

- `restart-replay/restart-replay-baseline.json` captures the first bounded broker-backed run before replay.
- `restart-replay/restart-replay-summary.json` captures the same `run_id` after restarting `processing` and `writer`, then rerunning `ingestion`.
- `restart-replay/preflight-fail-fast.txt` records the expected startup failures before Kafka topics are bootstrapped.

## Practical Reading Order

- Use the review artifact pack first to explain the run, track, and segment story.
- Use the Grafana artifacts next to corroborate TimescaleDB persistence and panel interpretation.
- Use the dataset export summary and run bundles third to show the final FMA-Small analytics/dataset outputs.
- Use the restart/replay artifacts last to explain startup gating and replay safety.
- Treat this as bounded PoC evidence only; it is not benchmark-scale or production-readiness evidence.
EOF
}

echo "Cleaning prior dataset export evidence..."
rm -rf "$dataset_evidence_root" \
  artifacts/datasets/demo-high-energy \
  artifacts/datasets/demo-silent-oriented \
  artifacts/datasets/demo-validation-failure
mkdir -p "$dataset_evidence_root"
rm -f "$dataset_summary_tmp"

echo "Running restart/replay evidence path..."
sh ./scripts/smoke/check-restart-replay-flow.sh

echo "Running dashboard evidence path..."
sh ./scripts/demo/generate-dashboard-evidence.sh

echo "Building dataset-exporter image..."
docker compose build dataset-exporter

for run_id in $dataset_run_ids; do
  echo "Exporting dataset bundle for $run_id..."
  docker compose run --rm --no-deps dataset-exporter export --run-id "$run_id" >/dev/null
done

echo "Verifying exported dataset bundles..."
docker compose run --rm --no-deps --entrypoint python \
  dataset-exporter \
  -m event_driven_audio_analytics.smoke.verify_dataset_demo_outputs > "$dataset_summary_tmp"
mv "$dataset_summary_tmp" "$dataset_summary_path"

assert_path_exists "$dataset_summary_path"
for run_id in $dataset_run_ids; do
  assert_path_exists "artifacts/datasets/$run_id"
done

mkdir -p "$demo_evidence_root"
write_demo_evidence_index

echo "Final demo evidence is ready."
echo "Restart/replay artifacts: $demo_evidence_root/restart-replay"
echo "Review/dashboard artifacts: artifacts/evidence/final-demo/review-dashboard"
echo "Dataset export summary: $dataset_summary_path"
echo "Dataset bundles: artifacts/datasets/demo-high-energy, artifacts/datasets/demo-silent-oriented, artifacts/datasets/demo-validation-failure"
echo "Evidence index: $evidence_index_path"
