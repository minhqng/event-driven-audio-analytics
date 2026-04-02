# TASK_BOARD.md

Operational backlog based on the current scaffold and the attached project plans.

## Immediate Next Tasks

1. Freeze the current Week 2 baseline across docs, schemas, SQL, and smoke checks without expanding scope casually.
2. Implement real ingestion on a small FMA-small sample.
3. Implement real processing parity for RMS, silence gate, log-mel summaries, and Welford behavior.
4. Extend evidence from fake-event writer flow to the first real segment-ready path.
5. Replace placeholder dashboard panels with queries backed by persisted data.

## Dependency Ordering

1. Keep the Week 2 shared baseline stable and documented.
2. Real ingestion artifact path.
3. Real processing path.
4. Real writer replay hardening under real producer traffic.
5. Real Grafana dashboards.
6. Restart/replay hardening.
7. Benchmark/demo/freeze.

## Member B Can Do Independently

- Port metadata ETL behavior expected from `tracks.csv` into `ingestion`.
- Port or refactor decode/resample plus segmentation logic from the legacy pipeline into the repo-owned modules.
- Prepare or extend sample fixtures: valid track, silent track, short clip, corrupt file if available.
- Define correctness tolerances against the old pipeline for segment count, log-mel shape, RMS, silence gate, and Welford outputs.
- Write or strengthen unit tests for RMS, silence gate, log-mel shape, checksum validation, and reference comparisons.
- Draft the DSP/reuse/correctness narrative for future report/demo use.

## Tasks Requiring A/B Synchronization

- Final envelope fields and payload names.
- Final topic list, including `audio.dlq`.
- Natural key and idempotency policy for `audio_features`.
- Checkpoint semantics and offset-commit rules.
- Artifact path and manifest format.
- Metric labels/panel semantics for Grafana.
- Any contract or schema change that crosses ingestion, processing, and writer boundaries.

## Gates / Acceptance Checkpoints

- Gate 1: `docker compose config` and infra bootstrap remain clean after any contract or SQL change.
- Gate 2: The current fake `audio.metadata` / `audio.features` writer path remains green, including checkpoint rows and replay-safe feature counts.
- Gate 3: `audio.metadata` and `audio.segment.ready` publish from a real FMA-small sample without sending raw PCM through Kafka.
- Gate 4: `audio.features` publishes with correct shape/summary semantics and checksummed artifact loading.
- Gate 5: Replay of the same `run_id` does not inflate persisted feature rows.
- Gate 6: At least 2 Grafana dashboards auto-load and show real data.
- Gate 7: Restart/replay scenarios keep correctness within declared tolerance.
- Gate 8: A 100-track dry run or equivalent demo scenario completes with evidence artifacts.

## Recommended Sequence For Future Codex Sessions

### Session 1

- Keep `ARCHITECTURE_CONTRACTS.md` and repo schemas aligned while starting real ingestion on a small sample.
- Leave the richer envelope and full DLQ flow as explicit follow-up unless A/B jointly re-scope them.

### Session 2

- Lock artifact URI, manifest, checksum, and segment-count behavior from the first real ingestion pass.

### Session 3

- Implement processing with legacy-pipeline parity on RMS, silence gate, log-mel, and Welford semantics.

### Session 4

- Extend writer verification from fake events to real producer traffic and replay scenarios.

### Session 5

- Replace placeholder dashboards with real queries and validate panel meaning.

### Session 6

- Run restart/replay/hardening scenarios and document pass/fail outcomes.

### Session 7

- Run benchmark/demo prep, freeze contracts, and polish docs/evidence.

### Session 8

- Reserve for integration cleanup, report evidence, or unresolved A/B sync items.

## Items That Should Not Be Started Yet

- Kubernetes or production HA work.
- Full OTel collector/backend work.
- Model serving or inference services.
- Exact-once experiments before at-least-once plus idempotent sink is stable.
- Dashboard expansion before writer persistence is real.
