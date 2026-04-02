# IMPLEMENTATION_STATUS.md

Status reconciled from the attached documents and the current repo scaffold.

## Interpretation

- `Fact`: explicit in attached docs or current repo status docs.
- `Inference`: derived from current repo code layout and placeholders.
- `Conflict`: plan/target design differs from repo scaffold.
- `Unknown`: not verified.

## What Is Already Decided

- `Fact`: The project is a PoC, not a production platform.
- `Fact`: Core platform is Kafka KRaft + shared claim-check storage + TimescaleDB + Grafana.
- `Fact`: FMA-small is the only dataset in scope.
- `Fact`: Audio semantics are mono 32 kHz, 3.0 s segments, 1.5 s overlap, RMS, silence gate, log-mel summary, Welford-style stats.
- `Fact`: Delivery semantics are at-least-once with idempotent sink behavior.
- `Fact`: The old audio pipeline is the reference for reuse and correctness.
- `Fact`: Member A owns System/Infra/Persistence. Member B owns Audio/Data/Processing.

## What The Repo Already Implements

- `Fact`: `docker-compose.yml` defines Kafka, TimescaleDB, Grafana, ingestion, processing, and writer services.
- `Fact`: SQL init files create `track_metadata`, `audio_features`, `system_metrics`, `run_checkpoints`, and operational views.
- `Fact`: Grafana datasource and dashboard provisioning are file-backed.
- `Fact`: Topic bootstrap scripts exist for `audio.metadata`, `audio.segment.ready`, `audio.features`, and `system.metrics`.
- `Fact`: JSON schemas, shared models, and fixtures exist for those 4 topics.
- `Fact`: `REUSE_MAP.md` now records the Week 1 Member B reuse audit against the old FMA-small pipeline.
- `Fact`: `tests/fixtures/audio/` now contains deterministic synthetic audio fixtures plus a manifest-only FMA-small reference pack strategy.
- `Fact`: Lightweight smoke scripts and placeholder tests exist.
- `Fact`: Repo docs explicitly describe the current state as a Week 1 bootstrap scaffold.

## Repo-Present But Still Placeholder

- `Inference`: `ingestion` service structure exists, but metadata loading, validation, segmentation, and artifact writing are not implemented.
- `Inference`: `processing` service structure exists, but artifact loading, RMS, log-mel, and event loops are mostly placeholders.
- `Inference`: `writer` contains UPSERT SQL strings and checkpoint record helpers, but not real Kafka polling or DB persistence logic.
- `Inference`: Welford exists only as a minimal scalar helper, not as the full reused mel-bin statistics path.
- `Inference`: Dashboards are provisioned but remain placeholder dashboards, not evidence of real analytics.
- `Inference`: Current tests validate shape/contracts/scaffold assumptions more than runnable end-to-end behavior.

## What Is Documented As Implemented

- `Fact`: Week 1 infrastructure bring-up is documented as validated.
- `Fact`: The stack can render Compose config, bring up Kafka/TimescaleDB/Grafana, mount `artifacts/`, and start scaffold containers that exit cleanly.
- `Fact`: The current repo does not claim end-to-end audio analytics execution yet.

## What Is Planned But Not Yet Implemented

- `Fact`: Flattened-header metadata ETL for `tracks.csv`.
- `Fact`: Real audio validation against FMA-small sample files.
- `Fact`: PyAV decode/resample integration inside the microservice pipeline.
- `Fact`: Real 3.0 s / 1.5 s segmentation with checksum and manifest generation.
- `Fact`: Claim-check artifact load and checksum verification in processing.
- `Fact`: RMS, silence gate, log-mel, and Welford parity against the old pipeline.
- `Fact`: Kafka consumption/publication loops for all services.
- `Fact`: Idempotent writer persistence with real checkpoints and replay-safe resume.
- `Fact`: Real dashboard panels backed by real DB data.
- `Fact`: Restart/replay reliability scenarios, 100-track dry run, benchmark notes, and demo artifacts.

## What Is Explicitly Deferred

- `Fact`: Kubernetes and service mesh.
- `Fact`: Multi-node Kafka and HA/DR.
- `Fact`: Exactly-once end-to-end to an external DB.
- `Fact`: Full schema registry/governance stack.
- `Fact`: Production object storage/IAM and data lake concerns.
- `Fact`: Online inference/model serving and broader MLOps.
- `Fact`: Full OpenTelemetry collector/backend stack.

## Week-By-Week Status Recovery

| Phase | Planned Meaning | Current Status |
| --- | --- | --- |
| Week 1 / Phase 1 | Scope lock, infra bootstrap, reuse audit | `Fact`: infra scaffold is documented as complete. `Fact`: `REUSE_MAP.md` and `tests/fixtures/audio/` now document the Week 1 Member B reuse audit and fixture strategy. |
| Week 2 / Phase 2 | Shared layer, event contract, DB schema, fake-event smoke path | `Inference`: schemas/SQL/helpers exist. `Conflict`: required fake-event-to-DB success is not documented. |
| Week 3 / Phase 3 | Ingestion on real sample data | `Inference`: not implemented. |
| Week 4 / Phase 4 | Processing / feature emission | `Inference`: not implemented. |
| Week 5 / Phase 5 | Writer idempotency and checkpoints | `Inference`: SQL scaffolding exists, runtime implementation missing. |
| Week 6 / Phase 6 | Dashboards / observability | `Inference`: provisioning exists, real data path missing. |
| Week 7 / Phase 7 | Hardening / restart / benchmark prep | `Inference`: not implemented. |
| Week 8 / Phase 8 | Freeze / polish / demo readiness | `Inference`: not implemented. |
| Weeks 9-10 | Extended-plan benchmark and freeze split | `Conflict`: present only in one planning document; no repo evidence yet. |

## Current Conflicts And Drift

- `Conflict`: Attached plans define a richer event envelope than the repo currently implements.
- `Conflict`: Attached plans include `audio.dlq`; repo topic scripts and constants do not.
- `Conflict`: Detailed plan expects `welford_snapshots`; current SQL does not create it.
- `Conflict`: Detailed plan uses logical natural key `(run_id, track_id, segment_idx)`; current SQL physical PK includes `ts`.
- `Conflict`: Documents disagree on overall schedule length: 8 weeks versus 10 weeks.
- `Conflict`: One plan names openSUSE Tumbleweed as host baseline; current repo/runbooks are effectively host-agnostic via Linux containers plus bash/PowerShell helpers.
- `Conflict`: The old audio pipeline depends on `av`, `polars`, `torch`, and `torchaudio`, but the current repo `pyproject.toml` does not yet declare those reuse-critical dependencies.
- `Conflict`: The current repo only has scalar placeholder Welford logic, while the old pipeline's recoverable behavior is vector-oriented over mel bins.

## Unresolved Blockers And Dependencies

- `Fact`: Contract drift must be reconciled before real end-to-end implementation.
- `Fact`: A concrete reuse-map from the old pipeline is now checked in as `REUSE_MAP.md`.
- `Fact`: Processing correctness depends on access to sample FMA-small data and old-pipeline reference behavior.
- `Fact`: Direct reuse of the old audio semantics still depends on adding the missing audio/data dependencies to this repo in a future Member B thread.
- `Fact`: Writer correctness depends on locking natural-key/idempotency/checkpoint semantics first.
- `Fact`: Dashboard work depends on real persistence first; placeholders are not enough.

## Items Requiring Member A/B Synchronization

- `Fact`: Final event envelope and payload field names.
- `Fact`: Topic set, especially whether `audio.dlq` is active now or later.
- `Fact`: Natural key versus physical Timescale constraint strategy.
- `Fact`: Checkpoint semantics and replay behavior.
- `Fact`: Artifact path and manifest conventions.
- `Fact`: Metrics naming/labels used by dashboards.
- `Conflict`: Exact timeline framing for reporting: 8-week condensed plan versus 10-week expanded plan.
