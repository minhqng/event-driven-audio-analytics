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
- `Fact`: Week 7 now provisions a stable TimescaleDB datasource UID plus real `Audio Quality` and `System Health` dashboards backed by `audio_features`, `track_metadata`, `system_metrics`, and the dashboard-focused SQL views.
- `Fact`: Topic bootstrap scripts and shared topic constants now reserve `audio.metadata`, `audio.segment.ready`, `audio.features`, `system.metrics`, and `audio.dlq`.
- `Fact`: `event-contracts.md` now locks Event Contract v1 for the 4 primary topics.
- `Fact`: JSON schemas, shared models, and contract fixtures/tests now reflect the locked v1 envelope and payload definitions for `audio.metadata`, `audio.segment.ready`, `audio.features`, and `system.metrics`.
- `Fact`: Shared semantic validation now enforces canonical v1 invariants that JSON Schema alone does not express, including top-level/payload `run_id` consistency.
- `Fact`: Writer SQL/persistence now stores `audio.metadata.duration_s` and optional `system.metrics.unit`, keeping the locked v1 payload lossless on the current writer path.
- `Fact`: `REUSE_MAP.md` now records the Week 1 Member B reuse audit against the old FMA-small pipeline.
- `Fact`: `tests/fixtures/audio/` now contains deterministic synthetic audio fixtures, committed `smoke_fma_small/` mirrors for the bounded smoke path, and a documented repo-local slot for non-committed `tracks.csv` plus `fma_small/` FMA-small copies.
- `Fact`: `ingestion` now ports the first real Week 3 Member B path: flattened-header metadata ETL, structured audio validation, PyAV decode/resample to mono 32 kHz, 3.0 s / 1.5 s segmentation, WAV claim-check artifact writing with SHA-256 checksums, Parquet manifest updates, and canonical `audio.metadata` plus `audio.segment.ready` envelope emission.
- `Fact`: The Week 4 Member B ingestion hardening baseline now verifies artifact/checksum/manifest linkage before segment-ready publication, omits optional payload fields instead of serializing schema-invalid `null`s, emits an explicit `validation_status=no_segments` outcome when decoded audio yields no legal segments under the inherited tail-padding rule, and requires positive metadata-side `track.duration` so reject-path `audio.metadata` events stay contract-valid.
- `Fact`: `processing` now ports the real Member B Week 5 path: claim-check artifact loading from `artifact_uri`, checksum validation before DSP work, segment RMS summaries, inherited post-log-mel silence gating, exact `(1,128,300)` log-mel extraction, vector-valued Welford updates over mel-bin means, canonical `audio.features` emission, and unit coverage over tone, silent, and short-clip fixtures.
- `Fact`: Member A Week 5 runtime hardening now adds a real long-lived `processing` Compose service with `preflight`, explicit consumer config, structured JSON logging, bounded retry for `artifact_not_ready` and `checksum_mismatch`, terminal non-commit exit behavior when retries are exhausted, and canonical `processing_ms`, `silent_ratio`, plus best-effort `feature_errors` publication on `system.metrics`.
- `Fact`: The Week 5 `processing` runtime now persists run-scoped logical segment state under `/artifacts/runs/<run_id>/state/processing_metrics.json`, which keeps `silent_ratio` `run_total` snapshots stable across service restarts for the same logical run and prevents replayed logical segments from inflating that snapshot after restart.
- `Fact`: Week 6 Member B correctness hardening now verifies the current processing path against the legacy FMA-small semantics on the committed stereo fixture plus a local 5-track FMA reference pack, fixes the shared decode/resample downmix drift back to arithmetic-mean mono behavior, and documents that `audio.features` remains summary-first with no active `feature_uri` in v1.
- `Fact`: The Week 5 processing smoke path now has both shell and PowerShell host wrappers, so the bounded broker-backed `ingestion -> Kafka -> processing` run remains runnable from the repo's supported Linux and Windows host orchestration paths and is meant to validate healthy runs without `feature_errors`.
- `Fact`: Service Docker builds now install per-service Python extras, so `ingestion` and `writer` images no longer pull the `torch` / `torchaudio` DSP layer that is only needed for processing and full-suite tests.
- `Fact`: The `processing` and `pytest` Docker images now preinstall CPU-only PyTorch wheels, avoiding the accidental CUDA dependency fan-out that made the earlier Docker smoke/test path unnecessarily heavy.
- `Fact`: The repo now provides an official containerized `pytest` service plus shell/PowerShell wrappers, and that service now runs against image-bundled repo contents instead of a bind-mounted workspace so full-suite discovery no longer trips over host-side permission drift.
- `Fact`: Member A Week 3 Compose wiring now mounts `artifacts/` as the shared claim-check bind mount, mounts a read-only bounded fixture dataset for smoke runs, applies bounded container log retention, and exposes env-backed producer retry/backoff settings for `ingestion`.
- `Fact`: The shared `artifacts/` and bounded fixture mounts for `ingestion` plus `processing` now use a shared SELinux label, so the long-lived `processing` consumer can read ingestion-produced claim-check artifacts during the same Compose run without spurious artifact permission failures.
- `Fact`: Member A Week 4 runtime hardening now adds an explicit `ingestion preflight` path, startup dependency gating for Kafka topics plus mounted inputs, a Compose healthcheck that exercises the one-shot preflight, run-scoped artifact-target write probing under `/artifacts/runs/<run_id>/...`, and structured JSON logs that now carry `trace_id`, `run_id`, and `track_id` context on the bounded ingestion path.
- `Fact`: `ingestion` now emits run-level `system.metrics` for `tracks_total`, `segments_total`, `validation_failures`, and `artifact_write_ms` on the canonical v1 envelope.
- `Fact`: `ingestion` publish helpers now wait for Kafka delivery reports before treating `audio.metadata`, `audio.segment.ready`, or `system.metrics` publication as successful.
- `Fact`: The bounded ingestion smoke flow now verifies `ingestion preflight`, real Kafka publication, exact current-run message counts by `RUN_ID`, reject-path `validation_status=probe_failed` behavior for track `666`, run-manifest contents under `/artifacts/runs/<run_id>/manifests/segments.parquet`, and structured-log context for one success track plus one reject track.
- `Fact`: Canonical v1 now treats `system.metrics` with `labels_json.scope=run_total` as snapshot identities that stay replay-stable across `ts` refreshes, keeping the producer-side event contract aligned with the writer's replay-safe sink rule.
- `Fact`: `writer` now consumes the locked v1 envelope for `audio.metadata`, `audio.features`, and `system.metrics`, persists them transactionally, updates checkpoints, and commits offsets only after successful persistence.
- `Fact`: `writer` now treats `system.metrics` rows with `labels_json.scope=run_total` as replay-safe snapshot upserts keyed by `(run_id, service_name, metric_name, labels_json)`, self-heals historical duplicates under the writer advisory lock using chunk-aware `(tableoid, ctid)` survivor targeting on the Timescale hypertable, rewrites the logical snapshot row with the latest `ts`/value/unit payload, and leaves other metrics append-only.
- `Fact`: The fake-event smoke path now publishes canonical v1 fixtures for `audio.metadata` plus `audio.features`, asserts TimescaleDB rows and checkpoint rows, and verifies replay-safe feature row counts.
- `Fact`: Lightweight smoke scripts and targeted writer regression tests now also verify `system.metrics` `scope=run_total` duplicate repair on a live Timescale hypertable by seeding cross-chunk duplicates and repairing them through the Kafka writer path.
- `Fact`: Member A Week 6 writer hardening now adds a real long-lived `writer` Compose service with `preflight`, explicit consumer config, psycopg connection pooling, structured JSON logging, fail-stop behavior on payload/checkpoint/offset-commit failure, and direct-to-DB internal metrics `write_ms`, `rows_upserted`, plus best-effort `write_failures`.
- `Fact`: The bounded Week 6 smoke path now proves a broker-backed `ingestion -> Kafka -> processing -> writer -> TimescaleDB` run for the active `RUN_ID`, verifies persisted `track_metadata`, `audio_features`, processing-owned `system.metrics`, writer-owned internal metrics, and `run_checkpoints`, and keeps the older fake-event writer smoke as the replay/idempotency baseline.
- `Fact`: Week 7 now adds `vw_dashboard_metric_events`, `vw_dashboard_run_total_metrics`, `vw_dashboard_run_validation`, and `vw_dashboard_run_summary` as the canonical Grafana query surface over the persisted observability data.
- `Fact`: Week 7 now centralizes the shared metric-label convention in `shared/metric_labels.py`, keeping `scope`, `topic`, `status`, and optional `failure_class` stable across ingestion, processing, writer, and Grafana queries.
- `Fact`: The Week 7 demo/evidence path now stages deterministic synthetic demo inputs, runs `week7-high-energy`, `week7-silent-oriented`, and `week7-validation-failure` through the live Compose stack, verifies the resulting TimescaleDB summaries, and captures Grafana screenshots under `artifacts/demo/week7/`.
- `Fact`: Week 7.5 now polishes the intermediate-demo path with a dedicated runbook, clearer dashboard panel titles, explicit recent-window Grafana URLs for live readability, generated artifact notes, and a repo-local FMA-small burst helper that targets `tests/fixtures/audio/tracks.csv` plus `tests/fixtures/audio/fma_small/`.
- `Fact`: Week 8 now adds graceful `SIGTERM` / `SIGINT` shutdown handling for the long-lived `processing` and `writer` consumers, a bounded broker-backed restart/replay smoke path for the same `run_id`, explicit fail-fast preflight evidence before topic bootstrap, and a combined `generate-week8-evidence.*` handoff path that refreshes both reliability and dashboard artifacts.
- `Fact`: The official containerized `pytest` path is green in the current workspace with `176 passed, 5 skipped`; the 5 skips are the optional Week 6 legacy-reference parity tests when the legacy checkout or its extra reference dependencies are unavailable.
- `Fact`: The Week 3 ingestion smoke path now has both shell and PowerShell host wrappers, so the bounded broker-backed smoke run remains runnable from the repo's supported Windows host orchestration path.
- `Fact`: Week 3 smoke validation now covers committed synthetic fixtures plus a local real-FMA sample run for tracks `2` and `666`, with observed segment counts `19` and `20` matching the documented legacy-reference counts.

## Repo-Present But Still Placeholder

- `Fact`: `ingestion` now implements the first real track-to-artifact path and is exercised under a live Kafka broker in Compose on a bounded committed smoke fixture set.
- `Fact`: `processing` now has a real claim-check-to-`audio.features` path, and broker-backed evidence now reaches writer persistence in TimescaleDB on the bounded Week 6 smoke path.
- `Fact`: The Compose `processing` service now stops on terminal record failures instead of auto-restarting, so unresolved poison records do not spin in an infinite replay loop while `audio.dlq` remains reserved.
- `Inference`: `writer` runtime is now exercised by real ingestion/processing traffic on both the bounded healthy path and the bounded same-`run_id` restart/replay path, but DLQ behavior and benchmark-scale replay evidence still remain later-phase work; `ingestion` likewise keeps `audio.dlq` log-only for unrecoverable failures in the current Week 4 runtime.
- `Inference`: `welford_snapshots` storage exists, but the current Week 5 processing path keeps Welford state in memory only; persisted snapshot semantics remain unresolved.
- `Inference`: Benchmark-scale replay/restart evidence under repeated real producer traffic is still missing even though the bounded Week 8 same-`run_id` replay path is now real.

## What Is Documented As Implemented

- `Fact`: Week 1 infrastructure bring-up is documented as validated.
- `Fact`: The stack can render Compose config, bring up Kafka/TimescaleDB/Grafana, mount `artifacts/`, and start the current long-lived `processing` / `writer` runtime containers plus one-shot `ingestion` demo runs cleanly.
- `Fact`: The current repo documents and exercises a fake-event writer path from Kafka to TimescaleDB, including checkpoint updates and idempotent feature replay.
- `Fact`: The current repo can now execute the ingestion-owned Week 3 path over both committed bounded smoke fixtures and local real FMA-small sample input through artifact writing and canonical event emission, but it still does not claim full end-to-end audio analytics execution through processing, persistence, and dashboards.
- `Fact`: The current repo can now execute the bounded broker-backed path from `audio.segment.ready` through `audio.features`, processing-owned `system.metrics`, writer persistence, TimescaleDB query views, and file-provisioned Grafana dashboards inside Compose.
- `Fact`: The current repo can now also execute a bounded broker-backed restart/replay verification for the same `run_id`, including pre-bootstrap fail-fast evidence, service restart, checkpoint advancement, replay-stable `silent_ratio`, and replay-stable processing recovery state.

## What Is Planned But Not Yet Implemented

- `Fact`: A 100-track dry run, benchmark-scale evidence beyond the current bounded Week 8 artifacts, a real DLQ flow, and persisted `welford_snapshots`.

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
| Week 4 / Phase 4 | Processing / feature emission | `Fact`: processing now implements the Member B claim-check path from `audio.segment.ready` through checksum validation, RMS / silence gate / exact log-mel / vector Welford, and canonical `audio.features` publication, with unit coverage on tone, silent, and short-clip fixtures. |
| Week 5 / Phase 5 | Writer idempotency and checkpoints | `Fact`: writer idempotency and checkpoint mechanics now exist on both the fixture-driven smoke path and the bounded broker-backed `processing -> writer -> TimescaleDB` path. `Inference`: broader replay hardening under real producer traffic is still pending. |
| Week 6 / Phase 6 | Dashboards / observability | `Fact`: the real broker-backed persistence path into TimescaleDB now exists, including writer-owned internal metrics and checkpoint evidence. `Fact`: Week 7 now completes the real Grafana path with file-provisioned datasource/dashboard loading, stable SQL views, real queries, and captured dashboard evidence. |
| Week 7 / Phase 7 | Hardening / restart / benchmark prep | `Fact`: bounded restart/replay hardening is now implemented. `Fact`: the repo now proves missing-topic fail-fast preflights, same-`run_id` replay after restarting `processing` and `writer`, checkpoint advancement, and replay-stable processing recovery state on the committed smoke fixture path. `Inference`: benchmark prep beyond the bounded PoC path remains later work. |
| Week 8 / Phase 8 | Freeze / polish / demo readiness | `Fact`: implemented within the locked PoC scope. `Fact`: README/runbooks now point to a final Week 8 evidence path, dashboard interpretation remains aligned with the real Grafana panels, and `IMPLEMENTATION_STATUS.md` plus `TASK_BOARD.md` now distinguish done/verified/partial/deferred status for final reporting. |
| Weeks 9-10 | Extended-plan benchmark and freeze split | `Conflict`: present only in one planning document; no repo evidence yet. |

## Current Conflicts And Drift

- `Conflict`: `audio.dlq` is now reserved in topic bootstrap/constants, but the repo still lacks matching schema/model/fixture coverage and a real DLQ publish/consume flow.
- `Conflict`: Detailed plan uses logical natural key `(run_id, track_id, segment_idx)`; current SQL physical PK includes `ts`.
- `Conflict`: Documents disagree on overall schedule length: 8 weeks versus 10 weeks.
- `Conflict`: One plan names openSUSE Tumbleweed as host baseline; current repo/runbooks are effectively host-agnostic via Linux containers plus bash/PowerShell helpers.
- `Conflict`: The locked `audio.features` v1 payload requires JSON-finite `rms`, while the inherited RMS helper returns `-inf` for truly silent audio; the current Week 5 processing path therefore clamps non-finite transport values to `-60.0` while preserving `silent_flag=true`.
- `Conflict`: The current repo has reserved `welford_snapshots` storage, but the old pipeline's recoverable Welford behavior is now wired into runtime processing only as in-memory vector state; persisted snapshot semantics still need A/B synchronization.
- `Conflict`: `welford_snapshots` storage still exists without a processing-side persisted producer path; Week 6 reference validation only verifies the update rule and summary-level parity, not persisted snapshot behavior.

## Unresolved Blockers And Dependencies

- `Fact`: The canonical v1 contract is now adopted in the shared layer, writer runtime, fake-event smoke path, broker-backed ingestion smoke path, broker-backed processing smoke path, the bounded broker-backed writer-to-TimescaleDB smoke path, and the Week 7 dashboard evidence path.
- `Fact`: A concrete reuse-map from the old pipeline is now checked in as `REUSE_MAP.md`.
- `Fact`: Processing correctness depends on access to sample FMA-small data and old-pipeline reference behavior.
- `Fact`: Week 3 and Week 5 reuse-critical audio/data dependencies are now declared in `pyproject.toml`, including the `torch` / `torchaudio` stack required for log-mel parity.
- `Fact`: Writer correctness now depends on keeping natural-key/idempotency/checkpoint semantics stable as real ingestion and processing are implemented; run-level `system.metrics` now rely on a shared snapshot identity plus sink-side timestamp refresh rule.
- `Fact`: Broader replay/restart work now depends on keeping the Week 7 dashboard query surface and metric-label convention stable while producer traffic grows.
- `Fact`: The bounded Week 8 replay smoke now depends on the same long-lived Kafka consumer configuration used by the Compose services, including clean shutdown under `docker compose restart`.
- `Inference`: The processing smoke path and the containerized `pytest` runner remain the heaviest Docker builds because they intentionally carry the DSP stack, but they now stay on CPU-only PyTorch wheels while the lighter ingestion and writer images avoid that layer entirely.

## Items Requiring Member A/B Synchronization

- `Fact`: Topic set, especially whether `audio.dlq` is active now or later.
- `Fact`: Natural key versus physical Timescale constraint strategy.
- `Fact`: Checkpoint semantics and replay behavior.
- `Fact`: Artifact path and manifest conventions.
- `Fact`: Metrics naming/labels used by dashboards.
- `Conflict`: Exact timeline framing for reporting: 8-week condensed plan versus 10-week expanded plan.
