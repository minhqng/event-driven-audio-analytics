# Correctness Against Reference

## Scope

This document records the first Week 6 Member B correctness pass for the current `processing` path against the legacy FMA-small pipeline semantics described in `REUSE_MAP.md`.

Compared path in this repo:

- current shared decode/resample
- current 3.0 s / 1.5 s segmentation
- current WAV claim-check artifact round-trip
- current `processing` RMS, silence gate, log-mel extraction, and vector-valued Welford updates
- current `audio.features` summary payload shape

Legacy/reference basis:

- `references/legacy-fma-pipeline/fma-small-audio-pipeline-main/src/features/audio_transforms.py`
- legacy segment silence rule `mel.std() < 1e-7`
- legacy Welford update rule from `src/utils/helpers.py::compute_global_stats`

Out of scope for this pass:

- writer SQL changes
- benchmark-scale runs
- benchmark-scale replay/restart validation

## Week 6 Hardening Change

One real semantic drift was found and fixed in `src/event_driven_audio_analytics/shared/audio.py`.

- `Fact`: the previous shared PyAV decode path let FFmpeg downmix stereo to mono during resample.
- `Conflict`: that downmix was about `sqrt(2)` louder than the legacy pipeline, which explicitly averages channels before resample.
- `Fact`: the decoder now preserves the original channel layout during resample and then applies arithmetic-mean mono fold-down explicitly, restoring legacy-aligned amplitude semantics.

## Inputs Used

Committed fixture checks:

- `tests/fixtures/audio/valid_synthetic_stereo_44k1.mp3`

Local FMA-small reference checks:

- 1-track run: `track_id=2`
- 5-track run: `track_id in {2, 140, 148, 666, 1482}`

Observed legacy-aligned segment counts on the local reference pack:

- `2 -> 19`
- `140 -> 19`
- `148 -> 19`
- `666 -> 20`
- `1482 -> 19`

## What Was Compared

1. Decode/resample mono 32 kHz behavior.
2. Segment counts under 3.0 s windows with 1.5 s overlap.
3. RMS / energy behavior.
4. `silent_flag` behavior.
5. Exact log-mel shape `(1,128,300)`.
6. Summary-level log-mel parity signal using segment mean absolute error.
7. Welford mean/std behavior over mel-bin means.

## Results

| Item | Status | Observation |
| --- | --- | --- |
| Mono / 32 kHz decode-resample semantics | Verified after Week 6 fix | Committed stereo fixture now matches the legacy downmix+resample path within `atol=1e-3`. |
| Segment counts | Verified exactly | Current path matched legacy counts on all checked local FMA tracks: `19, 19, 19, 20, 19`. |
| Log-mel shape | Verified exactly | Every checked segment stayed `(1,128,300)`. |
| `silent_flag` | Verified exactly on checked data | `0` silent mismatches on the 1-track run and on the 5-track run. All checked reference tracks were non-silent in processing. |
| RMS behavior | Verified at tolerance level | Current segment RMS stays on the legacy formula and differs only after the claim-check PCM16 round-trip. |
| Log-mel values | Approximate but acceptable | Shape is exact; values show small drift after claim-check PCM16 round-trip. This is not a Kafka contract problem because `audio.features` is summary-first. |
| Welford update rule | Verified | Current vector-valued Welford math matches the legacy update rule on the current samples. |
| Welford persisted snapshots | Missing / deferred | The SQL table exists, but `processing` does not persist Welford snapshots yet. |

## Recorded Integration Runs

### 1 Track

Reference track set:

- `2`

Observed results:

- segments: `19`
- max RMS diff vs legacy segment reference: `0.002212 dB`
- average RMS diff: `0.001096 dB`
- max segment log-mel mean absolute error: `0.016179`
- average segment log-mel mean absolute error: `0.015528`
- `silent_flag` mismatches: `0`
- Welford mean MAE vs legacy mel-bin means: `0.015358`
- Welford std MAE vs legacy mel-bin std: `0.000164`

Representative observation:

- For one real FMA track, the current path is effectively aligned on segment count, RMS, silence behavior, and Welford summary behavior. Residual mel-value drift is small and consistent with the claim-check WAV round-trip, not with a contract drift.

### 5 Tracks

Reference track set:

- `2`
- `140`
- `148`
- `666`
- `1482`

Observed results:

- per-track segments: `{2: 19, 140: 19, 148: 19, 666: 20, 1482: 19}`
- total segments: `96`
- max RMS diff vs legacy segment reference: `0.007229 dB`
- average RMS diff: `0.003419 dB`
- max segment log-mel mean absolute error: `0.032885`
- average segment log-mel mean absolute error: `0.022825`
- `silent_flag` mismatches: `0`
- Welford mean MAE vs legacy mel-bin means: `0.017949`
- Welford std MAE vs legacy mel-bin std: `0.008775`

Representative observation:

- The current path remains stable across multiple real FMA tracks. Segment counts stay exact, silence behavior stays exact, and summary-level RMS/Welford behavior stays close enough for the current PoC monitoring goal.

## `audio.features` To `audio_features` Mapping

Direct payload-to-table mapping verified in Week 6:

| `audio.features` payload field | `audio_features` column | Status |
| --- | --- | --- |
| `ts` | `ts` | Direct |
| `run_id` | `run_id` | Direct |
| `track_id` | `track_id` | Direct |
| `segment_idx` | `segment_idx` | Direct |
| `artifact_uri` | `artifact_uri` | Direct |
| `checksum` | `checksum` | Direct |
| `manifest_uri` | `manifest_uri` | Direct, optional |
| `rms` | `rms` | Direct |
| `silent_flag` | `silent_flag` | Direct |
| `mel_bins` | `mel_bins` | Direct |
| `mel_frames` | `mel_frames` | Direct |
| `processing_ms` | `processing_ms` | Direct |

Fields emitted by processing that should not be persisted directly into `audio_features`:

- envelope lineage fields: `event_id`, `event_type`, `event_version`, `trace_id`, `produced_at`, `source_service`, `idempotency_key`
- processing-owned `system.metrics` rows such as `silent_ratio`, `processing_ms` event copies, and `feature_errors`
- in-memory-only processing state such as the full mel tensor and the current Welford state

Fields that a downstream consumer might want but are currently absent from the locked `audio_features` persistence path:

- `feature_uri`
- explicit channel dimension for the log-mel shape
- persisted Welford snapshot identity/value columns for processing-side statistical state

Current Week 6 judgment:

- None of those absences are a blocker for the current PoC summary-first database path.
- They are only future extension candidates and must not be added silently.

## Week 8 Bounded Downstream Confirmation

The Week 6 reference pass remains focused on audio/DSP semantics, but Week 8 now adds bounded downstream confirmation that the summary-first output survives the current end-to-end PoC path:

- `Fact`: The bounded processing-to-writer smoke evidence is green on the committed smoke fixtures, proving current-run `audio.features` persistence into `audio_features` plus `system_metrics` and `run_checkpoints`.
- `Fact`: The deterministic dashboard evidence path is green and proves the Grafana-facing SQL views can read real persisted summaries for the energetic, silent-oriented, and validation-failure runs.
- `Inference`: this confirms the current summary-first `audio.features -> audio_features -> dashboard views` path is coherent on the bounded PoC demo path, but it is still not a benchmark-scale parity result.

## Summary Fields Versus External Artifacts

Practical Week 6 storage boundary:

- Keep in DB summary: `ts`, `run_id`, `track_id`, `segment_idx`, `artifact_uri`, `checksum`, `manifest_uri`, `rms`, `silent_flag`, `mel_bins`, `mel_frames`, `processing_ms`
- Keep outside DB: full `(1,128,300)` mel tensors, any per-bin feature arrays, embeddings, model inputs, or larger derived tensors

Rationale:

- The PoC needs replay-safe, explainable summaries in `audio_features`.
- The PoC does not need to turn TimescaleDB or Kafka into tensor transport.
- Claim-check artifacts remain the right place for large derived outputs if they become necessary later.

## `feature_uri` Decision

Current Week 6 decision:

- `Fact`: `feature_uri` is absent from the locked v1 contract.
- `Fact`: `feature_uri` is absent from the shared payload model.
- `Fact`: `feature_uri` is absent from the current `audio_features` table.

Normalized behavior for the current repo:

- `audio.features` remains a summary-first event with no `feature_uri`.
- Optional full-feature storage is not part of the active v1 runtime path.

If optional full-feature artifacts are added later, the expected rule should be:

- `feature_uri` exists only when a concrete external feature artifact has actually been written under `/artifacts/runs/<run_id>/features/<track_id>/<segment_idx>.*`
- `feature_uri` is absent when no external feature artifact exists
- `feature_uri` must remain a pointer only, never a tensor-in-Kafka workaround

Because `feature_uri` is not in v1 today, adding it later requires A/B synchronization and a coordinated update across docs, schemas, shared models, SQL expectations, fixtures, and tests.

## Welford Snapshot Findings

Current state:

- `Fact`: `processing` maintains vector-valued in-memory Welford state over mel-bin means.
- `Fact`: Week 5/6 tests verify the update rule against manual expectations.
- `Fact`: Week 6 reference runs show the current Welford summaries stay close to the legacy-reference mel-bin statistics.

What is still incomplete:

- `Conflict`: `infra/sql/002_core_tables.sql` already defines `welford_snapshots`.
- `Conflict`: the current `processing` runtime does not write to that table.
- `Inference`: Welford snapshotting is therefore partially implemented at the semantic level and missing at the persistence/integration level.

Week 6 sufficiency judgment:

- Sufficient for current monitoring correctness validation: `Yes`
- Sufficient for restart-stable persisted Welford monitoring: `No`

## Verified / Partially Verified / Not Yet Verified

Verified:

- mono 32 kHz decoding behavior after the Week 6 fix
- exact segment counts on the checked local FMA tracks
- exact log-mel shape `(1,128,300)`
- exact `silent_flag` behavior on the checked runs
- direct `audio.features` payload to `audio_features` summary-field mapping
- summary-first absence of `feature_uri` in the current locked path
- Welford update-rule correctness

Partially verified:

- log-mel value parity, at summary/tolerance level only
- RMS parity, with small claim-check WAV round-trip drift
- Welford value parity against legacy mel-bin statistics, at monitoring tolerance level

Not yet verified:

- benchmark-scale live writer persistence of larger local-reference runs into TimescaleDB
- benchmark-scale dashboard behavior over larger local-reference runs
- persisted `welford_snapshots` behavior
- any benchmark-scale or restart/replay-hardening scenario beyond the current targeted checks

## Remaining A/B Synchronization Items

- Decide whether `feature_uri` should stay completely out of the contract or be introduced later in a coordinated contract version.
- Decide whether `welford_snapshots` should become a real persisted processing output and, if so, how vector-valued data should be stored and consumed.
- Decide whether any writer-side lineage fields beyond the current summary table are worth storing, because the current `audio_features` path intentionally keeps only summary payload fields.
