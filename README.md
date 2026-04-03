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
5. If you want a broker-backed Week 4 ingestion smoke run, use `bash ./scripts/smoke/check-ingestion-flow.sh`.
   On Windows hosts, the equivalent is `powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-ingestion-flow.ps1`.

## Runtime Notes

- All application code executes inside Linux containers; the host only orchestrates Docker Compose.
- Kafka is exposed on `localhost:9092` for host tools and `kafka:29092` for other containers.
- The scaffold only validates local bootstrapping and contract shape; it does not claim end-to-end analytics execution yet.
- `ingestion` now runs a bounded Week 4 replay path in Compose: it performs a startup preflight, reads configured sample metadata, writes claim-check artifacts plus the run manifest under `artifacts/`, publishes `audio.metadata`, `audio.segment.ready`, and run-level `system.metrics`, then exits cleanly.
- The default Compose smoke path uses committed synthetic fixtures under `tests/fixtures/audio/`; override `METADATA_CSV_PATH` and `AUDIO_ROOT_PATH` when running against a local FMA-small pack.
- `processing` remains placeholder, and full end-to-end analytics through `writer` and dashboards still needs later phases.
