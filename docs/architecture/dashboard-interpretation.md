# Dashboard Interpretation

This document explains what the provisioned Grafana dashboards prove in the current PoC.

## Scope

- The canonical datasource is the provisioned `TimescaleDB` PostgreSQL datasource.
- The canonical dashboards are:
  - `infra/grafana/dashboards/audio_quality.json`
  - `infra/grafana/dashboards/system_health.json`
- The canonical SQL query surface is:
  - `audio_features`
  - `track_metadata`
  - `system_metrics`
  - `vw_dashboard_metric_events`
  - `vw_dashboard_run_validation`
  - `vw_dashboard_run_summary`

## Shared Metric Convention

The dashboards rely on the existing `system.metrics` contract and the shared label convention implemented in `src/event_driven_audio_analytics/shared/metric_labels.py`.

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
  - `scope=run_total` for replay-safe snapshot metrics
  - `scope=writer_record` for direct writer metrics keyed by Kafka record identity
  - `topic=<topic_name>` for append-only success or failure metrics tied to one topic
  - `status=ok|error` for append-only metrics
  - `failure_class=<reason>` only for error-path metrics

## Service Metric Ownership

- `ingestion` emits `tracks_total`, `segments_total`, `validation_failures`, and `artifact_write_ms` as run-level snapshots.
- `processing` emits append-only `processing_ms`, replay-safe `silent_ratio`, and error-path `feature_errors`.
- `writer` persists direct internal metrics `write_ms`, `rows_upserted`, and `write_failures` into `system_metrics`.

## Audio Quality Dashboard

### Segment RMS Over Time

- Query source: `audio_features`
- Meaning: average persisted `rms` per time bucket and `run_id`
- Why it matters: proves the pipeline preserves meaningful audio-energy differences after claim-check, processing, and persistence

### Silent Segment Ratio By Run

- Query source: `vw_dashboard_run_summary`
- Meaning: latest `silent_ratio` snapshot per run, with fallback to persisted `audio_features` summary
- Why it matters: proves the silent-oriented run is distinguishable from the energetic baseline without manual log inspection

### Persisted Segment Count By Run

- Query source: `vw_dashboard_run_summary`
- Meaning: persisted `audio_features` rows per run
- Why it matters: distinguishes healthy runs from validation-failure runs and exposes whether replayed inputs reached the sink

### Validation Outcomes By Run

- Query source: `vw_dashboard_run_validation`
- Meaning: `track_metadata.validation_status` counts per run
- Why it matters: shows that validation failures are ingestion outcomes, not hidden downstream breakage

### Run Quality Summary Table

- Query source: `vw_dashboard_run_summary`
- Meaning: run-level table combining counts, silent ratio, RMS, and validation failures
- Why it matters: provides a compact academic handoff table for the demo and report

## System Health Dashboard

### Persisted Segment Throughput

- Query source: `audio_features`
- Meaning: persisted feature-row count per time bucket and run
- Why it matters: provides the throughput signal using real sink-side data

### Processing Latency Over Time

- Query source: `vw_dashboard_metric_events`
- Meaning: average `processing_ms` per time bucket and run
- Why it matters: shows whether claim-check load plus DSP work stayed bounded during the demo runs

### Writer DB Latency By Topic

- Query source: `vw_dashboard_metric_events`
- Meaning: average writer `write_ms` grouped by destination topic
- Why it matters: keeps TimescaleDB persistence cost visible without external monitoring tooling

### Claim-Check Artifact Write Latency

- Query source: `vw_dashboard_run_summary`
- Meaning: run-level `artifact_write_ms` snapshot from ingestion
- Why it matters: proves the claim-check boundary has measurable write overhead before processing starts

### Track Validation Error Rate By Run

- Query source: `vw_dashboard_run_summary`
- Meaning: `validation_failures / tracks_total`
- Why it matters: gives the demo a defensible run-level error-rate panel without mixing track-scoped validation and segment-scoped runtime failures

### Operational Summary Table

- Query source: `vw_dashboard_run_summary`
- Meaning: run-level table for total errors, error rate, latency, and artifact-write cost
- Why it matters: supports report and demo narration without ad hoc SQL

## Demo Runs

The deterministic dashboard evidence path uses three stable demo runs:

- `week7-high-energy`: energetic baseline with `silent_ratio=0`
- `week7-silent-oriented`: mixed run with non-zero `silent_ratio`
- `week7-validation-failure`: ingestion-side `silent` rejection with zero persisted segments

## Evidence Artifacts

The dashboard evidence pack lives under `artifacts/demo/week7/`.

- `dashboard-demo-summary.json`
- `grafana-api.json`
- `audio_quality.png`
- `system_health.png`
- `demo-artifact-notes.md`

The final demo wrapper keeps those dashboard artifacts in place and adds restart/replay evidence under `artifacts/demo/week8/`.

The `week7` and `week8` directory names are retained because they are the stable evidence pack names already used throughout the repo. They are artifact locations, not new delivery phases.
