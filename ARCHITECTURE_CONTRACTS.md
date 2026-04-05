# ARCHITECTURE_CONTRACTS.md

## Interpretation

- `Fact`: explicit in attached documents or current repo docs/code.
- `Conflict`: attached documents and repo drift disagree.
- `Unknown`: not fixed yet.

## Architecture Overview

- `Fact`: The system is organized around 4 core subsystems: Ingestion, Streaming, Processing, Visualization.
- `Inference`: The current repo realizes this as 3 runtime services plus platform components.
- `Fact`: Platform components are Kafka KRaft, shared claim-check storage, TimescaleDB, and Grafana.
- `Fact`: The PoC boundary is small-event transport on Kafka plus large-payload indirection through claim-check storage.

## Service Boundaries

- `Fact`: `ingestion` owns metadata loading, validation, decode/resample, segmentation planning, artifact writing, and publication of `audio.metadata` and `audio.segment.ready`.
- `Fact`: `processing` owns artifact loading, checksum validation, RMS, silence gate, log-mel summary generation, Welford-style monitoring updates, and publication of `audio.features` plus `system.metrics`.
- `Fact`: `writer` owns ingestion of metadata/features/metrics events, persistence into TimescaleDB, checkpoint updates, and offset commits only after persistence succeeds.
- `Fact`: Grafana is file-provisioned. Do not treat click-ops in the UI as the canonical configuration path.
- `Fact`: The streaming subsystem owns ordering and replay semantics through Kafka topic keys, partitions, and consumer groups.

## Event Flow

- `Fact`: `audio.metadata` provides track-level dimension data.
- `Fact`: `audio.segment.ready` is the claim-check handoff from ingestion to processing.
- `Fact`: `audio.features` is the feature-summary handoff from processing to writer.
- `Fact`: `system.metrics` is emitted by runtime services for dashboards and operational views.
- `Fact`: Writer-owned internal metrics `write_ms`, `rows_upserted`, and best-effort `write_failures` are written directly into the TimescaleDB `system_metrics` table and are not published back to Kafka.
- `Conflict`: The detailed plan includes `audio.dlq`, and the current repo now reserves that topic in bootstrap/constants, but the DLQ contract is not yet fully modeled or exercised.

## Claim-Check Design

- `Fact`: Large audio or feature payloads must not be transported directly on Kafka as the normal path.
- `Fact`: Shared storage under `artifacts/` is the current PoC claim-check boundary.
- `Fact`: Artifact path shape is stable under `/artifacts/runs/<run_id>/...`.
- `Fact`: A run-level manifest belongs under `/artifacts/runs/<run_id>/manifests/segments.parquet`.
- `Fact`: Processing-owned replay-stable runtime state for `silent_ratio` currently lives under `/artifacts/runs/<run_id>/state/processing_metrics.json`.
- `Fact`: Optional feature artifacts may live under `/artifacts/runs/<run_id>/features/<track_id>/<segment_idx>.*`.
- `Fact`: Reference assets may live under `/artifacts/shared/reference/`.
- `Conflict`: The detailed plan allows `.npy` or `.wav` for stored segments; the current repo helper emits `.wav` paths.

## Canonical V1 Envelope

- `Fact`: Event Contract v1 is now locked in `event-contracts.md`.
- `Fact`: The canonical envelope fields are:
- `Fact`: `event_id`
- `Fact`: `event_type`
- `Fact`: `event_version`
- `Fact`: `trace_id`
- `Fact`: `run_id`
- `Fact`: `produced_at`
- `Fact`: `source_service`
- `Fact`: `idempotency_key`
- `Fact`: `payload`
- `Rule`: Do not expand or shrink the envelope casually. Any change must update docs, schemas, shared models, fixtures, and tests together.

## Remaining Implementation Drift

- `Fact`: The shared contract layer, writer runtime, and fake-event smoke path now use the canonical v1 envelope names.
- `Fact`: Shared semantic validation now enforces `run_id` consistency between the top-level envelope and payload.
- `Fact`: Contract-definition drift is resolved for the current fixture-driven runtime path, and broker-backed smoke runs now exercise the canonical v1 envelope through `ingestion`, `processing`, and `writer` on `audio.metadata`, `audio.segment.ready`, `audio.features`, and `system.metrics`.

## Topic Naming And Ownership

| Topic | Kafka Key | Producer | Main Consumer | Stable Intent | Current Repo Status |
| --- | --- | --- | --- | --- | --- |
| `audio.metadata` | `track_id` | `ingestion` | `writer` | Track metadata and validation status for persistence and dashboards | Present |
| `audio.segment.ready` | `track_id` | `ingestion` | `processing` | Claim-check reference to a ready segment artifact | Present |
| `audio.features` | `track_id` | `processing` | `writer` | Feature summaries and processing quality data | Present |
| `system.metrics` | `service_name` in plan | all core services | `writer` and Grafana queries/views | Operational metrics and health/throughput signals | Present |
| `audio.dlq` | `original_key` | any service | ops/debug only | Failed-event holding area with error context | Reserved in bootstrap/constants; no schema/model/fixture or runtime DLQ flow yet, and current ingestion runtime logs unrecoverable failures explicitly instead of publishing DLQ events |

## Payload Contracts

### `audio.metadata`

- `Fact`: Stable intent is track-level dimension data for a specific run.
- `Fact`: Canonical v1 payload fields are `run_id`, `track_id`, `artist_id`, `genre`, `source_audio_uri`, `validation_status`, and `duration_s`.
- `Fact`: `subset` remains optional and, when present, is fixed to `small`.
- `Fact`: `manifest_uri` and `checksum` remain optional in v1.
- `Fact`: Current writer schema/persistence now stores `duration_s` in `track_metadata`.
- `Inference`: V1 deliberately keeps the current repo field names `genre` and `source_audio_uri` to avoid gratuitous v1 churn.

### `audio.segment.ready`

- `Fact`: Stable intent is the claim-check handoff after segmentation.
- `Fact`: Canonical v1 payload fields are `run_id`, `track_id`, `segment_idx`, `artifact_uri`, `checksum`, `sample_rate`, `duration_s`, and `is_last_segment`.
- `Fact`: `manifest_uri` is optional in v1.
- `Fact`: No service-identity field lives inside the payload because `source_service` is now canonical at the envelope level.

### `audio.features`

- `Fact`: Stable intent is a feature summary, not a full feature tensor in the database path.
- `Fact`: Canonical v1 payload fields are `ts`, `run_id`, `track_id`, `segment_idx`, `artifact_uri`, `checksum`, `rms`, `silent_flag`, `mel_bins`, `mel_frames`, and `processing_ms`.
- `Fact`: `manifest_uri` remains optional in v1.
- `Inference`: V1 encodes the fixed `(1,128,300)` log-mel summary shape using `mel_bins=128` and `mel_frames=300`; the leading channel dimension remains implicit because it is fixed by the agreed audio semantics.

### `system.metrics`

- `Fact`: Stable intent is service-level operational metrics.
- `Fact`: Canonical v1 payload fields are `ts`, `run_id`, `service_name`, `metric_name`, and `metric_value`.
- `Fact`: `labels_json` and `unit` are optional in v1.
- `Fact`: Current writer schema/persistence now stores optional `unit` alongside `labels_json`.
- `Inference`: V1 keeps the current repo field name `labels_json` to stay aligned with the current scaffold and SQL naming.
- `Fact`: The shared contract layer and current writer persistence now treat `labels_json.scope=run_total` metrics as replay-safe snapshots keyed by `(run_id, service_name, metric_name, labels_json)`.
- `Fact`: Under the writer advisory lock, historical duplicate `scope=run_total` rows are repaired down to one logical row before the snapshot row is rewritten from the latest payload, and `ts` is refreshed from that latest snapshot payload; other system metrics remain append-only.
- `Fact`: The current Week 5 `processing` runtime persists run-scoped segment identity under `/artifacts/runs/<run_id>/state/processing_metrics.json`, which keeps `silent_ratio` `run_total` snapshots stable across service restarts for the same logical run.
- `Fact`: The current Week 5 `processing` runtime emits per-segment `processing_ms` metrics with `labels_json={"topic":"audio.features","status":"ok"}`, `silent_ratio` `run_total` snapshots with `labels_json={"scope":"run_total"}`, and best-effort terminal `feature_errors` metrics with `labels_json.failure_class` describing the failure path.
- `Fact`: The current Week 6 `writer` runtime writes replay-safe per-record `write_ms`, `rows_upserted`, and best-effort `write_failures` metrics keyed by `labels_json.scope=writer_record` plus Kafka `topic` / `partition` / `offset`; `write_failures` also carries `labels_json.failure_class`.

## Idempotency Rules

- `Fact`: Delivery semantics for the PoC are at-least-once.
- `Fact`: Writer persistence must be idempotent.
- `Fact`: Replay of the same logical run must not silently duplicate feature rows.
- `Fact`: Offset commit must happen only after successful persistence and checkpoint update.
- `Fact`: The current Week 6 `writer` runtime exits on payload-write, checkpoint-write, or offset-commit failure so the service cannot continue and accidentally commit past a failed record.
- `Fact`: Producer idempotence and `acks=all` are part of the intended Kafka posture for the PoC.
- `Fact`: Canonical v1 now defines `idempotency_key` in the shared contract layer.
- `Fact`: Event-type-specific key composition is documented in `event-contracts.md`.
- `Fact`: The current writer runtime now accepts the canonical v1 envelope, including `idempotency_key`, on the fixture-driven smoke path.

## Natural Keys

- `Fact`: `track_metadata` identity is `(run_id, track_id)`.
- `Fact`: The planned logical identity for feature summaries is `(run_id, track_id, segment_idx)`.
- `Conflict`: Current Timescale SQL uses physical primary key `(ts, run_id, track_id, segment_idx)` because hypertable uniqueness includes the partition column.
- `Inference`: Treat `ts` as a physical storage constraint and `(run_id, track_id, segment_idx)` as the domain identity unless the project explicitly redefines this.
- `Fact`: Current checkpoint identity is `(consumer_group, topic_name, partition_id)`.

## Checkpoint Rules

- `Fact`: Checkpoints exist to support restart/resume behavior.
- `Fact`: Checkpoints must move forward only after successful write completion.
- `Fact`: Checkpoint semantics are cross-owned and require A/B review when changed.
- `Unknown`: The final checkpoint payload/state model beyond current offset storage is not fixed.

## Schema Boundaries That Must Stay Aligned

- `Fact`: Root contract document `event-contracts.md`.
- `Fact`: JSON schema files in `schemas/`.
- `Fact`: Shared event/payload models in `src/event_driven_audio_analytics/shared/models/`.
- `Fact`: Topic constants and Kafka helpers in `src/event_driven_audio_analytics/shared/`.
- `Fact`: SQL tables/views in `infra/sql/`.
- `Fact`: Canonical event fixtures under `tests/fixtures/events/v1/`.
- `Fact`: Contract docs under repo root and `docs/architecture/`.
- `Rule`: No contract change is done until all of these agree.

## Stable Audio Semantics

- `Fact`: Dataset scope is FMA-small only.
- `Fact`: Metadata filter is `subset=small`.
- `Fact`: Decode/resample target is mono / 32 kHz.
- `Fact`: Segment duration is 3.0 seconds.
- `Fact`: Segment overlap is 1.5 seconds.
- `Fact`: Log-mel target shape is `(1,128,300)` in the reused pipeline semantics.
- `Fact`: Silence gating and Welford-style monitoring statistics are part of the intended processing path.

## Unresolved Contract Items

- `Unknown`: Whether `audio.dlq` graduates from a reserved bootstrap topic into the first fully modeled runnable contract.
- `Unknown`: Final system-metrics dedup treatment beyond the current `scope=run_total` snapshot-upsert rule is not fixed.
- `Unknown`: Final producer/update semantics for `welford_snapshots`.
