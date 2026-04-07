# Final Demo Runbook

## Purpose

This is the bounded Week 8 final-demo path for the locked PoC scope:

- fail-fast startup checks before Kafka topic bootstrap
- healthy broker-backed `ingestion -> processing -> writer -> TimescaleDB`
- same-`run_id` restart/replay verification after restarting `processing` and `writer`
- file-provisioned Grafana dashboards backed by real TimescaleDB data
- reproducible artifact output for report/demo handoff

It is a polished PoC demo path, not benchmark-scale or production-readiness evidence.

## Recommended Command

PowerShell on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-week8-evidence.ps1
```

Bash on Linux:

```sh
bash ./scripts/demo/generate-week8-evidence.sh
```

This command runs the bounded restart/replay smoke and the deterministic dashboard-evidence path sequentially, then writes an index under `artifacts/demo/week8/evidence-index.md`.

## Verified Outputs

After a successful run, the following evidence should exist:

- `artifacts/demo/week8/restart-replay-baseline.json`
- `artifacts/demo/week8/restart-replay-summary.json`
- `artifacts/demo/week8/preflight-fail-fast.txt`
- `artifacts/demo/week8/evidence-index.md`
- `artifacts/demo/week7/dashboard-demo-summary.json`
- `artifacts/demo/week7/grafana-api.json`
- `artifacts/demo/week7/audio_quality.png`
- `artifacts/demo/week7/system_health.png`
- `artifacts/demo/week7/demo-artifact-notes.md`

## Bounded Week 8 Reliability Notes

- Before topic bootstrap, all three service preflights now fail clearly with `startup_dependency` errors and explicit missing-topic messages.
- After topic bootstrap, all three service preflights pass on the same Compose stack.
- The bounded replay check reruns `ingestion` with `RUN_ID=week8-replay` after restarting `processing` and `writer`.
- On the committed smoke fixture set, the replay summary now shows:
  - `metadata_count=2`
  - `feature_count=3`
  - `processing_state_segments=3`
  - `silent_ratio_count=1`
  - writer checkpoint offsets advancing from `{audio.features: 2, audio.metadata: 1, system.metrics: 9}` to `{audio.features: 5, audio.metadata: 3, system.metrics: 19}`
- `processing` and `writer` now install graceful shutdown handlers so Compose restarts release Kafka consumer membership cleanly enough for the bounded replay smoke to pass.

## Bounded Dashboard Notes

- The deterministic dashboard demo still uses the stable Week 7 run ids:
  - `week7-high-energy`
  - `week7-silent-oriented`
  - `week7-validation-failure`
- The latest verified dashboard summary shows:
  - `week7-high-energy`: `segments_persisted=4`, `silent_ratio=0.0`, `error_rate=0.0`
  - `week7-silent-oriented`: `segments_persisted=4`, `silent_ratio=0.25`, `error_rate=0.0`
  - `week7-validation-failure`: `segments_persisted=0`, `validation_failures=1.0`, `error_rate=1.0`, `validation_status=silent`
- Grafana screenshots are regenerated automatically with the provisioned `Audio Quality` and `System Health` dashboards.

## Recommended Live Sequence

1. Run the recommended command from the repo root.
2. Open `artifacts/demo/week8/evidence-index.md`.
3. Use the Week 8 replay artifacts first to explain startup gating and restart/replay behavior.
4. Open Grafana or the Week 7 screenshots next to explain persistence and dashboard interpretation.
5. Use `docs/architecture/dashboard-interpretation.md` for the panel-by-panel talk track.

## Honest Limits

- This is verified on the committed bounded smoke fixtures and deterministic dashboard pack only.
- It does not include a 100-track burst, benchmark-scale latency evidence, or any production HA story.
- `audio.dlq` remains reserved only; the fail-fast path still stops for inspection on terminal record failures.
- `welford_snapshots` still exists in SQL without an active processing-side persisted producer path.
