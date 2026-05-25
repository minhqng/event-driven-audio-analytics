# M002/S01 — Research

**Date:** 2026-05-25

## Summary

The current Grafana evidence surface is already small and file-provisioned: Docker Compose mounts `infra/grafana/provisioning` and `infra/grafana/dashboards`, while K3s carries byte-identical dashboard JSON copies under `deploy/k3s/grafana/config/dashboards`. Grafana uses one non-editable TimescaleDB datasource with UID `timescaledb`, environment-derived PostgreSQL connection settings, and file provider updates from `/var/lib/grafana/dashboards`.

There are two dashboards to improve for presentation: `Audio Quality` (`uid: audio-quality`) and `System Health` (`uid: system-health`). Both already query persisted TimescaleDB truth through raw SQL against `audio_features`, `track_metadata`, and dashboard views from `infra/sql/003_operational_views.sql`. The milestone should preserve that truth model: Grafana corroborates persisted evidence and should not claim direct Kafka, MinIO, container, or cluster health unless those signals are exposed by the persisted rows.

## Recommendation

Improve the existing dashboard JSON in place, then keep K3s copies synchronized and strengthen static tests around UIDs, panel titles, descriptions, datasource UID, evidence-script URLs, and copy parity. Do not introduce click-ops, plugins, a new frontend, or live infrastructure-health claims. The safest downstream sequence is: define presentation copy and visual contract first, polish `Audio Quality`, polish `System Health`, then update parity/evidence tests and notes.

## Implementation Landscape

### Key Files

- `infra/grafana/dashboards/audio_quality.json` — Compose-provisioned `Audio Quality` dashboard (`uid: audio-quality`) and primary target for audio presentation polish.
- `infra/grafana/dashboards/system_health.json` — Compose-provisioned `System Health` dashboard (`uid: system-health`) and primary target for operational corroboration polish.
- `deploy/k3s/grafana/config/dashboards/audio_quality.json` — K3s copy of the Audio Quality dashboard; currently byte-identical to the Compose dashboard file.
- `deploy/k3s/grafana/config/dashboards/system_health.json` — K3s copy of the System Health dashboard; currently byte-identical to the Compose dashboard file.
- `infra/grafana/provisioning/dashboards/dashboards.yaml` — File provider named `event-driven-audio-analytics`, `allowUiUpdates: false`, path `/var/lib/grafana/dashboards`.
- `infra/grafana/provisioning/datasources/timescaledb.yaml` — Datasource `TimescaleDB` with UID `timescaledb`; PostgreSQL connection fields come from environment variables and datasource is non-editable.
- `infra/sql/003_operational_views.sql` — Defines dashboard views: `vw_run_feature_summary`, `vw_latest_run_checkpoints`, `vw_latest_system_metrics`, `vw_dashboard_metric_events`, `vw_dashboard_run_total_metrics`, `vw_dashboard_run_validation`, and `vw_dashboard_run_summary`.
- `scripts/demo/generate-dashboard-evidence.sh` — Starts stack components, verifies dashboard data, queries Grafana API, captures review/Grafana screenshots, and writes artifact notes.
- `scripts/demo/generate-dashboard-evidence.ps1` — PowerShell equivalent evidence path for Windows users.
- `tests/unit/test_grafana_provisioning.py` — Existing test coverage for Grafana datasource env references and Compose service env wiring.
- `tests/unit/test_demo_evidence_scripts.py` — Existing evidence-script guardrails; currently checks dataset script contracts and browser stderr handling for the PowerShell dashboard script.
- `tests/unit/test_k3s_manifests.py` — Existing K3s ConfigMap generator checks for Grafana datasource, dashboard provider, and dashboard JSON files.

### Current Dashboard Inventory

#### Audio Quality (`infra/grafana/dashboards/audio_quality.json`, `uid: audio-quality`)

| Panel | Type | Current title | Data source / views | Presentation purpose |
|---|---|---|---|---|
| 1 | `timeseries` | Segment RMS Over Time | `timescaledb`; raw query over persisted feature rows | Show audio amplitude/energy trend from persisted feature data. |
| 2 | `barchart` | Silent Segment Ratio By Run | `vw_dashboard_run_summary` | Explain silence detection outcome per deterministic run. |
| 3 | `barchart` | Persisted Segment Count By Run | `vw_dashboard_run_summary` | Show writer-backed segment persistence evidence per run. |
| 4 | `table` | Validation Outcomes By Run | `vw_dashboard_run_validation` | Explain accepted/rejected tracks and validation failures. |
| 5 | `table` | Run Quality Summary Table | `vw_dashboard_run_summary` | Compact academic report table for counts, RMS, silence, and validation failures. |

#### System Health (`infra/grafana/dashboards/system_health.json`, `uid: system-health`)

| Panel | Type | Current title | Data source / views | Presentation purpose |
|---|---|---|---|---|
| 1 | `timeseries` | Persisted Segment Throughput | `timescaledb`; raw query over persisted feature rows | Show bounded proof-of-concept throughput from committed feature rows. |
| 2 | `timeseries` | Processing Latency Over Time | `vw_dashboard_metric_events` | Show persisted processing latency metrics by run. |
| 3 | `timeseries` | Writer DB Latency By Topic | `vw_dashboard_metric_events` | Show writer persistence latency by topic from normalized metrics. |
| 4 | `barchart` | Claim-Check Artifact Write Latency | `vw_dashboard_run_summary` | Show run-level artifact write latency emitted by ingestion and normalized into summary. |
| 5 | `barchart` | Track Validation Error Rate By Run | `vw_dashboard_run_summary` | Show failed-track ratio and validation-driven error signal per run. |
| 6 | `table` | Operational Summary Table | `vw_dashboard_run_summary` | Compact table for error counts, error rate, processing latency, and artifact write latency. |

### Evidence Script Contract

Both evidence scripts use the same stable Grafana URLs in kiosk mode:

- `http://localhost:$grafana_port/d/audio-quality/audio-quality?from=now-6h&to=now&kiosk` in Bash.
- `http://localhost:$grafana_port/d/system-health/system-health?from=now-6h&to=now&kiosk` in Bash.
- `http://localhost:$grafanaPort/d/audio-quality/audio-quality?from=now-6h&to=now&kiosk` in PowerShell.
- `http://localhost:$grafanaPort/d/system-health/system-health?from=now-6h&to=now&kiosk` in PowerShell.

Both scripts also query or record:

- `api/dashboards/uid/audio-quality`
- `api/dashboards/uid/system-health`
- `grafana-api.json`
- `audio-quality-dashboard.png`
- `system-health-dashboard.png`
- `review-dashboard-notes.md`

### Build Order

1. Write the S01 presentation contract against the inventory above so S02 and S03 have stable wording, visual, and no-overclaim boundaries.
2. Polish `Audio Quality` first because it is the audience-friendly audio result surface.
3. Polish `System Health` second because it corroborates the event-driven pipeline and persistence behavior.
4. Add or extend static tests for dashboard JSON structure, dashboard copy parity, evidence URLs, panel titles/descriptions, and no-overclaim wording.
5. Run dashboard/evidence verification when Docker/Grafana is available.

### Verification Approach

For S01, verification is static: confirm this research artifact lists both dashboard UIDs, current panel titles, primary SQL views, evidence screenshot URLs, and existing/proposed test files. For later slices, use focused unit tests first, then run the existing dashboard evidence path when the local stack is available:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-dashboard-evidence.ps1
```

```sh
bash ./scripts/demo/generate-dashboard-evidence.sh
```

Recommended local unit test command for this Windows workspace:

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp tests/unit/test_grafana_provisioning.py tests/unit/test_demo_evidence_scripts.py tests/unit/test_k3s_manifests.py
```

## Constraints

- Grafana remains a supporting corroboration surface, not the primary product front door.
- TimescaleDB persisted rows are the dashboard truth source.
- The review console and dataset bundles remain primary product/evidence surfaces in the existing docs.
- Dashboard provisioning must remain file-based and read-only: `allowUiUpdates: false`, datasource `editable: false`.
- Dashboard URLs and UIDs are part of the evidence-script contract and should stay stable unless scripts and tests change together.
- Compose and K3s dashboard JSON copies must not drift silently.

## Common Pitfalls

- **Overclaiming live infrastructure health** — Avoid wording like “Kafka healthy,” “MinIO healthy,” “cluster healthy,” or “production ready” unless backed by persisted metrics that explicitly prove those states.
- **Screenshot-only polish** — Better layout is useful, but each panel must still map to persisted truth and explain what it proves.
- **Breaking evidence scripts by changing UIDs/slugs** — Keep `audio-quality` and `system-health` stable or update both Bash and PowerShell scripts plus tests.
- **Compose/K3s drift** — Any dashboard JSON edit must be copied or synchronized to `deploy/k3s/grafana/config/dashboards/`.

## Open Risks

- The best visual layout cannot be fully validated without running Grafana in a browser or producing screenshots.
- Current tests do not yet deeply inspect dashboard JSON panel titles, descriptions, units, thresholds, or copy parity.
- Some panel queries use direct persisted tables instead of named dashboard views; downstream contracts should identify those as persisted truth rather than force unnecessary SQL view changes.

## Proposed Test Targets

- Extend `tests/unit/test_grafana_provisioning.py` or add a focused dashboard test file to assert dashboard UIDs, titles, datasource UID `timescaledb`, expected panel titles, and non-empty descriptions.
- Add a parity test asserting Compose and K3s dashboard JSON files are identical or intentionally synchronized.
- Extend `tests/unit/test_demo_evidence_scripts.py` to assert both Bash and PowerShell dashboard evidence scripts use the stable `audio-quality` and `system-health` URLs and API UIDs.
- Optionally add no-overclaim text checks on dashboard titles/descriptions to prevent `Kafka healthy`, `MinIO healthy`, `K3s healthy`, or `production-ready` wording in Grafana presentation panels.

## Sources

- Repo README, demo runbook, and system overview establish Grafana as corroboration over persisted truth.
- Dashboard JSON and provisioning YAML establish current dashboards, UIDs, datasource UID, and file provisioning.
- `infra/sql/003_operational_views.sql` establishes available dashboard views.
- Evidence scripts establish screenshot URLs, API snapshots, and artifact names.