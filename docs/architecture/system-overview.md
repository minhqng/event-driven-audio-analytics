# System Overview

`event-driven-audio-analytics` is a bounded event-driven audio analytics PoC on FMA-small style inputs.

## Components

- `ingestion`: reads metadata/audio, validates tracks, writes segment WAV artifacts and manifests, publishes `audio.metadata`, `audio.segment.ready`, and run-level `system.metrics`.
- `processing`: consumes `audio.segment.ready`, loads claim-check artifacts, computes RMS/silence/log-mel summaries, publishes `audio.features` and processing metrics.
- `writer`: consumes persisted-truth events, writes TimescaleDB rows, stores replay-aware checkpoints, and emits writer metrics.
- `review`: read-only FastAPI surface over DB views and claim-check artifacts.
- `grafana`: file-provisioned dashboards over TimescaleDB as supporting evidence.

## Boundaries

- Kafka is small-event transport only.
- `artifacts/runs/<run_id>/` is the local claim-check runtime truth.
- TimescaleDB is the persisted summary and operational truth.
- The review service does not create or mutate business data.
- Grafana does not define semantics; it corroborates persisted rows.

## Event Contract

The active topics are:

- `audio.metadata`
- `audio.segment.ready`
- `audio.features`
- `system.metrics`
- `audio.dlq`

`audio.dlq` is reserved in topic/bootstrap constants but is not a fully modeled runtime path in this PoC.

## Evidence Model

Final generated evidence lives under `artifacts/evidence/final-demo/`:

- `review-dashboard/`: review API snapshot, review screenshot, Grafana API proof, dashboard screenshots, notes.
- `restart-replay/`: fail-fast preflight notes, baseline snapshot, replay summary.
- `evidence-index.md`: final handoff index.
