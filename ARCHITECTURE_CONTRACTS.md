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
- `Conflict`: The detailed plan includes `audio.dlq`, and the current repo now reserves that topic in bootstrap/constants, but the DLQ contract is not yet fully modeled or exercised.

## Claim-Check Design

- `Fact`: Large audio or feature payloads must not be transported directly on Kafka as the normal path.
- `Fact`: Shared storage under `artifacts/` is the current PoC claim-check boundary.
- `Fact`: Artifact path shape is stable under `/artifacts/runs/<run_id>/...`.
- `Fact`: A run-level manifest belongs under `/artifacts/runs/<run_id>/manifests/segments.parquet`.
- `Fact`: Optional feature artifacts may live under `/artifacts/runs/<run_id>/features/<track_id>/<segment_idx>.*`.
- `Fact`: Reference assets may live under `/artifacts/shared/reference/`.
- `Conflict`: The detailed plan allows `.npy` or `.wav` for stored segments; the current repo helper emits `.wav` paths.

## Canonical Target Envelope

- `Fact`: The detailed project plan defines the target event envelope as:
- `Fact`: `event_id`
- `Fact`: `event_type`
- `Fact`: `event_version`
- `Fact`: `trace_id`
- `Fact`: `run_id`
- `Fact`: `produced_at`
- `Fact`: `source_service`
- `Fact`: `idempotency_key`
- `Fact`: `payload`

## Current Scaffold Envelope Drift

- `Conflict`: The current repo implements a smaller envelope with:
- `Conflict`: `event_id`
- `Conflict`: `event_type`
- `Conflict`: `schema_version`
- `Conflict`: `occurred_at`
- `Conflict`: `produced_by`
- `Conflict`: `payload`
- `Conflict`: The current repo omits `trace_id`, top-level `run_id`, and `idempotency_key`.
- `Conflict`: The current repo uses `schema_version`/`occurred_at`/`produced_by` instead of `event_version`/`produced_at`/`source_service`.
- `Rule`: Do not expand or shrink the envelope casually. Any reconciliation must update schemas, models, fixtures, docs, and writer logic together.

## Topic Naming And Ownership

| Topic | Kafka Key | Producer | Main Consumer | Stable Intent | Current Repo Status |
| --- | --- | --- | --- | --- | --- |
| `audio.metadata` | `track_id` | `ingestion` | `writer` | Track metadata and validation status for persistence and dashboards | Present |
| `audio.segment.ready` | `track_id` | `ingestion` | `processing` | Claim-check reference to a ready segment artifact | Present |
| `audio.features` | `track_id` | `processing` | `writer` | Feature summaries and processing quality data | Present |
| `system.metrics` | `service_name` in plan | all core services | `writer` and Grafana queries/views | Operational metrics and health/throughput signals | Present |
| `audio.dlq` | `original_key` | any service | ops/debug only | Failed-event holding area with error context | Reserved in bootstrap/constants; no schema/model/fixture or runtime DLQ flow yet |

## Payload Contracts

### `audio.metadata`

- `Fact`: Stable intent is track-level dimension data for a specific run.
- `Fact`: Target fields from the detailed plan: `run_id`, `track_id`, `artist_id`, `genre_label`, `source_path`, `validation_status`, `duration_s`.
- `Conflict`: Current repo schema/model uses `genre`, `subset`, `source_audio_uri`, optional `manifest_uri`, and optional `checksum`.

### `audio.segment.ready`

- `Fact`: Stable intent is the claim-check handoff after segmentation.
- `Fact`: Stable fields across docs/repo: `run_id`, `track_id`, `segment_idx`, `artifact_uri`, `checksum`, `sample_rate`, `duration_s`, `is_last_segment`.
- `Fact`: A manifest reference is part of the current repo contract.
- `Conflict`: The detailed plan names `produced_by` inside payload; the repo does not.

### `audio.features`

- `Fact`: Stable intent is a feature summary, not a full feature tensor in the database path.
- `Fact`: Stable fields across docs/repo: `run_id`, `track_id`, `segment_idx`, `rms`, `silent_flag`, `processing_ms`.
- `Fact`: Current repo contract also includes `ts`, `artifact_uri`, `checksum`, `manifest_uri`, `mel_bins`, and `mel_frames`.
- `Conflict`: The detailed plan expresses the mel output more abstractly as `mel_shape`, optional `feature_uri`, and optional `welford_state_ref`.

### `system.metrics`

- `Fact`: Stable intent is service-level operational metrics.
- `Fact`: Stable fields across docs/repo: timestamp, `run_id`, `service_name`, `metric_name`, `metric_value`.
- `Conflict`: The detailed plan uses `unit` and `labels`; the current repo uses `labels_json` and omits `unit`.
- `Unknown`: Whether system metrics should be purely append-only or partially deduplicated is not fixed.

## Idempotency Rules

- `Fact`: Delivery semantics for the PoC are at-least-once.
- `Fact`: Writer persistence must be idempotent.
- `Fact`: Replay of the same logical run must not silently duplicate feature rows.
- `Fact`: Offset commit must happen only after successful persistence and checkpoint update.
- `Fact`: Producer idempotence and `acks=all` are part of the intended Kafka posture for the PoC.
- `Conflict`: The current repo enables idempotent producer config, but the current envelope does not yet carry the planned `idempotency_key`.

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

- `Fact`: JSON schema files in `schemas/`.
- `Fact`: Shared event/payload models in `src/event_driven_audio_analytics/shared/models/`.
- `Fact`: Topic constants and Kafka helpers in `src/event_driven_audio_analytics/shared/`.
- `Fact`: SQL tables/views in `infra/sql/`.
- `Fact`: Event fixtures under `tests/fixtures/events/`.
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

- `Unknown`: Final canonical envelope naming after repo-target reconciliation.
- `Unknown`: Whether `audio.dlq` graduates from a reserved bootstrap topic into the first fully modeled runnable contract.
- `Unknown`: Final system-metrics label/unit convention.
- `Unknown`: Final producer/update semantics for `welford_snapshots`.
