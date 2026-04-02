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
- `audio.dlq`

## Quick Start

1. Copy `.env.example` to `.env`.
2. Review `docs/architecture/system-overview.md`.
3. Start the scaffold with `bash ./run-demo.sh`.
4. If you only need Kafka topic bootstrap, run `sh ./infra/kafka/create-topics.sh`.

## Runtime Notes

- All application code executes inside Linux containers; the host only orchestrates Docker Compose.
- Kafka is exposed on `localhost:9092` for host tools and `kafka:29092` for other containers.
- The scaffold only validates local bootstrapping and contract shape; it does not claim end-to-end analytics execution yet.
- The `ingestion`, `processing`, and `writer` containers currently log their scaffold steps and exit cleanly; Week 1 success is infra wiring, not long-running service loops.
