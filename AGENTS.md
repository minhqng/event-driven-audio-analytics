# AGENTS.md

Read this file first in every future thread.

## Interpretation

- `Fact`: explicit in the attached project documents or current repo status docs.
- `Inference`: derived by reconciling attached documents with the repo.
- `Conflict`: documents disagree, or the repo drifts from the attached documents.
- `Unknown`: not fixed yet; do not guess.

## Project Mission

- `Fact`: This repo is an academic PoC for event-driven microservices for real-time audio analytics in a private-cloud-like environment.
- `Fact`: FMA-small is the case-study dataset and is replayed as a simulated stream.
- `Fact`: The older audio data pipeline is the technical source of truth for audio/DSP logic that should be reused or refactored, not casually rewritten.
- `Fact`: The PoC must demonstrate claim-check, event-driven decoupling, time-series persistence, and dashboard-based observability.
- `Fact`: The goal is not a production-complete platform. The goal is an honest, runnable, end-to-end PoC.

## Source-Of-Truth Rules

- `Fact`: These root guidance files were created from the attached documents and should be treated as the durable replacement for those raw files.
- `Fact`: When these root files and current placeholder repo code disagree, treat these root files as authoritative for target intent unless a human says otherwise.
- `Inference`: Use current repo code and repo runbooks mainly to determine implementation status, not to redefine project scope.
- `Conflict`: The current repo contract/schema implementation is smaller than the planned contract in the attached documents.
- `Unknown`: If a needed detail is missing here and cannot be recovered from the repo, ask instead of inventing.

## Architecture Summary

- `Fact`: The project is framed around 4 core subsystems: Ingestion, Streaming, Processing, Visualization.
- `Inference`: The current repo realizes those subsystems through 3 runtime services plus platform components.
- `Fact`: `ingestion` owns metadata ETL, validation, decode/resample, segmentation planning, artifact writing, and publishing `audio.metadata` plus `audio.segment.ready`.
- `Fact`: `streaming` is Kafka KRaft plus the claim-check boundary. It is a subsystem, not a standalone business-logic service.
- `Fact`: `processing` consumes segment-ready events, loads claim-check artifacts, computes RMS, silence decisions, log-mel summaries, and Welford-style monitoring output, then publishes `audio.features` and `system.metrics`.
- `Fact`: `visualization` is realized by `writer` plus TimescaleDB plus Grafana.
- `Fact`: Kafka carries small events only. Large audio or feature payloads stay outside the broker.

## Scope Boundaries

- `Fact`: In scope: Docker Compose, Kafka KRaft, shared-volume claim-check, TimescaleDB, Grafana, FMA-small replay, metadata ETL, audio validation, mono 32 kHz normalization, 3.0 s segmentation with 1.5 s overlap, RMS, silence gate, log-mel summary shape, Welford-style statistics, idempotent persistence, checkpoints, and run/demo docs.
- `Fact`: Out of scope: Kubernetes, service mesh, HA/DR, multi-node Kafka, autoscaling, exactly-once end-to-end to an external DB, full schema-governance stack, production object storage/IAM, model serving, training pipelines, and full observability backends.
- `Inference`: Arrow/Parquet is acceptable as an internal artifact or manifest format when useful, but it is not the runtime center of gravity for this PoC.

## Fixed Role Boundaries

- `Fact`: Member A owns System / Infra / Persistence.
- `Fact`: Member B owns Audio / Data / Processing.

### Member A Owns

- `Fact`: Docker Compose, networking, health checks, startup order.
- `Fact`: Kafka KRaft, topic bootstrap, env/config, retry policy, DLQ wiring if enabled.
- `Fact`: TimescaleDB schema, migrations, UPSERT/idempotent sink behavior, checkpoints.
- `Fact`: Grafana provisioning, dashboards, benchmark/runbook/demo scripts.
- `Fact`: Repo layout hygiene and backup/demo artifacts.

### Member A Must Not Change Alone

- `Fact`: Do not rewrite DSP/audio logic from the old pipeline without syncing with Member B.
- `Fact`: Do not change input/output data meaning without syncing with Member B.

### Member B Owns

- `Fact`: Audit of the old data pipeline into reuse/refactor/defer.
- `Fact`: Metadata ETL, validation, PyAV decode/resample, segmentation, artifact writing.
- `Fact`: RMS, silence gate, log-mel, Welford, and audio-correctness tests.
- `Fact`: Output comparison against the old pipeline and academic explanation of DSP correctness/reuse.

### Member B Must Not Change Alone

- `Fact`: Do not change DB schema, event contracts, retention, partitioning, or checkpoint semantics without syncing with Member A.
- `Fact`: Do not expand processing into inference/model-serving scope.

### Shared Review Items

- `Fact`: Event contracts, idempotency keys, checkpoints, topic naming, natural keys, integration tests, and core docs require cross-review.
- `Fact`: Do not merge directly to `main` without at least smoke-level validation.

## Rules For Event Contracts, Schema, Topics, And Checkpoints

- `Fact`: No raw PCM, waveform blobs, or large tensors on Kafka as the normal path.
- `Fact`: Contract changes must update docs, JSON schemas, shared models, SQL, fixtures/tests, and topic bootstrap scripts together.
- `Fact`: Offset commits happen only after successful persistence and checkpoint update.
- `Fact`: The writer must stay idempotent under replay/retry.
- `Inference`: Treat the logical identity of a feature row as `(run_id, track_id, segment_idx)` even if the physical Timescale constraint also includes `ts`.
- `Conflict`: `audio.dlq` is present in the detailed plan but not in the current repo topic/bootstrap implementation.
- `Conflict`: The detailed plan expects a richer event envelope than the current repo implements.
- `Unknown`: Final retention values and partition counts are not yet locked in repo configuration.

## Coding And Documentation Expectations

- `Fact`: Reuse or refactor existing audio logic. Do not fork or duplicate it across services without reason.
- `Fact`: Preserve the project's terminology: claim-check, FMA-small, run_id, checkpoint, at-least-once, idempotent sink.
- `Fact`: Keep docs honest. Distinguish target design, current implementation, conflicts, and unknowns.
- `Fact`: Do not overclaim production readiness or end-to-end completeness without evidence.
- `Inference`: Avoid host-OS-specific assumptions. The repo standard is containerized runtime with host-side orchestration only.
- `Fact`: Update `IMPLEMENTATION_STATUS.md` and `TASK_BOARD.md` when progress or priorities materially change.
- `Fact`: If you change architecture or contracts, update `ARCHITECTURE_CONTRACTS.md` in the same thread.

## What To Verify Before Making Changes

- `Fact`: Check whether the change is still inside PoC scope.
- `Fact`: Check `ARCHITECTURE_CONTRACTS.md` for contract drift and locked integration boundaries.
- `Fact`: Check `IMPLEMENTATION_STATUS.md` so you do not implement from stale assumptions.
- `Fact`: For audio logic changes, compare against the reused pipeline semantics: subset `small`, mono 32 kHz, 3.0 s windows, 1.5 s overlap, log-mel `(1,128,300)`, silence gate, Welford behavior.
- `Fact`: For writer changes, verify natural keys, UPSERT semantics, checkpoint behavior, and replay safety.
- `Fact`: For Grafana/metrics changes, verify file provisioning and that the backing SQL/data actually exists.
- `Fact`: Run only maturity-appropriate validation. Do not claim more confidence than the current tests justify.

## Handoff Discipline

- `Fact`: Leave the repo in a state where the next agent can tell what is target design versus current scaffold.
- `Fact`: Record every material conflict instead of silently resolving it by assumption.
- `Fact`: If work changes progress, blockers, or priorities, update `IMPLEMENTATION_STATUS.md` and `TASK_BOARD.md`.
- `Fact`: If work changes contracts or integration boundaries, update `ARCHITECTURE_CONTRACTS.md` and the matching code/tests in the same change.
- `Fact`: In the final handoff, state what you verified, what you did not verify, and what still needs A/B synchronization.
