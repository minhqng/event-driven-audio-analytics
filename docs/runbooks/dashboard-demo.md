# Dashboard Demo Runbook

## Purpose

This is the dashboard-only companion to the full demo runbook. It exercises:

- `ingestion -> processing -> writer -> TimescaleDB -> Grafana`
- one deterministic energetic run
- one deterministic silent-oriented run
- one deterministic validation-failure run

Use `docs/runbooks/demo.md` when you also need restart/replay evidence.

## Recommended Command

PowerShell on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-dashboard-evidence.ps1
```

Bash on Linux:

```sh
bash ./scripts/demo/generate-dashboard-evidence.sh
```

This command:

- validates `docker compose config`
- rebuilds the active demo images
- prepares deterministic dashboard demo inputs
- starts Kafka, TimescaleDB, Grafana, `processing`, and `writer`
- runs three one-shot `ingestion` cases
- verifies the resulting TimescaleDB dashboard summaries
- proves Grafana auto-loaded the dashboards from provisioning
- captures screenshots and notes under `artifacts/demo/week7/`

## Expected Outcome

After the command finishes successfully:

- `docker compose ps` shows healthy `kafka`, `timescaledb`, `grafana`, `processing`, and `writer` containers
- Grafana is reachable at [http://localhost:3000](http://localhost:3000)
- The dashboards are already present without click-ops:
  - [Audio Quality](http://localhost:3000/d/audio-quality/audio-quality?from=now-6h&to=now)
  - [System Health](http://localhost:3000/d/system-health/system-health?from=now-6h&to=now)
- Generated artifacts exist under `artifacts/demo/week7/`:
  - `dashboard-demo-summary.json`
  - `grafana-api.json`
  - `audio_quality.png`
  - `system_health.png`
  - `demo-artifact-notes.md`

The `week7` directory name is retained because it is the stable dashboard evidence pack already used across the repo.

## Recommended Live Sequence

1. Run the recommended command from the repo root.
2. Wait for `Dashboard demo evidence is ready.`
3. Open `Audio Quality` first, then `System Health`.
4. Walk through the three runs in this order:
   - `week7-high-energy`
   - `week7-silent-oriented`
   - `week7-validation-failure`
5. Use the saved screenshots if live Grafana navigation is interrupted.

## Panel Map

| Dashboard | Panel | What it proves | Main category |
| --- | --- | --- | --- |
| Audio Quality | `Segment RMS Over Time` | Energetic and silent-oriented runs remain visibly different after persistence. | Audio quality |
| Audio Quality | `Silent Segment Ratio By Run` | The silent-oriented run contains silent segments while the energetic baseline does not. | Audio quality / Reliability |
| Audio Quality | `Persisted Segment Count By Run` | Valid runs reached persistence; the validation-failure run did not produce downstream segments. | Throughput / Reliability |
| Audio Quality | `Validation Outcomes By Run` | The failure case is an ingestion-side validation outcome, not a hidden downstream break. | Reliability / Operational health |
| Audio Quality | `Run Quality Summary Table` | Compact summary of counts, RMS, silence ratio, and validation failures. | Audio quality / Reliability |
| System Health | `Persisted Segment Throughput` | The pipeline persisted real feature rows during the demo run. | Throughput |
| System Health | `Processing Latency Over Time` | The DSP and claim-check stage stayed measurable and bounded. | Latency |
| System Health | `Writer DB Latency By Topic` | TimescaleDB persistence latency stayed observable for writer-owned topic writes. | Latency / Operational health |
| System Health | `Claim-Check Artifact Write Latency` | Claim-check artifact writing has measurable overhead before processing starts. | Latency / Operational health |
| System Health | `Track Validation Error Rate By Run` | Validation-failure runs remain visible as operationally meaningful error-rate differences. | Reliability / Operational health |
| System Health | `Operational Summary Table` | Compact operational summary for presentation and report handoff. | Operational health |

## Optional Repo-Local FMA Burst

For a supplemental bounded real-data burst with a repo-local full FMA-small copy, keep the deterministic dashboard evidence path above as the presentation baseline and then use `scripts/demo/run-local-fma-burst.*` after placing:

- `tests/fixtures/audio/tracks.csv`
- `tests/fixtures/audio/fma_small/...`

## Still Out Of Scope

- 100-track dry run and benchmark evidence
- broader restart/failure-path hardening beyond the documented bounded replay path
- larger performance-tuning work
- broader observability expansion beyond the current dashboards
- contract, schema, or architecture redesign
