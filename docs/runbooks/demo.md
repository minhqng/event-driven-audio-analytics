# Final Demo Runbook

Use this runbook for the release-ready bounded demo.

## Primary Command

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-demo-evidence.ps1
```

Bash:

```sh
bash ./scripts/demo/generate-demo-evidence.sh
```

## Front Door

Open the review console first:

```text
http://localhost:8080/?demo=1
```

Use Grafana after the review story is clear:

```text
http://localhost:3000
```

## Deterministic Review Runs

- `demo-high-energy`: validated high-energy track with persisted segments.
- `demo-silent-oriented`: validated track with at least one silent persisted segment.
- `demo-validation-failure`: metadata-only validation failure with no persisted feature rows.

## Evidence Output

The final command writes:

- `artifacts/evidence/final-demo/evidence-index.md`
- `artifacts/evidence/final-demo/review-dashboard/review-dashboard-summary.json`
- `artifacts/evidence/final-demo/review-dashboard/review-api.json`
- `artifacts/evidence/final-demo/review-dashboard/grafana-api.json`
- `artifacts/evidence/final-demo/review-dashboard/review-console.png`
- `artifacts/evidence/final-demo/review-dashboard/audio-quality-dashboard.png`
- `artifacts/evidence/final-demo/review-dashboard/system-health-dashboard.png`
- `artifacts/evidence/final-demo/review-dashboard/review-dashboard-notes.md`
- `artifacts/evidence/final-demo/restart-replay/restart-replay-baseline.json`
- `artifacts/evidence/final-demo/restart-replay/restart-replay-summary.json`
- `artifacts/evidence/final-demo/restart-replay/preflight-fail-fast.txt`

## Bootstrap Only

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-demo.ps1
```

Bash:

```sh
bash ./run-demo.sh
```

This starts Kafka, TimescaleDB, Grafana, processing, writer, and the read-only review service without running deterministic demo inputs.

## Honest Limits

- Bounded demo evidence, not benchmark-scale proof.
- Same-`run_id` replay/restart behavior is verified on committed smoke fixtures.
- The review layer is read-only and non-authoritative.
- Grafana is supporting corroboration, not the primary product surface.
- `audio.dlq` remains reserved only.
