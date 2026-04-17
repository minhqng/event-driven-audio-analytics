# System Overview

## Purpose

This repository implements a bounded event-driven audio analytics PoC for FMA-small. It is designed for Docker Compose in a private-cloud-like local environment and is intentionally honest about PoC limits rather than production completeness.

## Core Boundary

- Kafka transports small events only.
- Shared storage under `artifacts/` holds claim-check artifacts and manifests.
- TimescaleDB stores analytical summaries and operational metrics.
- Grafana reads from TimescaleDB and is provisioned entirely from files.
- The read-only `review` service also reads from TimescaleDB plus `artifacts/` and presents run, track, and segment inspection.

## Services

- `ingestion`: loads metadata, validates audio, decodes and resamples to mono 32 kHz, plans segments, writes claim-check artifacts, and publishes `audio.metadata` plus `audio.segment.ready`
- `processing`: consumes `audio.segment.ready`, validates claim-check artifacts, computes RMS, silence decisions, log-mel summaries, Welford-style monitoring output, and publishes `audio.features` plus `system.metrics`
- `writer`: consumes metadata, features, and metrics events; persists them transactionally; updates checkpoints; and commits offsets only after successful persistence
- `review`: serves a read-only run review console backed by persisted DB views and shared artifacts; it does not consume Kafka or write state

## Audio Semantics

- Dataset: FMA-small
- Metadata filter: `subset=small`
- Normalization target: mono / 32 kHz
- Segmentation target: 3.0-second windows with 1.5-second overlap
- Processing outputs: RMS, silence gating, log-mel summary shape `(1,128,300)`, and Welford-style statistics

## Delivery Semantics

- Claim-check keeps payload-heavy data out of Kafka.
- Delivery is at-least-once.
- Sink behavior is idempotent and checkpoint-aware.
- Replay safety is verified on a bounded same-`run_id` restart/replay path.

## Honest Limits

- This repo does not claim production HA, multi-node Kafka, or exactly-once end to end.
- `audio.dlq` is reserved but not yet a fully modeled runtime path.
- `welford_snapshots` exists in SQL, but the current processing runtime does not persist that state yet.
