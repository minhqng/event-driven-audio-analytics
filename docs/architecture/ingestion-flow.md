# Ingestion Flow

## Purpose

- `Fact`: This document records the current Week 4-stable Member B ingestion baseline for reporting and handoff.
- `Fact`: Scope is limited to metadata ETL, validation, decode/resample, segmentation, artifact writing, checksum handling, manifest handling, and emission of `audio.metadata` plus `audio.segment.ready`.
- `Fact`: It does not redefine the locked v1 event contract or any Member A-owned SQL, checkpoints, Kafka bootstrap, or dashboard wiring.

## Current Flow

1. `Fact`: `ingestion` parses `tracks.csv` with the legacy-compatible 3-row FMA header flattening logic.
2. `Fact`: Metadata loading keeps only `subset=small` rows with non-empty top-level genre, requires positive `track.duration`, and resolves canonical FMA audio paths as `<folder>/<track_id>.mp3`.
3. `Fact`: Validation happens before segmentation:
   - physical file existence
   - probe/open readiness
   - minimum duration `>= 1.0 s`
   - PyAV decode plus mono / 32 kHz resample
   - full-track RMS silence rejection at `-60.0 dB`
4. `Fact`: Segmentation happens after successful decode/resample using the inherited `3.0 s` window, `1.5 s` overlap, and `remaining_tail > 1.0 s` padding rule.
5. `Fact`: For tracks that produce at least one legal segment, WAV claim-check artifacts are written under `/artifacts/runs/<run_id>/segments/<track_id>/<segment_idx>.wav`.
6. `Fact`: A run manifest is written under `/artifacts/runs/<run_id>/manifests/segments.parquet`.
7. `Fact`: After artifact write, ingestion verifies artifact existence, SHA-256 checksum, and descriptor-to-manifest row consistency before publishing segment-ready events.
8. `Fact`: `audio.metadata` is emitted once per track.
9. `Fact`: `audio.segment.ready` is emitted once per written segment after the metadata event for that same track.

## Checksum And Manifest Baseline

- `Fact`: `audio.metadata.checksum` currently carries the source-audio file checksum when the source file exists.
- `Fact`: `audio.metadata.duration_s` uses probe-derived duration when available and otherwise falls back to the positive metadata-side `track.duration` value.
- `Fact`: `audio.segment.ready.checksum` carries the written segment artifact checksum.
- `Fact`: The current run manifest stores the same segment checksum that is carried in `audio.segment.ready`.
- `Fact`: Current manifest required fields are:
  - `run_id`
  - `track_id`
  - `segment_idx`
  - `artifact_uri`
  - `checksum`
  - `manifest_uri`
  - `sample_rate`
  - `duration_s`
  - `is_last_segment`
- `Fact`: Current manifest optional fields: none.
- `Inference`: The manifest field set is now enforced by ingestion-owned code and tests, but it is not yet a separately locked cross-service contract in the same way as `event-contracts.md`.

## Reject Behavior

- `Fact`: `missing_file` rejects a row before probe/decode and emits metadata only.
- `Fact`: `probe_failed` rejects a row when the source cannot be opened/probed and emits metadata only.
- `Fact`: `too_short` rejects any clip with probed duration below `1.0 s` and emits metadata only.
- `Fact`: `decode_failed` rejects any file that probes successfully but fails during decode/resample and emits metadata only.
- `Fact`: `silent` rejects any decoded track whose full-track RMS falls below `-60.0 dB` and emits metadata only.
- `Fact`: `no_segments` rejects decoded audio that passes the earlier validation stages but yields zero legal segments under the inherited tail-padding rule and emits metadata only.
- `Fact`: Reject paths do not emit `audio.segment.ready`.
- `Fact`: Reject paths do not advertise a `manifest_uri`.

## Downstream Alignment

- `Fact`: The ingestion-side `AudioMetadataPayload` still maps 1:1 onto the current writer `track_metadata` expectation:
  - `run_id`
  - `track_id`
  - `artist_id`
  - `genre`
  - `subset`
  - `source_audio_uri`
  - `validation_status`
  - `duration_s`
  - `manifest_uri`
  - `checksum`
- `Fact`: Current repo-owned tests now check that `AudioMetadataPayload` field names exactly match the writer `TRACK_METADATA_UPSERT` column set.
- `Fact`: Reject paths such as `missing_file` and `probe_failed` stay contract-valid because ingestion now requires positive metadata-side `track.duration` for the selected subset.

## Representative Week 4 Checks

| Sample | Observed outcome | Notes |
| --- | --- | --- |
| `valid_synthetic_stereo_44k1.mp3` | validated, `3` segment artifacts | Source checksum in `audio.metadata`; artifact checksum carried in manifest and `audio.segment.ready` |
| `silent_mono_32k.wav` | `silent`, metadata only | No manifest or segment events |
| `short_tone_mono_32k.wav` | `too_short`, metadata only | Duration stays below the `1.0 s` minimum |
| `corrupt_audio.mp3` | `probe_failed`, metadata only | File checksum exists, probe/open does not |
| generated `1.00 s` tone | `no_segments`, metadata only | Explicit Week 4 edge-case reject |
| generated `1.01 s` tone | validated, `1` segment | Smallest practical segment-producing clip in current checks |
| generated `3.00 s` tone | validated, `2` segments | Inherited overlap + tail rule, not a new Week 4 convention |
| generated `4.49 s` tone | validated, `2` segments | Tail still pads because remaining audio stays above `1.0 s` |
| generated `4.51 s` tone | validated, `3` segments | Crosses the next overlapped-window boundary |
| generated `29.95 s` tone | validated, `19` segments | Matches existing legacy-reference tolerance note |
| generated `30.60 s` tone | validated, `20` segments | Matches existing legacy-reference tolerance note |

## Legacy Parity Notes

- `Fact`: Path layout remains under `/artifacts/runs/<run_id>/...`, which stays aligned with the locked claim-check convention.
- `Fact`: Segmentation semantics remain `mono / 32 kHz`, `3.0 s`, `1.5 s overlap`, and `remaining_tail > 1.0 s`.
- `Fact`: Existing repo notes from Week 3 and `REUSE_MAP.md` still record legacy-reference segment counts of `19` for track `2` and `20` for track `666`.
- `Inference`: The current duration-boundary matrix keeps the same tail-padding behavior that the inherited legacy segmentation algorithm implies; the Week 4 work hardened that behavior and documented it rather than changing it.

## Remaining A/B Sync Items

- `Inference`: `validation_status=no_segments` now exists as an explicit ingestion outcome; writer stores it as text without schema changes, but dashboards/reporting should treat it as a distinct reject class instead of folding it into silence or corrupt-file counts.
- `Inference`: If processing or writer later depend on extra manifest columns, that field-set change should be reviewed explicitly instead of being treated as an ingestion-only local detail.
