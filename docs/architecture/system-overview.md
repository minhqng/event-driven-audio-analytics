# System Overview

`event-driven-audio-analytics` implements a bounded FMA-Small research system for the topic:

> Nghiên cứu kiến trúc Event-Driven Microservices và Xây dựng hệ thống phân tích dữ liệu lớn âm thanh thời gian thực trên nền tảng Private Cloud

The system demonstrates a near-real-time event-driven microservices architecture, not a generic audio platform and not a production HA deployment. The dataset scope is strictly FMA-Small.

## Architecture Narrative

The pipeline keeps large audio artifacts out of Kafka. Services exchange small events through Kafka topics, while waveform segments and run manifests move through claim-check storage. The local backend supports deterministic development and demo runs; the MinIO/S3-compatible backend demonstrates the bounded private-cloud object-storage variant.

TimescaleDB is the persisted analytics truth. The review console reads that truth first and serves read-only run, track, segment, and media inspection. Grafana uses the same TimescaleDB rows as corroborating observability, not as the front door. The dataset exporter turns persisted truth and claim-check references into reusable FMA-Small analytics/dataset bundles.

## Components

- `ingestion`: reads FMA-Small metadata/audio, validates tracks, writes segment WAV artifacts and manifests, publishes `audio.metadata`, `audio.segment.ready`, and run-level `system.metrics`.
- `processing`: consumes `audio.segment.ready`, loads claim-check artifacts, verifies checksums, computes RMS/silence/log-mel shape summaries, publishes `audio.features` and processing metrics.
- `writer`: consumes persisted-truth events, writes TimescaleDB rows, stores replay-aware checkpoints, and emits writer metrics.
- `review`: read-only inspection surface over DB views and claim-check artifacts.
- `dataset-exporter`: exports run summaries, accepted/rejected records, split manifests, Parquet reference tables, normalization stats, and dataset cards from persisted truth.
- `grafana`: file-provisioned dashboards over TimescaleDB for corroborating observability.
- `minio`: optional S3-compatible claim-check backend for private-cloud-style artifact storage.

## Boundaries

- Kafka is small-event transport only; raw audio and tensors are not broker payloads.
- Audio artifacts use claim-check URIs under `/artifacts/runs/...` or `s3://<bucket>/runs/...`.
- TimescaleDB is the source of persisted analytics truth for review, Grafana, and dataset export.
- The review console and Grafana are read-only surfaces.
- Dataset bundles contain references, metadata, labels, and scalar summaries; they do not contain log-mel tensors because tensors are not persisted.

## Deployment And Evidence

Docker Compose remains the default local/dev path. The K3s/Kubernetes manifests provide a bounded single-node private-cloud mapping with Kafka, TimescaleDB, MinIO, Grafana, processing, writer, review, ingestion Jobs, and dataset-exporter Jobs.

Final generated evidence lives under `artifacts/evidence/final-demo/`:

- `review-dashboard/`: review API snapshot, review screenshot, Grafana API proof, dashboard screenshots, notes.
- `dataset-exports/`: machine-readable verification of deterministic dataset bundles.
- `restart-replay/`: fail-fast preflight notes, baseline snapshot, replay summary.
- `evaluation/`: latency, throughput, resource usage, scaling, and report artifacts.
- `evidence-index.md`: final handoff index.

Final dataset bundles live under `artifacts/datasets/<run_id>/`.

## Limits

- No training or model serving.
- No new datasets beyond FMA-Small.
- No production HA, service mesh, GitOps, Terraform, or multi-node Kafka claim.
- No benchmark-scale performance claim; evaluation evidence is bounded local/private-cloud research evidence.
- `audio.dlq` is reserved in topic/bootstrap constants but is not a fully modeled runtime path in this bounded system.
