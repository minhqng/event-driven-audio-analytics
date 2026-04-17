# Demo Runbook

## Purpose

This is the primary presentation path for the finished PoC. It combines:

- fail-fast startup evidence before Kafka topic bootstrap
- healthy broker-backed `ingestion -> processing -> writer -> TimescaleDB`
- a read-only run review surface over persisted truth
- bounded same-`run_id` restart/replay verification
- file-provisioned Grafana dashboards backed by persisted data
- reproducible artifacts for report and demo handoff

It is intentionally bounded evidence, not a benchmark or production-readiness claim.

## Recommended Command

PowerShell on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-demo-evidence.ps1
```

Bash on Linux:

```sh
bash ./scripts/demo/generate-demo-evidence.sh
```

This runs the restart/replay smoke path and the dashboard evidence path sequentially, then refreshes the final evidence index under `artifacts/demo/week8/evidence-index.md`.

## What A Successful Run Produces

- `artifacts/demo/week8/restart-replay-baseline.json`
- `artifacts/demo/week8/restart-replay-summary.json`
- `artifacts/demo/week8/preflight-fail-fast.txt`
- `artifacts/demo/week8/evidence-index.md`
- `artifacts/demo/week7/dashboard-demo-summary.json`
- `artifacts/demo/week7/review-api.json`
- `artifacts/demo/week7/grafana-api.json`
- `artifacts/demo/week7/run_review.png`
- `artifacts/demo/week7/audio_quality.png`
- `artifacts/demo/week7/system_health.png`
- `artifacts/demo/week7/demo-artifact-notes.md`

The `week7` and `week8` artifact directories are historical pack names retained for stability. They remain the canonical evidence locations for this repo.

## Reliability Notes

- Before topic bootstrap, all three service preflights fail clearly with `startup_dependency` errors and explicit missing-topic messages.
- After topic bootstrap, all three service preflights pass on the same Compose stack.
- The replay check reruns `ingestion` with the same logical `run_id` after restarting `processing` and `writer`.
- On the committed smoke fixture set, the replay evidence shows stable metadata and feature counts, replay-stable `silent_ratio`, and advancing writer checkpoints.
- `processing` and `writer` install graceful shutdown handlers so Compose restarts release Kafka consumer membership cleanly enough for the bounded replay check to pass.

## Dashboard Notes

- The deterministic dashboard evidence uses three stable demo runs:
  - `week7-high-energy`
  - `week7-silent-oriented`
  - `week7-validation-failure`
- The latest verified dashboard summary shows:
  - `week7-high-energy`: `segments_persisted=4`, `silent_ratio=0.0`, `error_rate=0.0`
  - `week7-silent-oriented`: `segments_persisted=4`, `silent_ratio=0.25`, `error_rate=0.0`
  - `week7-validation-failure`: `segments_persisted=0`, `validation_failures=1.0`, `error_rate=1.0`, `validation_status=silent`
- Grafana screenshots are regenerated automatically from the provisioned `Audio Quality` and `System Health` dashboards.

## Optional Bootstrap-Only Path

If you only want the stack up without running the demo inputs yet:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-demo.ps1
```

```sh
bash ./run-demo.sh
```

Use this when you want to inspect containers manually, run a specific smoke path from `docs/runbooks/validation.md`, or drive a repo-local FMA burst.

## Recommended Live Sequence

1. Run the recommended command from the repo root.
2. Open `artifacts/demo/week8/evidence-index.md`.
3. Use the restart/replay artifacts first to explain startup gating and replay safety.
4. Open the review console or the saved `run_review.png` screenshot next to explain run, track, and segment results.
5. Open Grafana or the saved screenshots after that to explain persistence and dashboard interpretation.
6. Use `docs/architecture/dashboard-interpretation.md` as the panel-by-panel talk track when you transition into Grafana.

## Honest Limits

- Verified on committed bounded smoke fixtures and the deterministic dashboard pack only
- No 100-track burst or benchmark-scale latency claims in the default demo path
- `audio.dlq` remains reserved only; terminal record failures still stop for inspection
- `welford_snapshots` exists in SQL without an active processing-side persisted producer path
