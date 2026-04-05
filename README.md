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
5. If you want a broker-backed Week 4 ingestion smoke run for the currently configured input selection, use `bash ./scripts/smoke/check-ingestion-flow.sh`.
   On Windows hosts, the equivalent is `powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-ingestion-flow.ps1`.
6. If you want a broker-backed Week 5 processing smoke run for the currently configured input selection, use `bash ./scripts/smoke/check-processing-flow.sh`.
   On Windows hosts, the equivalent is `powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-processing-flow.ps1`.
7. If you want a broker-backed Week 6 persistence smoke run from `ingestion` through `processing` into `writer` and TimescaleDB, use `bash ./scripts/smoke/check-processing-writer-flow.sh`.
   On Windows hosts, the equivalent is `powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-processing-writer-flow.ps1`.
8. If you want the full Week 7 dashboard evidence path, use `powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-week7-dashboard-evidence.ps1`.
9. If you want the official repo test path without relying on host-installed `pytest`, use `bash ./scripts/smoke/check-pytest.sh`.
   On Windows hosts, the equivalent is `powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1`.

## Runtime Notes

- All application code executes inside Linux containers; the host only orchestrates Docker Compose.
- Kafka is exposed on `localhost:9092` for host tools and `kafka:29092` for other containers.
- The default demo stack now auto-loads the provisioned TimescaleDB datasource and the `Audio Quality` / `System Health` dashboards from files.
- Service images now install per-service Python extras, so `ingestion` and `writer` smoke builds no longer resolve the `torch` / `torchaudio` layer that belongs to the processing DSP path.
- The `processing` and `pytest` images pin CPU-only PyTorch wheels during Docker builds, which avoids pulling CUDA packages into the PoC smoke/test path.
- `ingestion` now runs a bounded Week 4 replay path in Compose: it performs a startup preflight, reads configured sample metadata, writes claim-check artifacts plus the run manifest under `artifacts/`, publishes `audio.metadata`, `audio.segment.ready`, and run-level `system.metrics`, then exits cleanly.
- `processing` now runs as a long-lived Compose service: it performs a startup preflight, consumes `audio.segment.ready`, retries bounded artifact-readiness failures, publishes `audio.features`, and emits `processing_ms`, `silent_ratio`, plus terminal `feature_errors` metrics on `system.metrics`.
- `processing` also persists restart-recovery state under `/artifacts/runs/<run_id>/state/processing_metrics.json`, which keeps `silent_ratio` `run_total` snapshots stable across service restarts for the same logical run.
- When `processing` hits a terminal record failure, the container now stays stopped for inspection instead of auto-restarting into a poison-record replay loop while `audio.dlq` is still only reserved.
- `writer` now runs as a long-lived Compose service: it performs a startup preflight, consumes `audio.metadata`, `audio.features`, and `system.metrics`, persists them through a psycopg pool, updates checkpoints inside the same DB transaction, commits offsets only after DB success, and writes direct-to-DB internal metrics `write_ms`, `rows_upserted`, and best-effort `write_failures`.
- When `writer` hits a terminal record failure, the container likewise stays stopped for inspection instead of auto-restarting into a poison-record replay loop while `audio.dlq` is still only reserved.
- The default Compose smoke path uses committed synthetic fixtures under `tests/fixtures/audio/`, and the Python verifier derives its exact expectations from the active `METADATA_CSV_PATH`, `AUDIO_ROOT_PATH`, allowlist, and run id. Override `METADATA_CSV_PATH` and `AUDIO_ROOT_PATH` when running against a local FMA-small pack.
- The official `pytest` path now runs inside a dedicated Compose service against image-bundled repo contents, so the full suite no longer depends on host-installed Python tooling or bind-mounted workspace permissions.
- The shared `artifacts/` claim-check mount is configured for concurrent ingestion/processing access in Compose, which keeps the healthy Week 5 processing smoke path from tripping over artifact-read permissions.
- The bounded broker-backed path into TimescaleDB now feeds real Grafana dashboards through the file-provisioned Week 7 views and dashboard JSON.
- `docs/architecture/dashboard-interpretation.md` is the canonical explanation of what each panel proves.
