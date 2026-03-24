# event-driven-audio-analytics

`event-driven-audio-analytics` is a clean standalone PoC for event-driven real-time audio analytics on FMA-small.
It follows a claim-check architecture: Kafka moves small events, shared storage holds large artifacts, TimescaleDB stores analytical summaries and operational metrics, and Grafana is provisioned from files.

## Scope

- PoC only: Docker Compose, Kafka KRaft, TimescaleDB, Grafana, and three core services.
- No raw waveform payloads on Kafka.
- No Kubernetes, service mesh, or production-only abstractions.
- No train/validation/test split logic or Hugging Face publishing in the runtime scaffold.

## Repository Layout

- `src/event_driven_audio_analytics/`: one root Python package for ingestion, processing, writer, and shared code.
- `services/`: container/runtime wrappers for each service.
- `infra/`: Kafka bootstrap, TimescaleDB init SQL, and Grafana provisioning.
- `schemas/`: versioned event-contract placeholders.
- `docs/`: concise architecture, runbook, and source-material references.
- `artifacts/`: bind-mounted claim-check storage boundary.

## Core Topics

- `audio.metadata`
- `audio.segment.ready`
- `audio.features`
- `system.metrics`

## Quick Start

1. Copy `.env.example` to `.env`.
2. Review `docs/architecture/system-overview.md`.
3. Run `docker compose up --build -d`.
4. Run `./infra/kafka/create-topics.sh`.
5. Run `./run-demo.sh`.
