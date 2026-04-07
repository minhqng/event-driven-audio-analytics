# event-driven-audio-analytics

`event-driven-audio-analytics` is an academic proof of concept for event-driven real-time audio analytics on FMA-small. It demonstrates a claim-check architecture end to end: Kafka carries small events, shared storage carries audio artifacts, TimescaleDB stores summaries and operational metrics, and Grafana presents the resulting observability story from file-provisioned dashboards.

## What This Repository Demonstrates

- Event-driven decoupling across `ingestion`, `processing`, and `writer`
- Claim-check handling for audio segments and run manifests under `artifacts/`
- At-least-once delivery with checkpoint-aware, idempotent persistence
- Bounded restart/replay verification for the same `run_id`
- Dashboard-backed observability over real persisted PoC data

## Scope

- In scope: Docker Compose, Kafka KRaft, shared-volume claim-check storage, TimescaleDB, Grafana, metadata ETL, mono 32 kHz normalization, 3.0 s segments with 1.5 s overlap, RMS, silence gating, log-mel summary shape, Welford-style monitoring output, and bounded demo/evidence flows
- Out of scope: Kubernetes, service mesh, HA/DR, multi-node Kafka, production object storage/IAM, model serving, full MLOps, and benchmark-scale claims beyond the documented bounded runs
- Kafka remains small-event transport only. Raw waveform payloads and large tensors do not belong on the broker.

## Recommended Reader Path

1. Read `docs/README.md`.
2. Read `docs/architecture/system-overview.md`.
3. Run the final demo/evidence path from `docs/runbooks/demo.md`.
4. Use `docs/runbooks/validation.md` when you need targeted smoke checks or the official containerized `pytest` path.
5. Use `correctness-against-reference.md` and `docs/architecture/dashboard-interpretation.md` for the technical justification behind the demo outputs.

## Recommended Commands

Final demo and evidence bundle:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-demo-evidence.ps1
```

```sh
bash ./scripts/demo/generate-demo-evidence.sh
```

Dashboard-only evidence:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-dashboard-evidence.ps1
```

```sh
bash ./scripts/demo/generate-dashboard-evidence.sh
```

Bootstrap the stack without running demo inputs:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-demo.ps1
```

```sh
bash ./run-demo.sh
```

Official repo test path:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1
```

```sh
bash ./scripts/smoke/check-pytest.sh
```

## Repository Layout

- `src/event_driven_audio_analytics/`: repo-owned Python package for ingestion, processing, writer, and shared logic
- `services/`: per-service container wrappers
- `infra/`: Kafka topic bootstrap, TimescaleDB SQL, and Grafana provisioning
- `schemas/`: JSON schemas aligned to the locked event contract v1
- `docs/`: runbooks, architecture notes, archive material, and reader guidance
- `tests/`: contract, unit, integration, smoke-verifier, and fixture coverage
- `artifacts/`: shared claim-check boundary and demo evidence output root

## Core Topics

- `audio.metadata`
- `audio.segment.ready`
- `audio.features`
- `system.metrics`
- `audio.dlq`

`audio.dlq` is reserved in bootstrap/constants but is not yet a fully modeled or exercised runtime path in this PoC.

## Runtime Notes

- All application code runs inside Linux containers; the host only orchestrates Docker Compose.
- Kafka is exposed on `localhost:9092` for host tools and `kafka:29092` for other containers.
- The default stack auto-loads the provisioned `Audio Quality` and `System Health` dashboards from files.
- `processing` and `writer` are long-lived consumers with graceful shutdown handling for bounded restart/replay checks.
- The official `pytest` path runs in a dedicated Compose service against image-bundled repo contents.
- Historical evidence directories under `artifacts/demo/week7/` and `artifacts/demo/week8/` are intentionally retained because they are the stable demo packs referenced throughout the repo.
