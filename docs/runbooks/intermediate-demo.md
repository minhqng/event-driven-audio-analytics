# Intermediate Demo Runbook

## Purpose

This is the Week 7.5 intermediate-demo path for the current PoC:

- `ingestion -> processing -> writer -> TimescaleDB -> Grafana`
- one deterministic healthy energetic run
- one deterministic silent-oriented run
- one deterministic validation-failure run

It is a bounded demo path, not Week 8 benchmark or restart/replay hardening work.

## Recommended Command

PowerShell on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-week7-dashboard-evidence.ps1
```

Bash on Linux:

```sh
bash ./scripts/demo/generate-week7-dashboard-evidence.sh
```

This is the recommended single-command demo path because it:

- validates `docker compose config`
- rebuilds the active service images used by the demo path
- prepares deterministic Week 7 demo inputs
- starts Kafka, TimescaleDB, Grafana, `processing`, and `writer`
- runs three one-shot `ingestion` cases with real data
- verifies TimescaleDB dashboard summaries with `verify_dashboard_demo`
- proves Grafana auto-loaded the dashboards through provisioning
- captures screenshots plus short artifact notes under `artifacts/demo/week7/`

For a supplemental bounded real-data burst with a repo-local full FMA-small copy, keep the primary Week 7.5 evidence path above as the presentation baseline and use `scripts/demo/run-repo-local-fma-burst.*` only after placing:

- `tests/fixtures/audio/tracks.csv`
- `tests/fixtures/audio/fma_small/...`

## Expected Outcome

After the command finishes successfully:

- `docker compose ps` should show healthy `kafka`, `timescaledb`, `grafana`, `processing`, and `writer` containers.
- Grafana should be reachable at [http://localhost:3000](http://localhost:3000).
- The dashboards should already be present without click-ops. These links intentionally pin the recent demo window:
  - [Audio Quality](http://localhost:3000/d/audio-quality/audio-quality?from=now-6h&to=now)
  - [System Health](http://localhost:3000/d/system-health/system-health?from=now-6h&to=now)
- Generated artifacts should exist under `artifacts/demo/week7/`:
  - `dashboard-demo-summary.json`
  - `grafana-api.json`
  - `audio_quality.png`
  - `system_health.png`
  - `demo-artifact-notes.md`

## Recommended Live Demo Sequence

1. Run the recommended command above from the repo root.
2. Wait for `Week 7 dashboard evidence is ready.`
3. Open `Audio Quality` first, then `System Health`.
4. Walk through the three runs in this order:
   - `week7-high-energy`
   - `week7-silent-oriented`
   - `week7-validation-failure`
5. Use the generated screenshots as fallback evidence if live Grafana navigation is interrupted.

## Panel Map

| Dashboard | Panel | What it proves | Main category |
| --- | --- | --- | --- |
| Audio Quality | `Segment RMS Over Time` | High-energy and silent-oriented runs are visibly different in persisted segment energy. | Audio quality |
| Audio Quality | `Silent Segment Ratio By Run` | The silent-oriented run contains silent segments while the energetic baseline does not. | Audio quality / Reliability |
| Audio Quality | `Persisted Segment Count By Run` | Valid runs reached persistence; the validation-failure run did not produce downstream segments. | Throughput / Reliability |
| Audio Quality | `Validation Outcomes By Run` | The failure case is an ingestion-side validation outcome, not a hidden downstream break. | Reliability / Operational health |
| Audio Quality | `Run Quality Summary Table` | Compact academic summary of counts, RMS, silence ratio, and validation failures. | Audio quality / Reliability |
| System Health | `Persisted Segment Throughput` | The pipeline persisted real feature rows during the demo run. | Throughput |
| System Health | `Processing Latency Over Time` | The DSP/claim-check processing stage stayed measurable and bounded. | Latency |
| System Health | `Writer DB Latency By Topic` | TimescaleDB persistence latency stayed observable for writer-owned topic writes. | Latency / Operational health |
| System Health | `Claim-Check Artifact Write Latency` | Claim-check artifact writing has measurable overhead before processing starts. | Latency / Operational health |
| System Health | `Track Validation Error Rate By Run` | Validation-failure runs are visible as operationally meaningful error-rate differences. | Reliability / Operational health |
| System Health | `Operational Summary Table` | Compact operational summary for the presentation and report handoff. | Operational health |

## Expected Demo Differences

| Run | Expected dashboard signal |
| --- | --- |
| `week7-high-energy` | `silent_ratio=0`, lower-magnitude negative RMS, non-zero throughput, zero error rate |
| `week7-silent-oriented` | non-zero `silent_ratio`, lower average RMS than the energetic baseline, non-zero throughput, zero error rate |
| `week7-validation-failure` | `validation_status=silent`, zero persisted segments, `error_rate=100%`, no downstream throughput |

## Week 8 Items Still Deferred

- broader replay/restart hardening under real producer traffic
- 100-track dry run and benchmark evidence
- larger performance-tuning work
- broader observability expansion beyond the current dashboards
- contract, schema, or architecture redesign
