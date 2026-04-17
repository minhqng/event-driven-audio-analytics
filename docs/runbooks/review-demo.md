# Review Demo Runbook

## Purpose

This is the primary live-demo surface for the current PoC. It shows:

- recent runs as first-class review objects
- track-level outcomes, including metadata-only reject paths
- segment-level persisted summaries with claim-check audio playback
- secondary runtime proof from checkpoints and filesystem state

Use this surface first. Treat Grafana as corroborating operational evidence, not as the main narrative.

## Expected Service

After `bash ./run-demo.sh` or `bash ./scripts/demo/generate-dashboard-evidence.sh`, the review console is reachable at:

- [http://localhost:8080](http://localhost:8080)

For the deterministic demo pack, use demo mode:

- [http://localhost:8080/?demo=1](http://localhost:8080/?demo=1)

## Recommended Live Sequence

1. Open `http://localhost:8080/?demo=1`.
2. Start with `week7-high-energy` to show a clean persisted run.
3. Open the single track and play one segment artifact to prove the claim-check path is tangible.
4. Switch to `week7-silent-oriented` and highlight the silent segment row plus the non-zero silent ratio.
5. Switch to `week7-validation-failure` and show the metadata-only state with `validation_status=silent` and zero persisted segments.
6. Open the runtime-proof section only if you need to answer questions about checkpoints, manifest presence, or replay-stable processing state.
7. Move to Grafana only after the run/track/segment story is already clear.

## What The Review Surface Proves

- The PoC produces inspectable run results, not just background logs.
- Reject paths remain explicit metadata outcomes instead of disappearing.
- Persisted segment summaries and audio artifacts remain correlated by `run_id`, `track_id`, and `segment_idx`.
- The visualization layer is read-only and non-authoritative: it reads current DB views plus `artifacts/`, but it does not define new semantics.
