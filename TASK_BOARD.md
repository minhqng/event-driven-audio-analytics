# TASK_BOARD.md

Operational backlog based on the current scaffold and the attached project plans.

## Week 8 Status

### Done

- Bounded restart/replay hardening for the current Compose path.
- Fail-fast startup evidence before Kafka topic bootstrap for `ingestion`, `processing`, and `writer`.
- Graceful `SIGTERM` / `SIGINT` shutdown for the long-lived `processing` and `writer` consumers so Compose restart/replay is practical.
- Combined Week 8 evidence wrapper under `scripts/demo/generate-week8-evidence.*`.
- Final-facing runbook cleanup in `README.md`, `docs/runbooks/`, and `docs/architecture/dashboard-interpretation.md`.

### Verified

- `docker compose config`
- the official containerized `pytest` path via `scripts/smoke/check-pytest.ps1` (`176 passed, 5 skipped`)
- host-side targeted `pytest` coverage for the Week 8 follow-up guardrails in `tests/unit/test_restart_replay_smoke_verify.py` and `tests/unit/test_shutdown.py`

### Partially Verified

- Existing Week 6/7/8 smoke and demo wrappers remain the bounded evidence entrypoints, but `scripts/smoke/check-processing-writer-flow.*`, `scripts/smoke/check-restart-replay-flow.*`, `scripts/demo/generate-week7-dashboard-evidence.*`, and `scripts/demo/generate-week8-evidence.*` were not rerun in this follow-up patch set.
- Same-`run_id` replay is verified on the committed bounded smoke fixtures, not on a larger local FMA burst.
- Dashboard validity is verified on the deterministic Week 7 demo runs, not on benchmark-scale traffic.
- Failure-path restart behavior is verified for missing-topic startup dependency failures; a real DLQ flow is still absent.

### Deferred To Week 9/10

- 100-track burst / benchmark evidence
- broader benchmark-scale replay/restart behavior
- real DLQ implementation and schema/model coverage
- persisted `welford_snapshots`

Week 7 dashboard note:
- The deterministic dashboard evidence remains under `artifacts/demo/week7/`.
- The final Week 8 handoff anchor is `artifacts/demo/week8/evidence-index.md`.

## Dependency Ordering

1. Keep the locked v1 contract stable under future runtime work.
   Current writer persistence now stores canonical `audio.metadata.duration_s` and optional `system.metrics.unit`; keep those fields stable unless A/B re-scope the contract.
2. Keep the per-service image extras and official containerized `pytest` path green while extending runtime evidence.
3. Benchmark/demo/freeze beyond the current bounded Week 8 evidence.

## Member B Can Do Independently

- Port metadata ETL behavior expected from `tracks.csv` into `ingestion`.
- Port or refactor decode/resample plus segmentation logic from the legacy pipeline into the repo-owned modules.
- Prepare or extend sample fixtures: valid track, silent track, short clip, corrupt file if available.
- Define correctness tolerances against the old pipeline for segment count, log-mel shape, RMS, silence gate, and Welford outputs.
- Write or strengthen unit tests for RMS, silence gate, log-mel shape, checksum validation, and reference comparisons.
- Draft the DSP/reuse/correctness narrative for future report/demo use.

## Tasks Requiring A/B Synchronization

- Final topic list, including `audio.dlq`.
- Natural key and idempotency policy for `audio_features`.
- Checkpoint semantics and offset-commit rules.
- Artifact path and manifest format.
- Metric labels/panel semantics for Grafana.
- Any contract or schema change that crosses ingestion, processing, and writer boundaries.

## Gates / Acceptance Checkpoints

- Gate 1: `docker compose config` and infra bootstrap remain clean after any contract or SQL change.
- Gate 2: The canonical v1 fake `audio.metadata` / `audio.features` writer path remains green, including checkpoint rows and replay-safe feature counts.
- Gate 3: `audio.metadata` and `audio.segment.ready` publish from a real FMA-small sample without sending raw PCM through Kafka.
  Current status: Member B-owned code path is green with a recording producer plus real local FMA tracks `2` and `666`. Member A-owned Compose smoke now proves one-shot `ingestion preflight`, startup gating with run-scoped artifact-target probing, broker-backed publication, exact current-run counts by `RUN_ID`, reject-path metadata-only behavior for track `666`, run-manifest verification, and structured success/reject logs on a bounded committed fixture set.
- Gate 4: `audio.features` publishes with correct shape/summary semantics and checksummed artifact loading.
  Current status: Member B Week 5 unit coverage now proves claim-check artifact loading, checksum gating, RMS summary emission, inherited silence decisions, exact `(1,128,300)` log-mel enforcement, vector Welford updates, and canonical `audio.features` envelopes on tone, silent, short-clip, and ingestion-produced artifacts. Member B Week 6 reference validation now also checks the real processing path against the legacy transform on local FMA tracks `2`, `140`, `148`, `666`, and `1482`, with exact segment counts, exact `silent_flag` decisions, tolerance-level RMS/log-mel parity, and a documented summary-first `audio.features` mapping with no active `feature_uri` in v1. Member A Week 5 runtime work now adds a long-lived `processing` consumer with `preflight`, bounded artifact retry, structured logs, `processing_ms` plus `silent_ratio` publication, replay-stable `silent_ratio` recovery under `/artifacts/runs/<run_id>/state/processing_metrics.json`, and non-commit exit behavior on terminal failures without poison-record auto-restart loops. The bounded broker-backed `ingestion -> Kafka -> processing` smoke path is green on a clean `RUN_ID` without healthy-path `feature_errors`, and the bounded Week 6 broker-backed `ingestion -> processing -> writer -> TimescaleDB` smoke path now proves that current-run `audio.features` and `system.metrics` reach persistence.
- Gate 5: Replay of the same `run_id` does not inflate persisted feature rows.
  Current status: fake `audio.features` rows and `scope=run_total` `system.metrics` rows now have replay-safe shared identities plus replay-safe sink behavior on the current writer path, including chunk-aware duplicate repair plus `ts` refresh for `run_total` snapshots, and the writer smoke now proves that repair on a live Timescale hypertable. The bounded Week 8 restart/replay smoke now also proves same-`run_id` replay after restarting `processing` and `writer`, including stable `track_metadata` / `audio_features`, replay-stable `silent_ratio`, checkpoint advancement, and stable processing recovery state on the committed smoke fixtures.
- Gate 6: At least 2 Grafana dashboards auto-load and show real data.
  Current status: Week 7 is green. Grafana now auto-loads the provisioned TimescaleDB datasource plus the `Audio Quality` and `System Health` dashboards, `vw_dashboard_*` views keep the panel SQL stable, and `scripts/demo/generate-week7-dashboard-evidence.ps1` verifies the three deterministic demo runs plus screenshot capture under `artifacts/demo/week7/`. Week 7.5 now adds the dedicated intermediate-demo runbook, clearer dashboard naming, and generated screenshot notes without expanding into Week 8 hardening scope.
- Gate 7: Restart/replay scenarios keep correctness within declared tolerance.
  Current status: bounded Week 8 restart/replay evidence is in place. The dedicated restart/replay smoke path proves missing-topic fail-fast preflights, healthy post-bootstrap preflights, same-`run_id` replay after restarting `processing` and `writer`, checkpoint advancement, replay-stable `track_metadata` / `audio_features`, replay-stable `silent_ratio`, and stable processing recovery state under `artifacts/runs/<run_id>/state/processing_metrics.json`.
- Gate 8: A 100-track dry run or equivalent demo scenario completes with evidence artifacts.
  Current status: partially verified only. The deterministic dashboard demo and final Week 8 evidence bundle are green, but the repo-local 100-track burst remains intentionally deferred.

## Recommended Sequence For Future Codex Sessions

### Session 1

- Keep `ARCHITECTURE_CONTRACTS.md` and repo schemas aligned while starting real ingestion on a small sample.
- Leave the full DLQ flow as explicit follow-up unless A/B jointly re-scope it; current Week 4 ingestion runtime should stay on explicit structured-error logging only.

### Session 2

- Lock artifact URI, manifest, checksum, and segment-count behavior from the first real ingestion pass.

### Session 3

- Use the now-implemented processing path to collect broker-backed evidence from `audio.segment.ready` through writer persistence on real `audio.features` traffic.
- Keep the Week 5 and Week 6 smoke harnesses green while extending the evidence from Kafka outputs into replay and dashboard work.

### Session 4

- Extend writer verification from the new healthy-path broker smoke into replay scenarios and dashboard-backed queries.

### Session 5

- Extend the now-real dashboards only if replay/restart evidence requires additional panels or run-summary fields.

### Session 6

- Reserve for benchmark-scale evidence or the repo-local 100-track burst only if needed for later reporting.

### Session 7

- Reserve for final report packaging, screenshots, or unresolved A/B sync items.

### Session 8

- Reserve for only those deferred items that still fit the locked PoC scope.

## Items That Should Not Be Started Yet

- Kubernetes or production HA work.
- Full OTel collector/backend work.
- Model serving or inference services.
- Exact-once experiments before at-least-once plus idempotent sink is stable.
- Dashboard expansion before writer persistence is real.
