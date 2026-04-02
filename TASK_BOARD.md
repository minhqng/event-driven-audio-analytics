# TASK_BOARD.md

Operational backlog based on the current scaffold and the attached project plans.

## Immediate Next Tasks

1. Lock the canonical event contract.
2. Reconcile root docs, repo schemas/models, SQL, and tests around one agreed contract.
3. Produce a reuse-map from the old data pipeline into `ingestion` and `processing`.
4. Finish the Week 2 smoke path: fake event to writer to TimescaleDB with evidence.
5. Implement real ingestion on a small FMA-small sample.

## Dependency Ordering

1. Contract reconciliation.
2. Reuse-map and test fixtures.
3. Fake-event writer persistence and checkpoint smoke test.
4. Real ingestion artifact path.
5. Real processing path.
6. Real writer path and replay safety.
7. Real Grafana dashboards.
8. Restart/replay hardening.
9. Benchmark/demo/freeze.

## Member B Can Do Independently

- Audit the old data pipeline and classify `reuse now`, `refactor`, and `defer`.
- Prepare sample fixtures: valid track, silent track, short clip, corrupt file if available.
- Implement or document metadata ETL behavior expected from `tracks.csv`.
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
- Gate 2: A fake event can be persisted to TimescaleDB through the writer path.
- Gate 3: `audio.metadata` and `audio.segment.ready` publish from a real FMA-small sample without sending raw PCM through Kafka.
- Gate 4: `audio.features` publishes with correct shape/summary semantics and checksummed artifact loading.
- Gate 5: Replay of the same `run_id` does not inflate persisted feature rows.
- Gate 6: At least 2 Grafana dashboards auto-load and show real data.
- Gate 7: Restart/replay scenarios keep correctness within declared tolerance.
- Gate 8: A 100-track dry run or equivalent demo scenario completes with evidence artifacts.

## Recommended Sequence For Future Codex Sessions

### Session 1

- Resolve contract drift between attached-plan target and repo placeholder implementation.
- Decide whether `audio.dlq` and the richer envelope are immediate scope or staged follow-up.
- Leave `ARCHITECTURE_CONTRACTS.md` and repo schemas aligned.

### Session 2

- Build the fake-event writer smoke path.
- Prove SQL write + checkpoint behavior with lightweight evidence.

### Session 3

- Implement ingestion over a small real sample.
- Lock artifact URI, manifest, checksum, and segment-count behavior.

### Session 4

- Implement processing with old-pipeline parity on RMS, silence gate, log-mel, and Welford semantics.

### Session 5

- Implement real writer consumption, persistence, checkpointing, and replay safety.

### Session 6

- Replace placeholder dashboards with real queries and validate panel meaning.

### Session 7

- Run restart/replay/hardening scenarios and document pass/fail outcomes.

### Session 8

- Run benchmark/demo prep, freeze contracts, and polish docs/evidence.

## Items That Should Not Be Started Yet

- Kubernetes or production HA work.
- Full OTel collector/backend work.
- Model serving or inference services.
- Exact-once experiments before at-least-once plus idempotent sink is stable.
- Dashboard expansion before writer persistence is real.
