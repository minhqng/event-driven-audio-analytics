# REUSE_MAP.md

## Scope And Purpose

- `Fact`: This document is the Week 1 Member B handoff for reusing the old audio/data pipeline inside the event-driven PoC.
- `Fact`: Scope is limited to Member B responsibilities: metadata ETL, audio validation, PyAV decode/resample, segmentation, RMS, silence gate, log-mel, Welford, fixtures, and correctness expectations.
- `Fact`: This document does not change DB schema, writer persistence, Kafka topic design, checkpoint semantics, Grafana provisioning, or Compose architecture.
- `Inference`: The goal is to prevent semantic drift while the new `ingestion` and `processing` services are still placeholders.

## Source Documents Reviewed

- Root project guidance in this repo:
  - `AGENTS.md`
  - `PROJECT_CONTEXT.md`
  - `ARCHITECTURE_CONTRACTS.md`
  - `IMPLEMENTATION_STATUS.md`
  - `TASK_BOARD.md`
- Old pipeline materials reviewed from the sibling repo `../fma-small-audio-pipeline/`:
  - `README.md`
  - `configs/config.yaml`
  - `main.py`
  - `src/ingestion/metadata.py`
  - `src/ingestion/verify.py`
  - `src/ingestion/dataset_builder.py`
  - `src/features/audio_transforms.py`
  - `src/utils/helpers.py`
  - `tests/test_pipeline.py`
- Reference-only local data used to normalize a Week 1 FMA-small sample strategy:
  - `../music_genre_classification/data/raw/fma_metadata/tracks.csv`
  - `../music_genre_classification/data/raw/fma_small/`
- `Inference`: The sibling `fma-small-audio-pipeline` repo is the audio/DSP source of truth. The `music_genre_classification` tree was used only to observe real local FMA files, not to redefine semantics.

## Old Pipeline Summary

- `Fact`: The old pipeline is FMA-small-specific and code-first, not notebook-first.
- `Fact`: Its stable stages are: metadata parse -> audio validation -> decode/resample -> segmentation -> log-mel extraction -> segment silence filtering -> artist-aware split -> streaming normalization stats.
- `Fact`: The old pipeline explicitly fixes the following semantics:
  - `subset=small`
  - mono / 32 kHz normalization
  - 3.0-second segments
  - 1.5-second overlap
  - log-mel target shape `(1,128,300)`
  - silence handling at file-validation time and at segment time
  - Welford-style streaming statistics
- `Inference`: The new PoC should inherit stages through feature extraction and Welford math, but not the Arrow/Hugging Face publication workflow.

## Week 1 FMA-small Sample Strategy

- `Fact`: Week 1 should use two fixture layers:
  - commit-safe deterministic fixtures under `tests/fixtures/audio/` for unit and smoke checks
  - a non-committed external FMA-small reference pack for local parity checks
- `Fact`: The committed deterministic fixture set now contains:
  - `valid_synthetic_stereo_44k1.mp3`
  - `silent_mono_32k.wav`
  - `short_tone_mono_32k.wav`
  - `corrupt_audio.mp3`
- `Fact`: The external FMA-small reference pack should stay one track per genre for Week 1, not a benchmark-sized run.
- `Fact`: Local reference candidates recovered from `tracks.csv` plus available local audio are:

| Genre | Track ID | Artist ID | Canonical FMA path | Observed legacy segment count |
| --- | --- | --- | --- | --- |
| Electronic | `1482` | `249` | `001/001482.mp3` | `19` |
| Experimental | `148` | `57` | `000/000148.mp3` | `19` |
| Folk | `140` | `54` | `000/000140.mp3` | `19` |
| Hip-Hop | `2` | `1` | `000/000002.mp3` | `19` |
| Instrumental | `10250` | `42` | `010/010250.mp3` | `19` |
| International | `666` | `135` | `000/000666.mp3` | `20` |
| Pop | `10` | `6` | `000/000010.mp3` | `19` |
| Rock | `182` | `64` | `000/000182.mp3` | `20` |

- `Inference`: The 8-track one-per-genre pack is enough for Week 1 parity and fixture normalization; the 100-track dry run belongs to a later benchmark/demo phase.
- `Conflict`: Raw FMA audio is not committed in this repo, and existing repo/docs already avoid redistributing FMA audio. The reference pack therefore remains manifest-only.

## Reuse as-is

- `Fact`: `src/ingestion/metadata.py::_build_flattened_headers` is the recoverable source of truth for the 3-row `tracks.csv` header flattening logic.
- `Fact`: `src/ingestion/metadata.py::parse_fma_tracks` is the recoverable source of truth for selecting `track_id`, `track.genre_top`, `artist.id`, and `set.subset`, then filtering `subset=small` before any label-map work.
- `Fact`: `src/ingestion/metadata.py::resolve_audio_path` is the recoverable source of truth for the FMA file-path convention `000/000002.mp3`.
- `Fact`: `src/features/audio_transforms.py::_load_audio_pyav` is the recoverable source of truth for FFmpeg/PyAV decoding.
- `Fact`: `src/features/audio_transforms.py::AudioTransform.load_and_resample` is the recoverable source of truth for mono conversion plus resampling to 32 kHz.
- `Fact`: `src/features/audio_transforms.py::AudioTransform.extract_segments` is the recoverable source of truth for 3.0-second windows, 1.5-second hop, and final-tail padding only when the remaining tail exceeds 1.0 second.
- `Fact`: `src/features/audio_transforms.py::AudioTransform.to_mel_spectrogram` is the recoverable source of truth for the mel parameter set and exact `(1,128,300)` output shape.
- `Inference`: These functions should be lifted into a shared audio module inside this repo with semantic parity, not re-sketched from the placeholders.

## Reuse with adapter/refactor

- `Fact`: `src/ingestion/metadata.py::build_metadata` mixes stable metadata semantics with old-pipeline-specific label creation and file filtering; it needs refactoring into the new `MetadataRecord` and `audio.metadata` event flow.
- `Fact`: `src/ingestion/metadata.py::validate_audio_files` preserves the validation policy, but it currently filters rows instead of returning structured validation reasons required by the new service boundary.
- `Fact`: `src/ingestion/metadata.py::_compute_rms_db` is the old full-track RMS reference, but the new PoC also needs segment-level RMS in `processing`.
- `Fact`: `src/features/audio_transforms.py::AudioTransform.process_track` bundles steps that now belong in different services.
- `Fact`: `src/ingestion/dataset_builder.py::_is_silent_segment` is the old segment gate, but the new PoC should emit `silent_flag` or metrics rather than silently dropping segments with no trace.
- `Fact`: `src/utils/helpers.py::compute_global_stats` contains the reusable Welford update math, but the old implementation is training-split/Hugging-Face-centric and must be adapted to run-level monitoring outputs.
- `Inference`: The safe pattern is a shared module refactor that isolates reusable math/IO from old orchestration concerns.

## Defer / out-of-scope

- `Fact`: `src/ingestion/dataset_builder.py::build_arrow_dataset` is not part of the runtime PoC path.
- `Fact`: `src/ingestion/dataset_builder.py::push_to_hub` is out of scope for the new PoC runtime.
- `Fact`: `src/ingestion/dataset_builder.py::split_dataset` is artist-aware and useful as a correctness/reference asset, but it is not a runtime service requirement.
- `Fact`: `main.py` is the old end-to-end orchestrator for a training-data pipeline, not the runtime shape of the new event-driven services.
- `Fact`: notebook/demo assets from the old repo remain reference material only.
- `Inference`: Artist-aware split should stay available for academic explanation and future parity checks, but it must not be forced into the new runtime path unless the project scope changes.

## Mapping Table

- `Fact`: Because the old pipeline lives in a separate sibling repo and is not an installable dependency of this PoC, `direct import` is not the recommended Week 1 path.
- `Inference`: `shared-module refactor` is the default recommendation.
- `Fact`: `rewrite-not-allowed` means the placeholder must inherit the old semantics rather than be casually reimplemented from scratch.

| old module/function | old responsibility | target service in new PoC | recommended integration mode | notes / risks |
| --- | --- | --- | --- | --- |
| `src/ingestion/metadata.py::_build_flattened_headers` | Flatten 3-row FMA `tracks.csv` headers | `ingestion` | `rewrite-not-allowed` | Current `metadata_loader.py` placeholder does not preserve the old header logic. |
| `src/ingestion/metadata.py::parse_fma_tracks` | Parse metadata, select stable columns, filter `subset=small`, drop empty genres | `ingestion` | `rewrite-not-allowed` | Subset filtering must happen before label-map or genre assertions. |
| `src/ingestion/metadata.py::build_label_map` | Create stable sorted genre-to-int map | `ingestion` | `shared-module refactor` | New runtime may not persist integer labels, but tests/reference comparisons still need this helper. |
| `src/ingestion/metadata.py::resolve_audio_path` | Recover canonical FMA path `folder/file.mp3` from `track_id` | `ingestion` | `rewrite-not-allowed` | Needed for metadata ETL and fixture acquisition docs. |
| `src/ingestion/metadata.py::_compute_rms_db` | Compute RMS dB from decoded audio | `ingestion` and `processing` | `shared-module refactor` | Old code is full-track validation oriented; processing needs the same math adapted to segments. |
| `src/ingestion/metadata.py::validate_audio_files` | Fail-fast existence/decode/min-duration/silence validation | `ingestion` | `shared-module refactor` | Preserve thresholds and non-blocking SR mismatch behavior, but add structured reasons/checksum support. |
| `src/features/audio_transforms.py::_load_audio_pyav` | Decode audio via PyAV/FFmpeg | `shared (ingestion + processing)` | `rewrite-not-allowed` | Current repo does not yet declare `av`; dependency sync is a future blocker. |
| `src/features/audio_transforms.py::AudioTransform.load_and_resample` | Mono conversion and resample to 32 kHz | `shared (ingestion + processing)` | `rewrite-not-allowed` | Preserve mono averaging before resample. |
| `src/features/audio_transforms.py::AudioTransform.extract_segments` | 3.0-second segmentation with 1.5-second overlap and tail-padding rule | `ingestion` | `rewrite-not-allowed` | This is one of the most critical inheritance points; current `segmenter.py` is empty. |
| `src/features/audio_transforms.py::AudioTransform.to_mel_spectrogram` | Build `(1,128,300)` log-mel with exact transform config | `processing` | `rewrite-not-allowed` | Preserve `n_fft=1024`, `hop_length=320`, `n_mels=128`, `mel_scale='slaney'`, `norm='slaney'`, `log_epsilon=1e-9`. |
| `src/features/audio_transforms.py::AudioTransform.process_track` | Bundle decode -> resample -> segment -> mel for one track | `ingestion` and `processing` | `shared-module refactor` | New PoC splits this flow across claim-check artifact writing and later feature extraction. |
| `src/ingestion/dataset_builder.py::_is_silent_segment` | Segment-level silence gate on post-log mel tensors | `processing` | `shared-module refactor` | Old pipeline drops silent segments; new PoC likely needs explicit `silent_flag` and metrics. |
| `src/utils/helpers.py::compute_global_stats` | Streaming Welford mean/std over mel bins | `processing` | `shared-module refactor` | Current repo only has scalar placeholder Welford state; old behavior is vector-valued and training-oriented. |

## Do Not Rewrite Casually

- `Fact`: Do not replace the FMA `tracks.csv` flattening logic with ad hoc column-index assumptions.
- `Fact`: Do not move `subset=small` filtering to a later step; the old pipeline filters before label-map creation and downstream expectations depend on that.
- `Fact`: Do not change the FMA path rule `track_id -> folder/file.mp3`.
- `Fact`: Do not swap out PyAV decode/resample semantics with unrelated loaders without an explicit parity check.
- `Fact`: Do not change the normalization target away from mono / 32 kHz.
- `Fact`: Do not change segmentation away from 3.0 s windows, 1.5 s overlap, `segment_samples=96000`, `hop_samples=48000`, and the `remaining_tail > 1.0 s` padding rule.
- `Fact`: Do not change the log-mel parameter set or relax the exact `(1,128,300)` output requirement.
- `Fact`: Do not casually replace the old silence policy:
  - file-level validation threshold: `-60.0 dB`
  - segment-level gate floor: post-log mel std `< 1e-7`
- `Fact`: Do not treat the current scalar `processing/modules/welford.py` placeholder as the source of truth; the old pipeline computes vector-valued running statistics over mel bins.
- `Inference`: If a future implementation needs a structural refactor, it should move old code into a shared module first and change behavior only behind parity tests.

## Correctness Expectations And Tolerances

- `Fact`: Old config values recovered from `configs/config.yaml` are:
  - `sample_rate=32000`
  - `n_mels=128`
  - `n_fft=1024`
  - `hop_length=320`
  - `duration=3`
  - `segment_overlap=1.5`
  - `target_frames=300`
  - `log_epsilon=1e-9`
  - `min_duration_s=1.0`
  - `silence_threshold_db=-60.0`
- `Fact`: Local verification against the old pipeline and a real FMA mirror showed `subset=small` resolves to `8000` tracks and `8` top-level genres.
- `Fact`: Local verification through the old `AudioTransform` showed:
  - FMA track `000002.mp3` decodes to mono `32 kHz` and yields `19` segments
  - FMA track `000666.mp3` yields `20` segments because its duration is slightly above `30.0 s`
- `Fact`: Local verification through the committed synthetic fixtures showed:
  - `valid_synthetic_stereo_44k1.mp3` passes old validation despite a sample-rate mismatch, decodes to `(1, 147200)`, and yields `3` segments plus `(1,128,300)` mels
  - `silent_mono_32k.wav` yields `-inf` RMS and fails validation as silent
  - `short_tone_mono_32k.wav` fails validation because duration `< 1.0 s`
  - `corrupt_audio.mp3` is undecodable by design
- `Inference`: Acceptable Week 1 parity checks are:
  - exact metadata column selection and subset filtering behavior
  - exact segment counts for reference tracks/fixtures
  - exact mel output shape
  - identical validation pass/fail decisions on the committed synthetic fixtures
- `Unknown`: No numeric tolerance for per-bin mel values was documented in the old repo. Until Member B writes comparison tests, value-level parity should be treated as strict-by-configuration but unquantified.
- `Conflict`: Old Welford output is dataset-training-oriented, while the new PoC wants monitoring output. The update rule is reusable; the final emitted state shape is not yet locked.

## Unresolved Questions / Conflicts

- `Conflict`: Current repo placeholders are materially smaller than the old audio pipeline:
  - `metadata_loader.py` has no flattened-header parser
  - `audio_validator.py` has no PyAV/duration/silence logic
  - `segmenter.py` has no segmentation implementation
  - `log_mel.py` only returns a shape tuple
  - `welford.py` only tracks one scalar
- `Conflict`: Current repo `pyproject.toml` does not yet declare `av`, `polars`, `torch`, or `torchaudio`, which are required to reuse the old audio semantics directly.
- `Conflict`: The old pipeline silently filters invalid or silent rows/segments, while the new PoC likely needs explicit validation status and `silent_flag` fields for observability.
- `Conflict`: Raw FMA audio should not be casually committed into this repo; the Week 1 FMA reference pack therefore remains manifest-only.
- `Unknown`: Final checksum algorithm for claim-check segment artifacts is not fixed in the audio code yet.
- `Unknown`: Final artifact format for stored segments remains `.wav` versus `.npy`.
- `Unknown`: Final Welford payload/state representation for `system.metrics` or feature-side references still needs A/B synchronization because it touches contracts and persistence.
- `Fact`: Any change to event envelopes, payload fields, checkpoint behavior, topic design, or writer expectations still requires Member A/B synchronization.

## Recommended Implementation Order For Member B After Week 1

1. Extract the old metadata parser, PyAV loader, resample path, segmentation logic, mel transform, and silence helpers into a new shared audio module inside this repo.
2. Add the missing audio/data dependencies required for that shared module and wire tests to the committed synthetic fixtures.
3. Replace `ingestion/modules/metadata_loader.py` and `ingestion/modules/audio_validator.py` placeholders with legacy-parity implementations that return structured status instead of silent filtering alone.
4. Replace `ingestion/modules/segmenter.py` with the inherited 3.0 s / 1.5 s segmentation logic, then adapt it to claim-check artifact writing without changing semantics.
5. Replace `processing/modules/rms.py`, `processing/modules/silence_gate.py`, and `processing/modules/log_mel.py` with legacy-parity implementations over loaded segment artifacts.
6. Replace the scalar `processing/modules/welford.py` placeholder with vector-aware online statistics derived from the old update rule.
7. Only after those pieces are in place, add parity-style unit tests and a small local FMA smoke path.
