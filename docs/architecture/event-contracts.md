# Event Contracts

## Envelope

All topic messages use the shared envelope defined in `schemas/envelope.v1.json`:

- `event_id`
- `event_type`
- `schema_version`
- `occurred_at`
- `produced_by`
- `payload`

## Topics

### `audio.metadata`

- Carries track-level dimension data for writer persistence and dashboards.
- Payload placeholders include `run_id`, `track_id`, `artist_id`, `genre`, `subset`, `source_audio_uri`, `validation_status`, and optional `manifest_uri` / `checksum`.

### `audio.segment.ready`

- Claim-check event that signals a segment is available in shared storage.
- Payload placeholders include `artifact_uri`, `checksum`, and `manifest_uri` in addition to `run_id`, `track_id`, `segment_idx`, `sample_rate`, `duration_s`, and `is_last_segment`.

### `audio.features`

- Summary event emitted by processing after artifact loading and feature extraction.
- Payload placeholders include `ts`, `run_id`, `track_id`, `segment_idx`, `artifact_uri`, `checksum`, `manifest_uri`, `rms`, `silent_flag`, `mel_bins`, `mel_frames`, and `processing_ms`.

### `system.metrics`

- Minimal operational metric event for dashboards and operational views.
- Payload placeholders are fixed around `ts`, `run_id`, `service_name`, `metric_name`, `metric_value`, and `labels_json`.
