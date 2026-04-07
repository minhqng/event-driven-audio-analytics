#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../.."

week8_evidence_root="artifacts/demo/week8"
evidence_index_path="$week8_evidence_root/evidence-index.md"

write_week8_evidence_index() {
  cat >"$evidence_index_path" <<'EOF'
# Week 8 Evidence Index

This directory is the final Week 8 handoff anchor for the bounded PoC evidence set.

## Reliability Hardening

- `restart-replay-baseline.json` captures the first bounded broker-backed run before replay.
- `restart-replay-summary.json` captures the same `run_id` after restarting `processing` and `writer`, then rerunning `ingestion`.
- `preflight-fail-fast.txt` records the expected startup failures before Kafka topics are bootstrapped.

## Dashboard And Demo Evidence

The dashboard-facing artifacts remain under `artifacts/demo/week7/` because the existing deterministic dashboard demo pack and screenshot names are already stable in docs and slides:

- `../week7/dashboard-demo-summary.json`
- `../week7/grafana-api.json`
- `../week7/audio_quality.png`
- `../week7/system_health.png`
- `../week7/demo-artifact-notes.md`

## Practical Week 8 Reading

- Use the Week 8 replay artifacts to explain restart/replay behavior and fail-fast startup checks.
- Use the Week 7 dashboard artifacts to explain TimescaleDB persistence, Grafana provisioning, and panel interpretation.
- Treat this as bounded PoC evidence only; it is not benchmark-scale or production-readiness evidence.
EOF
}

echo "Running Week 8 restart/replay evidence path..."
sh ./scripts/smoke/check-restart-replay-flow.sh

echo "Running Week 7 dashboard evidence path..."
sh ./scripts/demo/generate-week7-dashboard-evidence.sh

mkdir -p "$week8_evidence_root"
write_week8_evidence_index

echo "Week 8 evidence generation is ready."
echo "Reliability artifacts: $week8_evidence_root"
echo "Dashboard artifacts: artifacts/demo/week7"
echo "Evidence index: $evidence_index_path"
