#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../.."

demo_evidence_root="artifacts/demo/week8"
evidence_index_path="$demo_evidence_root/evidence-index.md"

write_demo_evidence_index() {
  cat >"$evidence_index_path" <<'EOF'
# Final Demo Evidence Index

This directory is the final handoff anchor for the bounded PoC evidence set.

## Reliability Evidence

- `restart-replay-baseline.json` captures the first bounded broker-backed run before replay.
- `restart-replay-summary.json` captures the same `run_id` after restarting `processing` and `writer`, then rerunning `ingestion`.
- `preflight-fail-fast.txt` records the expected startup failures before Kafka topics are bootstrapped.

## Dashboard Evidence

The dashboard-facing artifacts remain under `artifacts/demo/week7/` because that historical pack name is already stable across the repo:

- `../week7/dashboard-demo-summary.json`
- `../week7/grafana-api.json`
- `../week7/audio_quality.png`
- `../week7/system_health.png`
- `../week7/demo-artifact-notes.md`

## Practical Reading Order

- Use the restart/replay artifacts to explain startup gating and replay safety.
- Use the dashboard artifacts to explain TimescaleDB persistence, Grafana provisioning, and panel interpretation.
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
echo "Reliability artifacts: $demo_evidence_root"
echo "Dashboard artifacts: artifacts/demo/week7"
echo "Evidence index: $evidence_index_path"
