# System Overview

## Purpose

This repository scaffolds an event-driven real-time audio analytics PoC for FMA-small.
It is designed for Docker Compose on a private-cloud-like local environment and keeps the implementation disciplined without overstating production readiness.
    
## Core Boundary

- Kafka transports small events only.
- Shared storage under `artifacts/` holds large artifacts and manifests.
- TimescaleDB stores analytical summaries and operational metrics.
- Grafana reads from TimescaleDB and is provisioned entirely from files.

## Services

- `ingestion`: loads metadata, validates audio, plans segmentation, writes artifacts, and publishes metadata and segment-ready events.
- `processing`: consumes segment-ready events, loads artifacts, computes feature summaries, and publishes analytics and metrics events.
- `writer`: consumes metadata/features/metrics events and persists them with idempotent, checkpoint-aware behavior.

## Audio Semantics

- Dataset: FMA-small.
- Metadata filter: `subset=small`.
- Normalization target: mono / 32 kHz.
- Segmentation target: 3.0-second windows with 1.5-second overlap.
- Downstream analytics placeholders: RMS, silence gating, log-mel summary shape, and Welford-style streaming statistics.
