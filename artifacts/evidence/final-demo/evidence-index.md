# Final Demo Evidence Index

This directory is the final handoff anchor for the thesis-aligned bounded FMA-Small evidence set.

It demonstrates the event-driven microservices pipeline, claim-check artifact boundary, persisted analytics truth, read-only review inspection, Grafana corroboration, dataset/analytics output generation, and restart/replay behavior. It is bounded research evidence, not production-readiness or benchmark-scale proof.

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
- Use the separate validation runbook for MinIO/private-cloud, K3s, and evaluation evidence paths.
- Treat this as bounded FMA-Small research evidence only; it is not benchmark-scale or production-readiness evidence.
