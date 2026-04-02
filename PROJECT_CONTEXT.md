# PROJECT_CONTEXT.md

## Interpretation

- `Fact`: explicit in attached docs or current repo status docs.
- `Inference`: derived by reconciling attached docs and repo state.
- `Conflict`: sources disagree or the repo drifts from the attached docs.
- `Unknown`: not fixed yet.

## Project Objective

- `Fact`: Build an event-driven microservices PoC for real-time audio analytics on a private-cloud-like environment.
- `Fact`: Use FMA-small as the replayed input stream.
- `Fact`: Reuse the old audio data pipeline as the trusted basis for audio semantics and correctness checks.
- `Fact`: Demonstrate why event-driven microservices fit streaming audio analytics, especially when combined with claim-check and time-series observability.

## Actual PoC Scope

- `Fact`: Runtime stack: Docker Compose, Kafka KRaft, shared-volume claim-check, TimescaleDB, Grafana, and core application services.
- `Fact`: Audio scope: metadata ETL, validation, mono 32 kHz normalization, 3.0 s segments with 1.5 s overlap, RMS, silence gate, log-mel summary shape, Welford-style statistics.
- `Fact`: Delivery scope: at-least-once event flow with idempotent persistence.
- `Fact`: Observability scope: system and data-quality metrics persisted to TimescaleDB and visualized in Grafana.
- `Fact`: Demonstration scope: replay a bounded sample or benchmark run, not a production deployment.

## Reused Pipeline Components

- `Fact`: Metadata ETL from `tracks.csv`, including flattened multi-level header handling and `subset=small` filtering.
- `Fact`: Audio validation and fail-fast checks.
- `Fact`: PyAV-based decode/resample logic.
- `Fact`: Segmentation at 3.0 s with 1.5 s overlap.
- `Fact`: Log-mel generation with target shape `(1,128,300)`.
- `Fact`: Silence detection/gating.
- `Fact`: Welford-style streaming statistics.
- `Fact`: Artist-aware split logic exists in the old pipeline.
- `Inference`: Artist-aware split is mainly a correctness/reference asset, not a mandatory runtime feature of the new PoC.

## Target Deliverables

- `Fact`: End-to-end Compose demo that replays FMA-small audio, emits events, processes segments, persists summaries, and shows Grafana dashboards.
- `Fact`: Evidence set should include logs, manifests, topic messages or snapshots, SQL counts, and dashboard screenshots.
- `Fact`: Documentation should cover architecture, contracts, run/demo steps, risks, and acceptance criteria.
- `Fact`: The detailed plan uses a 100-track dry run / benchmark as a representative demo target.

## Current Timeline Model

- `Conflict`: One architecture document uses an 8-week plan. One assignment document expands this into a 10-week plan.
- `Inference`: The stable part is the sequence, not the exact calendar length.
- `Inference`: Stable execution order is:
- `Inference`: Phase 1: scope lock, infra bootstrap, reuse audit.
- `Inference`: Phase 2: shared layer, event contract, DB schema, fake-event smoke path.
- `Inference`: Phase 3: ingestion on real sample data.
- `Inference`: Phase 4: processing and feature events.
- `Inference`: Phase 5: writer persistence, idempotency, checkpoints.
- `Inference`: Phase 6: dashboards and observability.
- `Inference`: Phase 7: hardening, replay/restart tests.
- `Inference`: Phase 8: benchmark, demo prep, freeze/polish.

## Important Constraints

- `Fact`: Team size is 2.
- `Fact`: Attached documents explicitly prioritize vertical slices and early integration over late big-bang integration.
- `Fact`: The PoC must stay small enough to run and explain honestly.
- `Fact`: The project should reuse existing audio logic rather than rewriting it.
- `Fact`: Payload-heavy data must stay outside Kafka.
- `Fact`: Private Cloud here means a self-managed environment, not a managed public-cloud stack.

## Stable Assumptions

- `Fact`: Dataset is FMA-small.
- `Fact`: Metadata filter is `subset=small`.
- `Fact`: Audio normalization target is mono / 32 kHz.
- `Fact`: Segment target is 3.0 s with 1.5 s overlap.
- `Fact`: Log-mel target shape is `(1,128,300)`.
- `Fact`: Core platform technologies are Kafka, TimescaleDB, Grafana, and shared storage.
- `Fact`: Claim-check is the intended data path for segment artifacts.
- `Fact`: Correctness target is at-least-once plus idempotent sink, not exactly-once end-to-end.
- `Inference`: The runtime should stay container-first and host-agnostic.

## Major Risks

- `Conflict`: The detailed plan's richer event contract does not match the repo's current placeholder schemas/models.
- `Conflict`: The detailed plan includes `audio.dlq`; the current repo topic/bootstrap scripts do not.
- `Conflict`: The exact schedule is unresolved because docs say both 8 weeks and 10 weeks.
- `Fact`: Late integration is explicitly called out as a project risk.
- `Fact`: Replay/retry can break correctness if idempotency and checkpoints are weak.
- `Fact`: Payload creep can abuse Kafka if claim-check is not enforced.
- `Fact`: Audio parity with the old pipeline can drift if reuse is replaced with ad hoc rewrites.
- `Fact`: Dashboard work can become hollow if real persistence is not completed first.

## Unknown Or Unresolved

- `Unknown`: Final canonical envelope field names between target design and repo implementation.
- `Unknown`: Whether `audio.dlq` is mandatory in the first runnable milestone or remains planned-only.
- `Unknown`: Final artifact extension choice for stored segments (`.wav` versus `.npy`); only the path shape is stable.
- `Unknown`: Final retention and partition settings beyond the current PoC defaults.
- `Unknown`: Whether `welford_snapshots` remains a required DB table in the implementation, because it is planned in docs but absent from current SQL.
