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
- `Fact`: SQL init files create `track_metadata`, `audio_features`, `system_metrics`, `run_checkpoints`, `welford_snapshots`, and operational views.
- `Fact`: Grafana datasource and dashboard provisioning are file-backed.
- `Fact`: Topic bootstrap scripts and shared topic constants now reserve `audio.metadata`, `audio.segment.ready`, `audio.features`, `system.metrics`, and `audio.dlq`.
- `Fact`: `event-contracts.md` now locks Event Contract v1 for the 4 primary topics.
- `Fact`: JSON schemas, shared models, and contract fixtures/tests now reflect the locked v1 envelope and payload definitions for `audio.metadata`, `audio.segment.ready`, `audio.features`, and `system.metrics`.
- `Fact`: Shared semantic validation now enforces canonical v1 invariants that JSON Schema alone does not express, including top-level/payload `run_id` consistency.
- `Fact`: Writer SQL/persistence now stores `audio.metadata.duration_s` and optional `system.metrics.unit`, keeping the locked v1 payload lossless on the current writer path.
- `Fact`: `REUSE_MAP.md` now records the Week 1 Member B reuse audit against the old FMA-small pipeline.
- `Fact`: `tests/fixtures/audio/` now contains deterministic synthetic audio fixtures plus a manifest-only FMA-small reference pack strategy.
- `Fact`: `ingestion` now ports the first real Week 3 Member B path: flattened-header metadata ETL, structured audio validation, PyAV decode/resample to mono 32 kHz, 3.0 s / 1.5 s segmentation, WAV claim-check artifact writing with SHA-256 checksums, Parquet manifest updates, and canonical `audio.metadata` plus `audio.segment.ready` envelope emission.
- `Fact`: The Week 4 Member B ingestion hardening baseline now verifies artifact/checksum/manifest linkage before segment-ready publication, omits optional payload fields instead of serializing schema-invalid `null`s, emits an explicit `validation_status=no_segments` outcome when decoded audio yields no legal segments under the inherited tail-padding rule, and requires positive metadata-side `track.duration` so reject-path `audio.metadata` events stay contract-valid.
- `Fact`: Member A Week 3 Compose wiring now mounts `artifacts/` as the shared claim-check bind mount, mounts a read-only bounded fixture dataset for smoke runs, applies bounded container log retention, and exposes env-backed producer retry/backoff settings for `ingestion`.
- `Fact`: Member A Week 4 runtime hardening now adds an explicit `ingestion preflight` path, startup dependency gating for Kafka topics plus mounted inputs, a Compose healthcheck that exercises the one-shot preflight, run-scoped artifact-target write probing under `/artifacts/runs/<run_id>/...`, and structured JSON logs that now carry `trace_id`, `run_id`, and `track_id` context on the bounded ingestion path.
- `Fact`: `ingestion` now emits run-level `system.metrics` for `tracks_total`, `segments_total`, `validation_failures`, and `artifact_write_ms` on the canonical v1 envelope.
- `Fact`: `ingestion` publish helpers now wait for Kafka delivery reports before treating `audio.metadata`, `audio.segment.ready`, or `system.metrics` publication as successful.
- `Fact`: The bounded ingestion smoke flow now verifies `ingestion preflight`, real Kafka publication, exact current-run message counts by `RUN_ID`, reject-path `validation_status=probe_failed` behavior for track `666`, run-manifest contents under `/artifacts/runs/<run_id>/manifests/segments.parquet`, and structured-log context for one success track plus one reject track.
- `Fact`: Canonical v1 now treats `system.metrics` with `labels_json.scope=run_total` as snapshot identities that stay replay-stable across `ts` refreshes, keeping the producer-side event contract aligned with the writer's replay-safe sink rule.
- `Fact`: `writer` now consumes the locked v1 envelope for `audio.metadata`, `audio.features`, and `system.metrics`, persists them transactionally, updates checkpoints, and commits offsets only after successful persistence.
- `Fact`: `writer` now treats `system.metrics` rows with `labels_json.scope=run_total` as replay-safe snapshot upserts keyed by `(run_id, service_name, metric_name, labels_json)`, self-heals historical duplicates under the writer advisory lock using chunk-aware `(tableoid, ctid)` survivor targeting on the Timescale hypertable, rewrites the logical snapshot row with the latest `ts`/value/unit payload, and leaves other metrics append-only.
- `Fact`: The fake-event smoke path now publishes canonical v1 fixtures for `audio.metadata` plus `audio.features`, asserts TimescaleDB rows and checkpoint rows, and verifies replay-safe feature row counts.
- `Fact`: Lightweight smoke scripts and targeted writer regression tests now also verify `system.metrics` `scope=run_total` duplicate repair on a live Timescale hypertable by seeding cross-chunk duplicates and repairing them through the Kafka writer path.
- `Fact`: The Week 3 ingestion smoke path now has both shell and PowerShell host wrappers, so the bounded broker-backed smoke run remains runnable from the repo's supported Windows host orchestration path.
- `Fact`: Week 3 smoke validation now covers committed synthetic fixtures plus a local real-FMA sample run for tracks `2` and `666`, with observed segment counts `19` and `20` matching the documented legacy-reference counts.

## Repo-Present But Still Placeholder

- `Fact`: `ingestion` now implements the first real track-to-artifact path and is exercised under a live Kafka broker in Compose on a bounded committed smoke fixture set.
- `Inference`: `processing` service structure exists, but artifact loading, RMS, log-mel, and event loops are mostly placeholders.
- `Inference`: `writer` runtime is real for the current scaffold contract, but it is not yet exercised by real ingestion/processing traffic and does not publish to `audio.dlq`; `ingestion` likewise keeps `audio.dlq` log-only for unrecoverable failures in the current Week 4 runtime.
- `Inference`: `welford_snapshots` storage exists, but the full reused mel-bin Welford processing path is still not implemented.
- `Inference`: Dashboards are provisioned but remain placeholder dashboards, not evidence of real analytics.
- `Inference`: Current tests validate shape/contracts/scaffold assumptions more than runnable end-to-end behavior.

## What Is Documented As Implemented

- `Fact`: Week 1 infrastructure bring-up is documented as validated.
- `Fact`: The stack can render Compose config, bring up Kafka/TimescaleDB/Grafana, mount `artifacts/`, and start scaffold containers that exit cleanly.
- `Fact`: The current repo documents and exercises a fake-event writer path from Kafka to TimescaleDB, including checkpoint updates and idempotent feature replay.
- `Fact`: The current repo can now execute the ingestion-owned Week 3 path over both committed bounded smoke fixtures and local real FMA-small sample input through artifact writing and canonical event emission, but it still does not claim full end-to-end audio analytics execution through processing, persistence, and dashboards.

## What Is Planned But Not Yet Implemented

- `Fact`: Claim-check artifact load and checksum verification in processing.
- `Fact`: RMS, silence gate, log-mel, and Welford parity against the old pipeline.
- `Fact`: Live Kafka broker-backed publication/consumption evidence for the real ingestion path into writer persistence and dashboards.
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
| Week 2 / Phase 2 | Shared layer, event contract, DB schema, fake-event smoke path | `Fact`: schemas/SQL/helpers exist. `Fact`: Event Contract v1 is now locked in root docs, shared schemas/models, contract fixtures/tests, the writer runtime, and the fake-event smoke path. `Conflict`: the DLQ contract remains unresolved. |
| Week 3 / Phase 3 | Ingestion on real sample data | `Fact`: initial real ingestion path is implemented for Member B scope. `Fact`: metadata ETL, validation, PyAV decode/resample, segmentation, artifact writing, checksum + manifest creation, and canonical `audio.metadata` / `audio.segment.ready` emission now work on committed fixtures and local real FMA samples. `Fact`: Member A Week 3 Compose/runtime work now proves broker-backed `audio.metadata`, `audio.segment.ready`, and `system.metrics` publication on the bounded smoke path. |
| Week 4 / Phase 4 | Processing / feature emission | `Inference`: processing remains not implemented, but the Member A-owned ingestion runtime hardening for startup readiness, preflight, log context, and bounded Kafka integration smoke is now implemented. |
| Week 5 / Phase 5 | Writer idempotency and checkpoints | `Inference`: runtime implementation now exists for the current scaffold contract, but broader replay hardening under real producer traffic is still pending. |
| Week 6 / Phase 6 | Dashboards / observability | `Inference`: provisioning exists, real data path missing. |
| Week 7 / Phase 7 | Hardening / restart / benchmark prep | `Inference`: not implemented. |
| Week 8 / Phase 8 | Freeze / polish / demo readiness | `Inference`: not implemented. |
| Weeks 9-10 | Extended-plan benchmark and freeze split | `Conflict`: present only in one planning document; no repo evidence yet. |

## Current Conflicts And Drift

- `Conflict`: `audio.dlq` is now reserved in topic bootstrap/constants, but the repo still lacks matching schema/model/fixture coverage and a real DLQ publish/consume flow.
- `Conflict`: Detailed plan uses logical natural key `(run_id, track_id, segment_idx)`; current SQL physical PK includes `ts`.
- `Conflict`: Documents disagree on overall schedule length: 8 weeks versus 10 weeks.
- `Conflict`: One plan names openSUSE Tumbleweed as host baseline; current repo/runbooks are effectively host-agnostic via Linux containers plus bash/PowerShell helpers.
- `Conflict`: The old audio pipeline depends on `av`, `polars`, `torch`, and `torchaudio`; the current repo now declares the Week 3-critical `av` and `polars` dependencies, but the Week 4 processing path still lacks the heavier `torch` / `torchaudio` reuse-critical dependencies.
- `Conflict`: The current repo has reserved `welford_snapshots` storage, but the old pipeline's recoverable Welford behavior is still vector-oriented over mel bins and not yet wired into runtime processing.

## Unresolved Blockers And Dependencies

- `Fact`: The canonical v1 contract is now adopted in the shared layer, writer runtime, fake-event smoke path, and broker-backed ingestion smoke path, but real ingestion-to-writer-to-dashboard implementation is still required before real end-to-end completion.
- `Fact`: A concrete reuse-map from the old pipeline is now checked in as `REUSE_MAP.md`.
- `Fact`: Processing correctness depends on access to sample FMA-small data and old-pipeline reference behavior.
- `Fact`: Week 3 reuse-critical audio/data dependencies for metadata ETL and PyAV decode/resample are now declared in `pyproject.toml`; Week 4 mel-processing parity still depends on adding the remaining `torch` / `torchaudio` stack.
- `Fact`: Writer correctness now depends on keeping natural-key/idempotency/checkpoint semantics stable as real ingestion and processing are implemented; run-level `system.metrics` now rely on a shared snapshot identity plus sink-side timestamp refresh rule.
- `Fact`: Dashboard work depends on real persistence first; placeholders are not enough.

## Items Requiring Member A/B Synchronization

- `Fact`: Topic set, especially whether `audio.dlq` is active now or later.
- `Fact`: Natural key versus physical Timescale constraint strategy.
- `Fact`: Checkpoint semantics and replay behavior.
- `Fact`: Artifact path and manifest conventions.
- `Fact`: Metrics naming/labels used by dashboards.
- `Conflict`: Exact timeline framing for reporting: 8-week condensed plan versus 10-week expanded plan.
