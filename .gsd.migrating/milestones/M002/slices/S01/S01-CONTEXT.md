# M002/S01: Grafana presentation contract

**Gathered:** 2026-05-25
**Status:** Ready for downstream dashboard implementation

## Project Description

This slice defines the presentation contract for improving the existing file-provisioned Grafana dashboards in `event-driven-audio-analytics`. The goal is not to make Grafana the product front door. The goal is to make Grafana a clear, trustworthy presentation surface that corroborates persisted TimescaleDB truth after the review console story is established.

The contract covers two dashboards:

- `Audio Quality` — `uid: audio-quality`, source file `infra/grafana/dashboards/audio_quality.json`.
- `System Health` — `uid: system-health`, source file `infra/grafana/dashboards/system_health.json`.

Both dashboards must stay read-only, file-provisioned, and backed by datasource UID `timescaledb`.

## Why This Slice

The user wants to improve Grafana for presentation. The existing dashboards already show useful data, but their downstream edits need a shared contract so they become easier to explain without drifting into false claims about live infrastructure health, production readiness, or unobserved private-cloud behavior.

This slice prevents presentation polish from becoming screenshot-only decoration. Every dashboard change must preserve evidence provenance: what the panel proves, where the data comes from, what the presenter can safely say, and what remains outside the evidence boundary.

## User-Visible Outcome

### When this slice is consumed by downstream work, the user can:

- Open Grafana after the review console and explain the audio result dashboard first, then operational corroboration second.
- Point to each panel and state what persisted evidence it proves.
- Avoid overclaiming Kafka, MinIO, container, K3s, or production health from panels that only read TimescaleDB rows.
- Capture dashboard screenshots/API snapshots that support a thesis presentation without manual click-ops.

### Entry point / environment

- Entry point: `http://localhost:3000`
- Kiosk dashboard URLs:
  - `http://localhost:3000/d/audio-quality/audio-quality?from=now-6h&to=now&kiosk`
  - `http://localhost:3000/d/system-health/system-health?from=now-6h&to=now&kiosk`
- Environment: local Docker Compose Grafana, with K3s dashboard copies kept in parity.
- Live dependencies involved: Grafana, TimescaleDB, file provisioning, deterministic demo evidence scripts.

## Completion Class

- Contract complete means: this document names the presentation narrative, panel purposes, allowed claims, forbidden claims, visual guidance, and downstream test targets.
- Integration complete means: S02/S03 dashboard JSON changes can be checked against this contract without guessing intended wording or metric semantics.
- Operational complete means: the final evidence path can capture Grafana screenshots/API snapshots with stable dashboard UIDs and URLs.

## Final Integrated Acceptance

To call the full milestone complete, we must prove:

- `Audio Quality` and `System Health` dashboards load from file provisioning and are readable in kiosk/screenshot mode.
- Panel titles, descriptions, legends, units, and thresholds support a presenter explaining audio quality and pipeline corroboration in under a few minutes.
- Grafana remains a read-only corroboration layer over TimescaleDB persisted truth, not a source of unobserved infrastructure-health claims.
- Compose and K3s dashboard JSON copies are synchronized or explicitly checked by tests.
- Evidence scripts still produce `grafana-api.json`, `audio-quality-dashboard.png`, `system-health-dashboard.png`, and `review-dashboard-notes.md`.

## Presentation Narrative Order

### Overall demo order

1. Review console first: show selected deterministic runs, validation outcomes, track/segment detail, and persisted review evidence.
2. Grafana Audio Quality second: corroborate audio analytics results with dashboard visuals.
3. Grafana System Health third: corroborate pipeline persistence, latency, throughput, and error/validation behavior from persisted metrics.
4. Dataset bundles and restart/replay artifacts last: show reusable outputs and bounded reliability evidence.

### Grafana-only reading order

1. Start with `Audio Quality` because the audience can understand audio outcomes before operational metrics.
2. Read the audio dashboard left-to-right/top-to-bottom:
   - RMS/energy trend.
   - Silent segment ratio.
   - Persisted segment count.
   - Validation outcomes.
   - Run quality summary table.
3. Move to `System Health` as corroboration:
   - Persisted segment throughput.
   - Processing latency.
   - Writer DB latency.
   - Claim-check artifact write latency.
   - Track validation error rate.
   - Operational summary table.
4. End by saying: “These panels are generated from persisted TimescaleDB rows, so they corroborate what the review console and dataset exporter read from the same truth source.”

## Presenter Script Bullets

Use concise Vietnamese-first narration with English technical terms in parentheses where useful:

- “Dashboard này không phải là giao diện chính; nó là bằng chứng hỗ trợ (corroboration) từ TimescaleDB.”
- “Audio Quality cho thấy dữ liệu âm thanh đã được xử lý và persist: RMS, silent ratio, số segment, và validation outcome.”
- “System Health cho thấy pipeline có ghi nhận throughput, latency, write latency, và error/validation signal từ persisted metrics.”
- “Các số liệu này không khẳng định production-ready hay cluster health; chúng chứng minh bounded demo chạy đúng trên dữ liệu đã lưu.”
- “Review console và dataset bundle vẫn là lớp đọc chính; Grafana giúp nhìn nhanh bằng biểu đồ.”

Avoid long bilingual duplication. Prefer short Vietnamese labels plus precise English technical terms when the term maps to code or dashboard concepts.

## Dashboard Purposes

### Audio Quality (`uid: audio-quality`)

Purpose: answer “What did the audio analytics pipeline produce, and which runs/tracks were valid enough to explain?”

This dashboard should emphasize:

- Audio amplitude/energy evidence from RMS.
- Silence detection outcomes from silent ratio.
- Whether segments were actually persisted.
- Why validation failures produce less or no downstream evidence.
- A compact report table that can be screenshotted for academic reporting.

### System Health (`uid: system-health`)

Purpose: answer “Did the bounded event-driven pipeline persist metrics that corroborate processing, writing, and validation behavior?”

This dashboard should emphasize:

- Persisted segment throughput as a proof-of-concept throughput signal.
- Processing latency and writer DB latency as persisted runtime metrics.
- Claim-check artifact write latency as evidence of the artifact boundary.
- Validation/error rate as a demo-quality signal, not a production SLO.
- A compact operational summary table that supports the report/demo handoff.

## Panel Contract

### Audio Quality panels

| Panel | Required purpose | Data provenance | Allowed claim | Presentation improvement target |
|---|---|---|---|---|
| Segment RMS Over Time | Show audio energy trend from processed segments. | Persisted feature rows through `timescaledb`. | “The pipeline computed and persisted RMS-like audio feature evidence over time.” | Use readable unit/legend wording such as RMS or RMS dB if query semantics confirm it; keep run grouping visible. |
| Silent Segment Ratio By Run | Compare silence outcome by run. | `vw_dashboard_run_summary`. | “This run has higher/lower silent segment share based on persisted summary rows.” | Show percent unit and make high silence visually obvious but not alarmist. |
| Persisted Segment Count By Run | Prove segment feature rows were written. | `vw_dashboard_run_summary`. | “The writer persisted this many segment feature records for the run.” | Use count unit and title that says persisted, not merely produced. |
| Validation Outcomes By Run | Explain accepted/rejected track counts. | `vw_dashboard_run_validation`. | “Validation outcomes explain why some runs have limited downstream segments.” | Keep table readable; expose run id, validation status, and track count clearly. |
| Run Quality Summary Table | Provide compact academic summary. | `vw_dashboard_run_summary`. | “This table summarizes run-level persisted quality evidence.” | Use presenter-friendly column names and ordering; avoid raw internal-only names where possible. |

### System Health panels

| Panel | Required purpose | Data provenance | Allowed claim | Presentation improvement target |
|---|---|---|---|---|
| Persisted Segment Throughput | Show committed feature-row throughput. | Persisted feature rows through `timescaledb`. | “The system persisted segment feature rows over this time window.” | Label as persisted throughput, not full broker throughput. |
| Processing Latency Over Time | Show processing service latency metric. | `vw_dashboard_metric_events`, metric `processing_ms`. | “Processing emitted latency metrics that were normalized and persisted.” | Use milliseconds unit and readable legend by run. |
| Writer DB Latency By Topic | Show writer DB persistence latency. | `vw_dashboard_metric_events`, metric `write_ms`. | “Writer DB latency is visible by destination topic from persisted metrics.” | Use milliseconds unit; keep topic grouping visible. |
| Claim-Check Artifact Write Latency | Show artifact-boundary write latency. | `vw_dashboard_run_summary`. | “Ingestion recorded artifact write latency for claim-check evidence.” | Clarify this is artifact write latency, not MinIO or filesystem health. |
| Track Validation Error Rate By Run | Show validation error ratio by run. | `vw_dashboard_run_summary`. | “This ratio reflects track validation failures for each run.” | Use percent unit; distinguish validation failure from service outage. |
| Operational Summary Table | Provide compact operational handoff table. | `vw_dashboard_run_summary`. | “This table summarizes persisted operational evidence.” | Put error counts, error rate, latency, and artifact write latency in a demo-friendly order. |

## Allowed Claims

Grafana may claim:

- The dashboards are file-provisioned and read-only.
- The datasource is TimescaleDB via UID `timescaledb`.
- The panels read persisted analytics and metrics rows.
- Audio quality evidence includes RMS, silence ratio, persisted segment counts, validation outcomes, and run-level summaries.
- Operational evidence includes persisted throughput, processing latency, writer DB latency, artifact write latency, validation/error counts, and summary tables.
- The evidence is bounded demo/research evidence over FMA-Small deterministic runs.
- Grafana corroborates the review console and dataset exporter because they read from the same persisted truth source.

## Forbidden Overclaims

Grafana must not claim unless separately proven by explicit data:

- Kafka is healthy, real-time, lossless, highly available, or production-ready.
- MinIO/S3 is healthy, durable, or production-equivalent.
- Docker, K3s, private cloud, or cluster infrastructure is healthy.
- The system has production SLOs, HA/DR, autoscaling, or benchmark-scale performance.
- `system.metrics` rows prove full infrastructure monitoring.
- A green panel means all services are live right now.
- Grafana is the authoritative product UI or the source of truth.
- Audio model quality, ML training, or serving quality is proven; this project persists scalar/log-mel-shape evidence, not a trained model.

Preferred wording for uncertain/live status: “persisted evidence shows,” “dashboard rows indicate,” “bounded demo run recorded,” and “corroborates.” Avoid wording like “system is healthy,” “cluster is healthy,” “all infrastructure is OK,” or “production monitoring.”

## Visual Guidance

### Titles and descriptions

- Titles should be audience-readable and specific: mention persisted data, run, latency, validation, or audio quality where relevant.
- Descriptions should include one short sentence about provenance and one short sentence about interpretation.
- Avoid raw implementation names in titles unless they are meaningful technical terms for the thesis audience.
- Keep dashboard and panel UIDs stable: `audio-quality`, `system-health`.

### Units and thresholds

- Percent values: use percent units for silent ratio and validation error rate.
- Counts: use count/short unit for persisted segment counts and validation counts.
- Latency: use milliseconds for `processing_ms`, `write_ms`, and `artifact_write_ms`.
- Throughput: label as persisted segment rows per time bucket, not Kafka throughput.
- Thresholds should help presentation, not imply production alerting. If thresholds are added, label them as demo interpretation bands, not SLOs.

### Legends and layout

- Legends should identify `run_id`, `topic_name`, or validation grouping clearly.
- Kiosk/screenshot mode should be readable on a laptop/projector: avoid dense tiny legends and overly narrow tables.
- Prefer fewer larger panels over many small panels.
- Put “what happened to the audio?” panels before “how did the pipeline behave?” panels.
- Tables should have human-friendly column order and avoid hiding critical columns such as `run_id`, validation status, counts, and latencies.

### Color semantics

- Use calm, academic/professional color cues.
- Do not make validation failure look like infrastructure outage.
- Use warning/error color only for actual failed or degraded evidence, not for expected demo cases like a validation-failure run.
- Silent ratio can be visually highlighted, but the explanation should distinguish “silent audio content” from “pipeline failure.”

## Error Handling and Fallback Strategy

Grafana dashboards are read-only and file-provisioned. If a panel has no data:

- The presenter should say the selected time window or demo data may not contain rows.
- The dashboard copy should avoid implying the pipeline is broken solely from no-data panels.
- The evidence script remains the authoritative capture path for final screenshots/API snapshots.
- S05 should verify screenshots after deterministic demo data generation when Docker is available.

If evidence generation fails:

- Preserve the failing command and error output.
- Check Grafana `/api/health`, dashboard API UIDs, TimescaleDB readiness, and deterministic demo data verification.
- Do not manually edit dashboards in the Grafana UI to repair the demo; fix the JSON/provisioning files.

## Existing Codebase and Prior Art

- `infra/grafana/dashboards/audio_quality.json` — Compose dashboard JSON for audio evidence.
- `infra/grafana/dashboards/system_health.json` — Compose dashboard JSON for operational evidence.
- `deploy/k3s/grafana/config/dashboards/*.json` — K3s dashboard copies that must remain synchronized.
- `infra/grafana/provisioning/dashboards/dashboards.yaml` — Grafana file provider with UI edits disabled.
- `infra/grafana/provisioning/datasources/timescaledb.yaml` — non-editable TimescaleDB datasource using environment variables.
- `infra/sql/003_operational_views.sql` — source of dashboard summary and metric views.
- `scripts/demo/generate-dashboard-evidence.sh` and `.ps1` — final dashboard evidence capture paths.
- `tests/unit/test_grafana_provisioning.py` — existing provisioning tests.
- `tests/unit/test_demo_evidence_scripts.py` — existing evidence-script tests.
- `tests/unit/test_k3s_manifests.py` — existing K3s provisioning/resource tests.

## Relevant Requirement

- `R001` — Grafana dashboards must be presentation-ready for thesis/demo use. This slice advances R001 by defining the contract future dashboard edits must satisfy.

## Scope

### In Scope

- Presentation narrative and dashboard reading order.
- Panel-by-panel purpose and provenance.
- Allowed and forbidden claims.
- Label, unit, threshold, legend, layout, and color guidance.
- Downstream acceptance checklist and test targets.

### Out of Scope / Non-Goals

- Editing dashboard JSON directly in this slice.
- Running the full Docker/Grafana evidence path in this slice.
- Adding new Grafana plugins, datasources, frontend stacks, or click-ops workflows.
- Turning Grafana into the primary review/product surface.
- Claiming live infrastructure health beyond persisted evidence.

## Technical Constraints

- Dashboards must remain file-provisioned.
- Datasource UID must remain `timescaledb` unless all dashboards, scripts, and tests change together.
- Dashboard UIDs and slugs must remain `audio-quality` and `system-health` unless both evidence scripts and tests change together.
- Compose and K3s dashboard copies must stay byte-identical or have a tested synchronization mechanism.
- Compose and K3s dashboard JSON copies must stay byte-identical unless a future task adds an explicit, tested sync/render step.
- Dashboard copy should remain compatible with Grafana `11.1.4` from `docker-compose.yml`.

## Integration Points

- Grafana file provisioning — consumes dashboard JSON and datasource YAML.
- TimescaleDB — supplies persisted analytics and metrics rows.
- Demo evidence scripts — capture API snapshots and screenshots using stable dashboard UIDs/URLs.
- K3s manifests — package dashboard copies for bounded private-cloud variant.
- Unit tests — should guard provisioning, dashboard contract, evidence URLs, no-overclaim wording, and parity.

## Downstream Acceptance Checklist

### S02: Audio quality dashboard polish

- Preserve `uid: audio-quality` and datasource UID `timescaledb`.
- Improve panel titles/descriptions for presenter readability.
- Keep RMS, silent ratio, persisted segment count, validation outcomes, and quality summary visible.
- Add or verify units for percent/count/RMS fields.
- Do not imply audio model training/serving quality.
- Copy changes to the K3s dashboard file or use a tested sync mechanism.
- Add tests for expected panel titles, descriptions, datasource UID, and parity.

### S03: System health dashboard polish

- Preserve `uid: system-health` and datasource UID `timescaledb`.
- Improve panel titles/descriptions for persisted operational evidence.
- Keep throughput, processing latency, writer DB latency, artifact write latency, validation error rate, and operational summary visible.
- Use milliseconds for latency and percent for error rate.
- Label throughput as persisted segment rows, not Kafka throughput.
- Do not claim Kafka/MinIO/container/K3s health.
- Copy changes to the K3s dashboard file or use a tested sync mechanism.
- Add tests for expected panel titles, descriptions, datasource UID, no-overclaim wording, and parity.

### S04: Provisioning parity and evidence script alignment

- Assert Compose and K3s dashboard JSON copies are identical or intentionally synchronized.
- Assert dashboard evidence scripts reference `audio-quality` and `system-health` URLs and API UIDs.
- Assert `grafana-api.json`, `audio-quality-dashboard.png`, `system-health-dashboard.png`, and `review-dashboard-notes.md` remain expected artifacts.
- Update artifact notes to match the upgraded presentation story.
- Keep `allowUiUpdates: false` and datasource `editable: false`.

## Testing Requirements

S02/S03/S04 should use static tests before runtime verification:

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp tests/unit/test_grafana_provisioning.py tests/unit/test_demo_evidence_scripts.py tests/unit/test_k3s_manifests.py
```

Recommended additional tests:

- Dashboard JSON loads successfully.
- Dashboard UIDs and titles match expected values.
- All panels use datasource UID `timescaledb`.
- Expected panel titles/descriptions are present and non-empty.
- Compose and K3s dashboard JSON files are identical.
- Evidence scripts reference stable dashboard URLs and API UIDs.
- Dashboard titles/descriptions avoid forbidden overclaim terms.

Final S05 verification should run the dashboard evidence script when Docker is available:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-dashboard-evidence.ps1
```

or:

```sh
bash ./scripts/demo/generate-dashboard-evidence.sh
```

## Acceptance Criteria

- This contract names the Grafana presentation order and panel reading order.
- Each existing panel has a stated purpose, provenance, allowed claim, and improvement target.
- Allowed claims and forbidden overclaims are explicit.
- Visual guidance covers titles, descriptions, units, thresholds, legends, layout, and color semantics.
- Downstream S02/S03/S04 acceptance checklists are actionable and file-specific.
- Test targets are concrete enough for later agents to implement without re-discovering the dashboard surface.

## Open Questions

- Whether S02/S03 should rename panels extensively or preserve most titles with improved descriptions — current recommendation is to preserve familiar meanings while making labels more presentation-friendly.
- Whether runtime screenshots should be produced in S02/S03 or deferred to S05 — current recommendation is static tests in S02/S03, final screenshots/API proof in S05.
- Whether no-overclaim checks should be simple forbidden-term tests or semantic review — current recommendation is both: static forbidden-term checks plus human review against this contract.
