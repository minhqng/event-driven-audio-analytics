# IMPLEMENTATION_STATUS.md

Final implementation summary for the current repository state.

## Interpretation

- `Fact`: explicit in current repo docs, code, fixtures, or recorded evidence.
- `Inference`: derived from the current repo state and bounded evidence.
- `Conflict`: current repo state and planning documents still disagree.
- `Unknown`: not fixed or not yet verified.

## Final Repo State

- `Fact`: The repository is a runnable PoC, not a production platform.
- `Fact`: The runtime stack is Docker Compose, Kafka KRaft, shared claim-check storage, TimescaleDB, Grafana, and three core services: `ingestion`, `processing`, and `writer`.
- `Fact`: Event Contract v1 is locked in `event-contracts.md` and aligned across `schemas/`, shared models, fixtures, tests, and the current bounded runtime path.
- `Fact`: The repo demonstrates claim-check, event-driven decoupling, idempotent sink behavior, checkpoint-aware offset handling, and dashboard-backed observability.
- `Fact`: The repo includes a documented final demo path, a dashboard-only demo path, targeted smoke flows, and an official containerized `pytest` path.
- `Fact`: The current official `pytest` baseline is `176 passed, 5 skipped`; the skipped tests are the optional legacy-reference parity checks when local reference inputs or extra reference dependencies are unavailable.

## What Is Fully Implemented

### Ingestion

- `Fact`: Metadata ETL handles the flattened FMA `tracks.csv` header and `subset=small` filtering.
- `Fact`: Validation covers file presence, probe/open readiness, duration, decode/resample, silence rejection, and no-segment rejection.
- `Fact`: Audio is decoded and resampled to mono 32 kHz.
- `Fact`: Segmentation uses 3.0-second windows with 1.5-second overlap.
- `Fact`: Claim-check artifacts are written as WAV files under `/artifacts/runs/<run_id>/segments/...`.
- `Fact`: A run manifest is written under `/artifacts/runs/<run_id>/manifests/segments.parquet`.
- `Fact`: `ingestion` publishes canonical `audio.metadata`, `audio.segment.ready`, and run-level `system.metrics` events.

### Processing

- `Fact`: `processing` consumes `audio.segment.ready`, loads claim-check artifacts, validates checksums, computes RMS, silence decisions, log-mel summaries, and Welford-style monitoring output, and publishes `audio.features` plus `system.metrics`.
- `Fact`: The log-mel summary shape remains locked to `(1,128,300)`.
- `Fact`: `processing` persists replay-stable run state for `silent_ratio` under `/artifacts/runs/<run_id>/state/processing_metrics.json`.
- `Fact`: `processing` is a long-lived Kafka consumer with startup preflight, bounded retry for recoverable artifact-readiness failures, structured logging, and graceful shutdown handling.

### Writer, Persistence, And Observability

- `Fact`: `writer` consumes canonical `audio.metadata`, `audio.features`, and `system.metrics` envelopes.
- `Fact`: `writer` persists rows transactionally into `track_metadata`, `audio_features`, `system_metrics`, and `run_checkpoints`.
- `Fact`: Offset commits happen only after successful persistence and checkpoint update.
- `Fact`: Replay-safe `system.metrics` snapshots with `labels_json.scope=run_total` are upserted with duplicate repair on the current Timescale path.
- `Fact`: Grafana datasource and dashboards are provisioned from files.
- `Fact`: The canonical dashboard SQL surface is `vw_dashboard_metric_events`, `vw_dashboard_run_validation`, and `vw_dashboard_run_summary`.

### Validation, Correctness, And Evidence

- `Fact`: The repo provides targeted smoke flows for ingestion, processing, processing-to-writer persistence, restart/replay, and fake-event writer verification.
- `Fact`: The repo provides deterministic dashboard demo evidence under `artifacts/demo/week7/`.
- `Fact`: The repo provides bounded restart/replay evidence under `artifacts/demo/week8/`.
- `Fact`: `correctness-against-reference.md` records the current audio/DSP parity position against the legacy FMA-small pipeline.
- `Fact`: `REUSE_MAP.md` records the legacy-pipeline reuse and refactor map.

## Verified Reader And Demo Path

- `Fact`: `README.md` now points to the final reader path and the final demo command.
- `Fact`: `docs/README.md` is the documentation entrypoint.
- `Fact`: `docs/runbooks/demo.md` is the primary demo runbook.
- `Fact`: `docs/runbooks/dashboard-demo.md` is the dashboard-only companion runbook.
- `Fact`: `docs/runbooks/validation.md` is the validation and smoke-check runbook.
- `Fact`: Historical bootstrap documentation has been moved out of the main reader path into `docs/archive/`.

## Accepted Limitations

- `Fact`: `audio.dlq` is reserved in bootstrap/constants but is not yet a fully modeled or exercised runtime path.
- `Fact`: `welford_snapshots` exists in SQL, but the current processing runtime does not persist that state.
- `Fact`: The default demo path is bounded to committed smoke fixtures and deterministic dashboard inputs, not a benchmark-scale run.
- `Fact`: The default repo does not claim a 100-track burst, benchmark latency, or production HA behavior.
- `Fact`: Exactly-once end to end is out of scope; the correctness target remains at-least-once plus idempotent sink behavior.

## Current Conflicts And Drift

- `Conflict`: `audio.dlq` is reserved in the repo, but the repo still lacks matching schema/model/fixture coverage and a real DLQ publish/consume flow.
- `Conflict`: The logical identity for feature rows is `(run_id, track_id, segment_idx)`, while the current Timescale physical primary key still includes `ts`.
- `Conflict`: Planning documents disagree on overall schedule length: 8 weeks versus 10 weeks.
- `Conflict`: The inherited RMS helper returns `-inf` for truly silent audio, while the locked v1 event contract requires JSON-finite `rms`; the current transport path clamps non-finite values to `-60.0` while preserving `silent_flag=true`.
- `Conflict`: `welford_snapshots` storage exists without a processing-side persisted producer path.

## Explicitly Deferred

- `Fact`: 100-track burst and benchmark-scale evidence
- `Fact`: Real DLQ implementation
- `Fact`: Persisted `welford_snapshots`
- `Fact`: Kubernetes, service mesh, multi-node Kafka, HA/DR
- `Fact`: Full schema registry/governance stack
- `Fact`: Production object storage/IAM, online inference, and broader MLOps
- `Fact`: Full OpenTelemetry collector/backend stack

## Archived Delivery History

This section is retained only to reconcile the finished repo against the original planning language.

| Archived phase label | Planned meaning | Final repo result |
| --- | --- | --- |
| Week 1 / Phase 1 | Scope lock, infra bootstrap, reuse audit | `Fact`: complete. Infra bring-up, fixture strategy, and reuse map are documented. |
| Week 2 / Phase 2 | Shared layer, event contract, DB schema, fake-event smoke path | `Fact`: complete within v1 scope. `Conflict`: DLQ contract remains unresolved. |
| Week 3 / Phase 3 | Ingestion on real sample data | `Fact`: complete for the bounded PoC path. |
| Week 4 / Phase 4 | Processing / feature emission | `Fact`: complete for the bounded PoC path. |
| Week 5 / Phase 5 | Writer idempotency and checkpoints | `Fact`: complete for the bounded PoC path. |
| Week 6 / Phase 6 | Dashboards / observability | `Fact`: complete for the bounded PoC path. |
| Week 7 / Phase 7 | Hardening / restart / benchmark prep | `Fact`: restart/replay hardening is complete on the bounded path. `Fact`: benchmark prep beyond that remains deferred. |
| Week 8 / Phase 8 | Freeze / polish / demo readiness | `Fact`: complete within locked PoC scope. |
| Weeks 9-10 | Extended-plan benchmark and freeze split | `Conflict`: present only in one planning document; no repo evidence yet. |

## Items Requiring Member A/B Synchronization

- `Fact`: Whether `audio.dlq` becomes an active contract in a future revision
- `Fact`: Natural-key strategy versus Timescale physical-key constraints
- `Fact`: Checkpoint semantics and replay behavior if extended beyond the current bounded path
- `Fact`: Any manifest field-set expansion used by more than ingestion
- `Fact`: Any contract, schema, or retention change that crosses ingestion, processing, and writer boundaries
