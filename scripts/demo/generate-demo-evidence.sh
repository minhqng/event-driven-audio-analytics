#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../.."

demo_evidence_root="artifacts/evidence/final-demo"
evidence_index_path="$demo_evidence_root/evidence-index.md"

write_demo_evidence_index() {
  cat >"$evidence_index_path" <<'EOF'
# Final Demo Evidence Index

This directory is the final handoff anchor for the bounded PoC evidence set.

## Restart/Replay Evidence

- `restart-replay/restart-replay-baseline.json` captures the first bounded broker-backed run before replay.
- `restart-replay/restart-replay-summary.json` captures the same `run_id` after restarting `processing` and `writer`, then rerunning `ingestion`.
- `restart-replay/preflight-fail-fast.txt` records the expected startup failures before Kafka topics are bootstrapped.

## Review/Dashboard Evidence

The review/dashboard artifacts are generated under `artifacts/evidence/final-demo/review-dashboard/`:

- `review-dashboard/review-dashboard-summary.json`
- `review-dashboard/review-api.json`
- `review-dashboard/grafana-api.json`
- `review-dashboard/review-console.png`
- `review-dashboard/audio-quality-dashboard.png`
- `review-dashboard/system-health-dashboard.png`
- `review-dashboard/review-dashboard-notes.md`

## Practical Reading Order

- Use the review artifact pack first to explain the run, track, and segment story.
- Use the restart/replay artifacts next to explain startup gating and replay safety.
- Use the review/dashboard artifacts last to explain TimescaleDB persistence, Grafana provisioning, and panel interpretation.
- Treat this as bounded PoC evidence only; it is not benchmark-scale or production-readiness evidence.
EOF
}

echo "Running restart/replay evidence path..."
sh ./scripts/smoke/check-restart-replay-flow.sh

echo "Running dashboard evidence path..."
sh ./scripts/demo/generate-dashboard-evidence.sh

mkdir -p "$demo_evidence_root"
write_demo_evidence_index

echo "Final demo evidence is ready."
echo "Restart/replay artifacts: $demo_evidence_root/restart-replay"
echo "Review/dashboard artifacts: artifacts/evidence/final-demo/review-dashboard"
echo "Evidence index: $evidence_index_path"
