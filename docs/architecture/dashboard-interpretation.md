# Dashboard Interpretation

This document records the Week 7 dashboard meaning for the file-provisioned Grafana dashboards under `infra/grafana/dashboards/`.

## Scope

- The canonical datasource is the provisioned `TimescaleDB` PostgreSQL datasource.
- The canonical dashboards are:
  - `infra/grafana/dashboards/audio_quality.json`
  - `infra/grafana/dashboards/system_health.json`
- The canonical query surface is:
  - `audio_features`
  - `track_metadata`
  - `system_metrics`
  - `vw_dashboard_metric_events`
  - `vw_dashboard_run_validation`
  - `vw_dashboard_run_summary`

## Shared Metric Convention

The Week 7 dashboards rely on the existing `system.metrics` contract and a shared label convention implemented in `src/event_driven_audio_analytics/shared/metric_labels.py`.

- Stable metric names:
  - `tracks_total`
  - `segments_total`
  - `validation_failures`
  - `artifact_write_ms`
  - `processing_ms`
  - `silent_ratio`
  - `feature_errors`
  - `write_ms`
  - `rows_upserted`
  - `write_failures`
- Stable labels:
  - `scope=run_total` for replay-safe snapshot metrics.
  - `scope=writer_record` for direct writer metrics keyed by Kafka record identity.
  - `topic=<topic_name>` for append-only success or failure metrics tied to one topic.
  - `status=ok|error` for append-only metrics.
  - `failure_class=<reason>` only for error-path metrics.
- Query normalization:
  - `vw_dashboard_metric_events` turns `labels_json` into stable SQL columns such as `metric_scope`, `metric_status`, `topic_name`, and `failure_class`.
  - Grafana panels query those normalized columns instead of repeating raw JSON extraction logic.

## Service Metric Ownership

- `ingestion` emits `tracks_total`, `segments_total`, `validation_failures`, and `artifact_write_ms` as run-level snapshots.
- `processing` emits append-only `processing_ms`, replay-safe `silent_ratio`, and error-path `feature_errors`.
- `writer` persists direct internal metrics `write_ms`, `rows_upserted`, and `write_failures` into `system_metrics`.

## Audio Quality Dashboard

### RMS Over Time

- Query source: `audio_features`
- Query meaning: average persisted `rms` per time bucket and `run_id`
- System property: segment energy level over time
- Why it matters: proves the pipeline preserves meaningful audio-energy differences after claim-check, processing, and persistence
- Supports:
  - audio quality
  - operational health

### Silent Ratio By Run

- Query source: `vw_dashboard_run_summary`
- Query meaning: latest `silent_ratio` snapshot per run, with fallback to persisted `audio_features` summary
- System property: proportion of segments classified as silent by processing
- Why it matters: proves the silent-oriented run is distinguishable from the energetic baseline without requiring manual log inspection
- Supports:
  - audio quality
  - reliability

### Segment Counts By Run

- Query source: `vw_dashboard_run_summary`
- Query meaning: persisted `audio_features` rows per run
- System property: how many segments survived ingestion, processing, and writer persistence
- Why it matters: distinguishes healthy runs from validation-failure runs and exposes whether replayed demo inputs reached the sink
- Supports:
  - throughput
  - reliability

### Validation Outcomes By Run

- Query source: `vw_dashboard_run_validation`
- Query meaning: `track_metadata.validation_status` counts per run
- System property: ingestion-side acceptance versus rejection outcomes
- Why it matters: explains why `week7-validation-failure` has no downstream features while still being a successful demonstration of validation and observability
- Supports:
  - reliability
  - operational health

### Run Quality Summary

- Query source: `vw_dashboard_run_summary`
- Query meaning: compact run-level table combining counts, silent ratio, RMS, and validation failures
- System property: one-row summary for report/demo use
- Why it matters: provides the academic handoff table for the dashboard story without requiring click-ops or ad hoc SQL during the demo
- Supports:
  - audio quality
  - reliability
  - operational health

## System Health Dashboard

### Throughput

- Query source: `audio_features`
- Query meaning: persisted feature-row count per time bucket and run
- System property: how fast the pipeline converts validated segments into persisted summaries
- Why it matters: provides the PoC throughput signal using real sink-side data instead of producer-side estimates
- Supports:
  - throughput
  - operational health

### Processing Latency

- Query source: `vw_dashboard_metric_events`
- Query meaning: average `processing_ms` per time bucket and run
- System property: processing-service latency for claim-check load plus DSP work
- Why it matters: shows whether the Week 5 processing stage stays bounded under the Week 7 demo runs
- Supports:
  - latency
  - operational health

### DB Write Latency

- Query source: `vw_dashboard_metric_events`
- Query meaning: average writer `write_ms` grouped by destination topic
- System property: sink-side latency inside the writer transaction path
- Why it matters: proves that TimescaleDB persistence is observable and that write cost stays visible without external monitoring tooling
- Supports:
  - latency
  - reliability
  - operational health

### Artifact Write Latency

- Query source: `vw_dashboard_run_summary`
- Query meaning: run-level `artifact_write_ms` snapshot from ingestion
- System property: cost of writing claim-check segment artifacts before processing starts
- Why it matters: proves the claim-check boundary has measurable overhead and lets the demo compare artifact-write cost across runs
- Supports:
  - latency
  - throughput
  - operational health

### Error Rate By Run

- Query source: `vw_dashboard_run_summary`
- Query meaning: `validation_failures / tracks_total`
- System property: track-level validation failure rate for the bounded PoC run
- Why it matters: gives the report/demo a defensible run-level error-rate panel without mixing track-scoped validation outcomes and segment-scoped runtime error counts
- Supports:
  - reliability
  - operational health

### Operational Summary

- Query source: `vw_dashboard_run_summary`
- Query meaning: run-level table for total errors, error rate, latency, and artifact-write cost
- System property: compact observability summary
- Why it matters: supports report/demo narration without extra SQL during the live demo
- Supports:
  - reliability
  - throughput
  - latency
  - operational health

## Demo Runs Used For Week 7

The deterministic Week 7 evidence run uses the shared `event_driven_audio_analytics.smoke.prepare_week7_inputs` helper through `scripts/demo/generate-week7-dashboard-evidence.ps1`.

- `week7-high-energy`
  - Input shape: continuous energetic tone
  - Expected signal: lower-magnitude negative RMS, `silent_ratio=0`, non-zero throughput
- `week7-silent-oriented`
  - Input shape: first segment silent, later segments energetic
  - Expected signal: lower average RMS than the energetic baseline and non-zero `silent_ratio`
- `week7-validation-failure`
  - Input shape: fully silent track
  - Expected signal: `validation_status=silent`, zero persisted segments, non-zero error rate

## Evidence Artifacts

The Week 7 evidence script writes demo artifacts under `artifacts/demo/week7/`.

- `dashboard-demo-summary.json`
- `grafana-api.json`
- `audio_quality.png`
- `system_health.png`

These artifacts are demo outputs, not canonical source-of-truth documents.
The canonical dashboard configuration remains the file-provisioned Grafana JSON and YAML under `infra/grafana/`.
