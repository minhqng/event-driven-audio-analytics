# event-driven-audio-analytics

`event-driven-audio-analytics` is an academic proof of concept for event-driven real-time audio analytics on FMA-small. It demonstrates a claim-check architecture end to end: Kafka carries small events, local or MinIO-backed claim-check storage carries audio artifacts, TimescaleDB stores summaries and operational metrics, a read-only review console presents run/track/segment outcomes, Grafana provides the supporting observability story from file-provisioned dashboards, and the dataset-exporter materializes final FMA-Small analytics/dataset bundles from persisted truth.

## What This Repository Demonstrates

- Event-driven decoupling across `ingestion`, `processing`, and `writer`
- Claim-check handling for audio segments and run manifests under logical `/artifacts/...` or `s3://<bucket>/...`
- At-least-once delivery with checkpoint-aware, idempotent persistence
- A read-only review surface over persisted run, track, and segment outcomes
- Deterministic dataset/analytics bundle generation from completed persisted runs
- Bounded restart/replay verification for the same `run_id`
- Dashboard-backed observability over real persisted PoC data

## Scope

- In scope: Docker Compose, Kafka KRaft, local and MinIO/S3-compatible claim-check storage, TimescaleDB, Grafana, metadata ETL, mono 32 kHz normalization, 3.0 s segments with 1.5 s overlap, RMS, silence gating, log-mel summary shape, Welford-style monitoring output, and bounded demo/evidence flows
- Out of scope: Kubernetes, service mesh, HA/DR, multi-node Kafka, production object storage/IAM, model serving, full MLOps, and benchmark-scale claims beyond the documented bounded runs
- Kafka remains small-event transport only. Raw waveform payloads and large tensors do not belong on the broker.

## Recommended Reader Path

1. Read `docs/README.md`.
2. Read `docs/architecture/system-overview.md`.
3. Run the final demo/evidence path from `docs/runbooks/demo.md`.
4. Use `docs/runbooks/validation.md` for smoke checks and the official containerized `pytest` path.
5. Use `artifacts/README.md` and `data/README.md` for generated output and local dataset boundaries.

## Recommended Commands

Final demo and evidence bundle:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-demo-evidence.ps1
```

```sh
bash ./scripts/demo/generate-demo-evidence.sh
```

This is the front-door productization path: it produces review console evidence, Grafana corroboration, restart/replay proof, and the final deterministic FMA-Small dataset bundles under `artifacts/datasets/`. Read the review outputs first, use Grafana as supporting corroboration, and treat the dataset bundles as the productized output layer from persisted truth.

Review/dashboard evidence:

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

Optional MinIO claim-check smoke and evidence path:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-minio-claim-check-flow.ps1
```

```sh
bash ./scripts/smoke/check-minio-claim-check-flow.sh
```

This path keeps the default deterministic demo on `STORAGE_BACKEND=local`, then exercises the bounded MinIO variant separately. Canonical storage env vars live in `.env.example`, and the full manual/acceptance steps are in `docs/runbooks/validation.md`.

When `MINIO_ENDPOINT_URL` is left unset, the services derive `http://minio:9000`
or `https://minio:9000` from `MINIO_SECURE`. If a local processing deployment
must also fail fast on historical `s3://...` replay readiness, set
`PROCESSING_PROBE_S3_REPLAY_READINESS=true`.

Bounded FMA-Small evaluation evidence:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\evaluation\run-evaluation.ps1
```

```sh
bash ./scripts/evaluation/run-evaluation.sh
```

This writes latency, throughput, resource usage, scaling, and markdown report
artifacts under `artifacts/evidence/final-demo/evaluation/`. Treat these as
bounded local measurements, not benchmark-scale performance claims.

Bounded local FMA-small burst after placing the dataset under `data/local/`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\run-local-fma-burst.ps1
```

```sh
bash ./scripts/demo/run-local-fma-burst.sh
```

## Repository Layout

- `src/event_driven_audio_analytics/`: repo-owned Python package for ingestion, processing, writer, and shared logic
- `services/`: per-service container wrappers
- `infra/`: Kafka topic bootstrap, TimescaleDB SQL, and Grafana provisioning
- `schemas/`: JSON schemas aligned to the locked event contract v1
- `docs/`: compact final runbooks, architecture notes, and reader guidance
- `tests/`: contract, unit, integration, smoke-verifier, and fixture coverage
- `data/`: local-only dataset mount point; `data/local/` is ignored and excluded from Docker build context
- `artifacts/`: generated claim-check boundary and demo evidence output root

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
- The default stack also exposes the read-only `review` service at `http://localhost:8080`.
- `processing` and `writer` are long-lived consumers with graceful shutdown handling for bounded restart/replay checks.
- The official `pytest` path runs in a dedicated Compose service against image-bundled repo contents.
- Generated evidence lives under `artifacts/evidence/`, with final demo output under `artifacts/evidence/final-demo/`.
- Full FMA-small data is a local runtime input under `data/local/`, not a tracked test fixture.
