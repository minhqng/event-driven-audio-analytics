# Event Contract v1

## Purpose And Scope

- This file is the canonical Event Contract v1 for the current PoC.
- Scope is limited to the 4 primary topics already in active use or immediate implementation scope:
  - `audio.metadata`
  - `audio.segment.ready`
  - `audio.features`
  - `system.metrics`
- V1 is intentionally small. It exists to lock field names, traceability, replay-safety semantics, and claim-check boundaries before real ingestion and processing work expands.
- V1 does not model `audio.dlq` beyond noting that the topic remains reserved and outside the core contract set.

## Canonical V1 Envelope

All v1 events on the 4 primary topics must use this envelope:

- `event_id`
- `event_type`
- `event_version`
- `trace_id`
- `run_id`
- `produced_at`
- `source_service`
- `idempotency_key`
- `payload`

### Required Envelope Fields

- `event_id`: unique per emitted message. Opaque string. It is not the dedup key.
- `event_type`: must match the Kafka topic name exactly.
- `event_version`: fixed to `v1`.
- `trace_id`: end-to-end correlation id for one logical processing chain.
- `run_id`: identifier for one replay/demo/pipeline run.
- `produced_at`: event production timestamp in UTC RFC 3339 form.
- `source_service`: emitting service name. V1 uses `ingestion`, `processing`, or `writer`.
- `idempotency_key`: deterministic key derived from the logical identity of the event, not from transport metadata.
- `payload`: topic-specific object payload.

### Optional Envelope Fields

- None in v1. Unknown top-level fields are forbidden.

### Forbidden Envelope Patterns

- Do not use the old scaffold field names `schema_version`, `occurred_at`, or `produced_by` in new v1 events.
- Do not omit `run_id`, `trace_id`, or `idempotency_key`.
- Do not use `event_id` as a proxy for idempotency.
- Do not add undocumented top-level fields without updating docs, schemas, models, fixtures, and tests together.

## Canonical Payload Decisions

- V1 keeps the existing payload field names `genre`, `source_audio_uri`, and `labels_json` to avoid gratuitous churn against the current repo naming. Renaming those would be a v2 contract change, not an ad hoc v1 tweak.
- The 4 v1 payloads still repeat `run_id` inside `payload` for compatibility with the current writer-facing storage mapping.
- The top-level `run_id` is canonical. When payload `run_id` is present, it must match the top-level `run_id` exactly.
- Kafka remains small-event transport only. Large artifacts stay behind `artifact_uri` or other claim-check references.
- `artifact_uri` values are references inside the configured artifacts root. Consumers must resolve them against that root and reject paths that escape it.
- Payload numeric values must be JSON-finite. `NaN`, `Infinity`, and `-Infinity` are invalid contract values.

## Topic Contracts

### `audio.metadata`

Purpose:
- Track-level dimension data and validation context for one track within one `run_id`.

Required payload fields:
- `run_id`
- `track_id`
- `artist_id`
- `genre`
- `source_audio_uri`
- `validation_status`
- `duration_s`

Optional payload fields:
- `subset`
  - If present, it must be `small`.
  - Because the whole PoC is FMA-small-only, this field is descriptive, not a scope-expander.
- `manifest_uri`
  - Optional run-level manifest reference.
- `checksum`
  - Optional source or derived artifact checksum string.

Forbidden / must-not-do:
- No raw audio bytes, waveform arrays, or embedded file blobs.
- No label-map payloads or other training-pipeline-only structures.

### `audio.segment.ready`

Purpose:
- Claim-check handoff from ingestion to processing for one ready segment artifact.

Required payload fields:
- `run_id`
- `track_id`
- `segment_idx`
- `artifact_uri`
- `checksum`
- `sample_rate`
- `duration_s`
- `is_last_segment`

Optional payload fields:
- `manifest_uri`
  - Optional reference to the run-level or segmentation manifest.

Forbidden / must-not-do:
- No raw PCM, waveform blobs, or segment tensors in Kafka.
- No in-payload duplicate audio content when `artifact_uri` already points to the claim-check artifact.

### `audio.features`

Purpose:
- Feature summary and processing outcome for one segment, not the full tensor payload.

Required payload fields:
- `ts`
- `run_id`
- `track_id`
- `segment_idx`
- `artifact_uri`
- `checksum`
- `rms`
- `silent_flag`
- `mel_bins`
- `mel_frames`
- `processing_ms`

Optional payload fields:
- `manifest_uri`
  - Optional link back to the run or segment manifest.

Contract note:
- V1 encodes log-mel summary shape as `mel_bins=128` and `mel_frames=300`.
- The leading channel dimension is fixed to `1` by the agreed audio semantics and is therefore not duplicated as a separate payload field.

Forbidden / must-not-do:
- No full mel tensors, PCM, embeddings, or large model-ready arrays on Kafka.
- No feature payloads that drop `segment_idx`, because replay-safe writer identity depends on `(run_id, track_id, segment_idx)`.

### `system.metrics`

Purpose:
- Small operational metrics for observability and dashboards.

Required payload fields:
- `ts`
- `run_id`
- `service_name`
- `metric_name`
- `metric_value`

Optional payload fields:
- `labels_json`
  - Small label object for dimensions such as topic, status, or stage.
  - Replay-safe scopes are explicit. Current locked scopes are `run_total`, `processing_record`, and `writer_record`.
- `unit`
  - Optional measurement unit such as `ms`, `count`, or `ratio`.

Forbidden / must-not-do:
- No embedded checkpoint state or large debug dumps.
- No feature rows disguised as metrics events.

## Idempotency Key Rules

General rules:
- `idempotency_key` must be deterministic from the logical identity of the event.
- `idempotency_key` must not depend on `event_id` or `produced_at`.
- Replaying the same logical event in the same `run_id` must reproduce the same `idempotency_key`.
- A new logical event in the same run must produce a different `idempotency_key`.

Canonical v1 compositions:
- `audio.metadata`: `audio.metadata:v1:<run_id>:<track_id>`
- `audio.segment.ready`: `audio.segment.ready:v1:<run_id>:<track_id>:<segment_idx>`
- `audio.features`: `audio.features:v1:<run_id>:<track_id>:<segment_idx>`
- `system.metrics` append-only metrics: `system.metrics:v1:<run_id>:<service_name>:<metric_name>:<ts>:<labels_hash>`
- `system.metrics` snapshot metrics where `labels_json.scope=run_total`: `system.metrics:v1:<run_id>:<service_name>:<metric_name>:run_total:<labels_hash>`
- `system.metrics` consumed-record metrics where `labels_json.scope=processing_record`: `system.metrics:v1:<run_id>:<service_name>:<metric_name>:processing_record:<labels_hash>`
- `system.metrics` writer-record metrics where `labels_json.scope=writer_record`: `system.metrics:v1:<run_id>:<service_name>:<metric_name>:writer_record:<labels_hash>`

`labels_hash` rule for `system.metrics`:
- Compute SHA-256 over canonical JSON serialization of `labels_json`.
- Canonical JSON means sorted keys and no extra whitespace.
- Use the hash so metrics remain deterministic without inflating the event envelope.
Replay-safe scope rules:
- Treat `run_total`, `processing_record`, and `writer_record` metrics as logical rows keyed by `(run_id, service_name, metric_name, labels_json)`.
- Replays or timestamp refreshes for the same scoped metric must keep the same `idempotency_key`.
- The payload `ts` still records when that metric was observed; it is not part of replay-safe scoped identity.
- `processing_record` and `writer_record` labels must include Kafka record identity such as `topic`, `partition`, and `offset`.

## `trace_id` Rules

General rules:
- Preserve `trace_id` when one service is continuing the same logical chain from an upstream event.
- Do not regenerate `trace_id` on every hop if the event still belongs to the same logical chain.

Canonical v1 roots:
- Track-scoped events use `run/<run_id>/track/<track_id>`.
- Service-scoped metrics without a track identity use `run/<run_id>/service/<service_name>`.

Propagation expectations:
- `audio.metadata` starts a track-scoped trace.
- `audio.segment.ready` for the same track keeps the same track-scoped trace id.
- `audio.features` emitted from a consumed `audio.segment.ready` event preserves that trace id.
- `system.metrics` preserves the active trace when it describes a specific processing chain; otherwise it falls back to the service-scoped form above.

## `run_id` Rules

- `run_id` identifies one pipeline replay/demo/execution session.
- It is created once at run start by the human operator, orchestration layer, or explicit run bootstrap.
- It must remain stable across all events, artifacts, checkpoints, and persistence rows for that run.
- It must not be regenerated per track or per segment.
- Recommended form is a lowercase slug, optionally timestamp-suffixed for uniqueness.
- It must be one path segment. Empty values, whitespace, `.`, `..`, `/`, `\`, and `:` are forbidden.
- Artifact paths remain anchored under `/artifacts/runs/<run_id>/...`.

## Serialization, Timestamps, And Versioning

- Kafka message values are UTF-8 JSON object envelopes.
- Runtime JSON serialization and deserialization must reject non-standard JSON constants such as `NaN` and `Infinity`.
- `produced_at` and payload timestamps such as `ts` use RFC 3339 UTC timestamps.
- Prefer the compact `Z` suffix form, for example `2026-04-02T00:00:00Z`.
- `event_version` is semantic contract version, not an implementation build number.
- Any field rename, removal, incompatible type change, or changed meaning requires a new event version.
- Minor implementation changes that do not affect the event contract stay within `v1`.

## Explicitly Banned Patterns

- No raw PCM or large tensors in Kafka payloads.
- No missing `run_id`, `trace_id`, or `idempotency_key`.
- No silent contract drift across docs, schemas, models, fixtures, and tests.
- No topic messages whose `event_type` does not match the topic.
- No idempotency keys derived only from random ids or wall-clock timestamps.
- No unreviewed field additions that bypass A/B synchronization when they affect shared boundaries.

## Open Questions / A-B Sync Items

- The v1 contract is now locked in docs, schemas, shared models, contract tests, and the bounded runtime demo/smoke path.
- `audio.dlq` remains reserved but is not part of the 4-topic core v1 contract.
- The long-term dedup/persistence policy for `system.metrics` remains open beyond the currently locked replay-safe scopes.
