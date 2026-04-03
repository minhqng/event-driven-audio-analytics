# Audio Fixtures

This directory contains the Week 1 Member B audio fixture setup.

## Purpose

- Provide a tiny, deterministic fixture pack for validation, decode/resample, segmentation, and silence-gate testing.
- Keep the repo free of redistributed raw FMA audio.
- Normalize a separate, non-committed FMA-small reference pack for local parity checks.

## Fixture Layers

1. Committed synthetic fixtures
2. External FMA-small reference pack

The committed synthetic fixtures are safe to version in this repo.
The external FMA pack is described in `fixture_manifest.json` but intentionally not committed.

## Committed Synthetic Fixtures

| File | Sample rate | Duration | Purpose | Expected behavior |
| --- | --- | --- | --- | --- |
| `valid_synthetic_stereo_44k1.mp3` | `44100 Hz`, stereo | `4.6 s` | Valid decode/resample/mono + segmentation smoke fixture | Passes old validation; sample-rate mismatch is non-blocking; old transform yields `3` segments and `(1,128,300)` mels |
| `silent_mono_32k.wav` | `32000 Hz`, mono | `3.0 s` | Deterministic silent input | Fails old validation as silent; RMS is `-inf` |
| `short_tone_mono_32k.wav` | `32000 Hz`, mono | `0.75 s` | Deterministic too-short input | Fails old validation because duration `< 1.0 s` |
| `corrupt_audio.mp3` | n/a | n/a | Deterministic corrupt file | Must fail decode/open |

## Compose Smoke Mirrors

- `smoke_tracks.csv` is a tiny 3-row-header metadata file for the Week 3 Compose smoke path and now includes `track.duration` so reject-path metadata events stay contract-valid.
- `fma_small/000/000002.mp3` mirrors the valid synthetic fixture under canonical FMA naming.
- `fma_small/000/000666.mp3` mirrors the corrupt fixture under canonical FMA naming.
- These are still synthetic or intentionally corrupt repo fixtures, not redistributed FMA audio.

## External FMA-small Reference Pack

Use the one-track-per-genre pack listed in `fixture_manifest.json` for local parity checks.

- It is reference-only and not committed here.
- Canonical path rule remains `data/raw/fma_small/<folder>/<track_id>.mp3`.
- The recommended Week 1 pack is intentionally small: 8 tracks, one per top-level FMA-small genre.

## Naming Convention

- Synthetic committed fixtures use descriptive names with format hints:
  - `valid_*`
  - `silent_*`
  - `short_*`
  - `corrupt_*`
- External FMA references are identified by stable `track_id` and canonical FMA relative path, not by copied binaries.

## Regeneration Notes

The committed fixtures were generated deterministically with `ffmpeg`.

### Valid synthetic MP3

```powershell
ffmpeg -y `
  -f lavfi -i "sine=frequency=440:duration=4.6:sample_rate=44100" `
  -f lavfi -i "sine=frequency=660:duration=4.6:sample_rate=44100" `
  -filter_complex "[0:a][1:a]amerge=inputs=2[aout]" `
  -map "[aout]" `
  -c:a libmp3lame -q:a 6 `
  tests\fixtures\audio\valid_synthetic_stereo_44k1.mp3
```

### Silent WAV

```powershell
ffmpeg -y `
  -f lavfi -i "anullsrc=r=32000:cl=mono" `
  -t 3.0 `
  -c:a pcm_s16le `
  tests\fixtures\audio\silent_mono_32k.wav
```

### Short WAV

```powershell
ffmpeg -y `
  -f lavfi -i "sine=frequency=880:duration=0.75:sample_rate=32000" `
  -ac 1 `
  -c:a pcm_s16le `
  tests\fixtures\audio\short_tone_mono_32k.wav
```

### Corrupt File

```powershell
Set-Content -LiteralPath tests\fixtures\audio\corrupt_audio.mp3 -Value 'not an audio stream' -NoNewline
```

## Missing Or Non-Committed Fixtures

- Actual FMA-derived audio binaries are intentionally absent from this repo.
- If a future thread needs a committed real-audio fixture, that decision should be reviewed against the repo's current no-redistribution posture first.
