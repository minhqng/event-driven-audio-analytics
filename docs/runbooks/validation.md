# Validation Runbook

Use these checks to validate the repo at the same bounded maturity level claimed by the documentation. Run them from the repository root.

## Tree And Script Presence

```sh
bash ./scripts/smoke/check-tree.sh
```

## Compose Config Sanity

```sh
bash ./scripts/smoke/check-compose.sh
```

## Import And Syntax Sanity

```sh
bash ./scripts/smoke/check-imports.sh
```

## Official Pytest Path

```sh
bash ./scripts/smoke/check-pytest.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1
```

```sh
bash ./scripts/smoke/check-pytest.sh tests/unit/test_processing_runtime.py -q
```

Use the containerized `pytest` path as the authoritative repo test entrypoint. The suite relies on `pytest` fixtures, parametrization, and `raises` assertions, so `unittest discover` is not a complete validation path here.

The `pytest` container runs against image-bundled repo contents rather than a host bind mount, which avoids permission and discovery drift across machines. Use the wrappers above for targeted test files as well so the run stays aligned with the current workspace.

## Writer Smoke Flow

```sh
bash ./scripts/smoke/check-writer-flow.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-writer-flow.ps1
```

This smoke flow verifies all of the following:

- Kafka topics are created, including `audio.dlq`.
- Fake `audio.metadata` and `audio.features` events are published from the container runtime.
- The `writer` persists rows into `track_metadata` and `audio_features`.
- A fake `system.metrics` `scope=run_total` event repairs seeded duplicate rows on the live `system_metrics` Timescale hypertable.
- `run_checkpoints` is updated for the exercised writer topics, including `system.metrics`.
- Replaying the same fake feature event keeps the natural-key row count at `1`.

The smoke flow does **not** prove Kafka offset ordering under failure. Keep that guarantee covered by the writer unit tests around pipeline and commit logic.

## Ingestion Broker Smoke Flow

```sh
bash ./scripts/smoke/check-ingestion-flow.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-ingestion-flow.ps1
```

```sh
sh ./scripts/smoke/observe-topic.sh audio.metadata 5
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\observe-topic.ps1 audio.metadata 5
```

This smoke flow verifies all of the following:

- The `ingestion` service runs inside Compose against a bounded sample set.
- `ingestion preflight` succeeds before the batch run starts.
- Kafka receives real `audio.metadata`, `audio.segment.ready`, and `system.metrics` messages.
- The Python verifier, not the sample topic printout, is the authority for exact current-run message counts by `RUN_ID`, and it derives those expectations from the active metadata/audio input selection.
- `audio.metadata` and `audio.segment.ready` stay keyed by `track_id`.
- `system.metrics` stays keyed by `service_name=ingestion`.
- Any reject-path track stays metadata-only with `validation_status` context preserved in logs; on the committed synthetic fixture set that remains track `666` with `validation_status=probe_failed`.
- Claim-check artifacts are written under the shared `artifacts/` bind mount.
- The run manifest exists under `/artifacts/runs/<run_id>/manifests/segments.parquet` and matches the published `audio.segment.ready` artifact URIs plus checksums.
- Structured ingestion logs expose `trace_id`, `run_id`, and `track_id` for current-run success and reject paths when those paths are present in the selected input set.
- Override `RUN_ID` if needed; the shell and PowerShell wrappers now clean artifacts and validate logs for the current run, not only `demo-run`.
- The default smoke fixtures live under `tests/fixtures/audio/smoke_fma_small/`; reserve `tests/fixtures/audio/tracks.csv` plus `tests/fixtures/audio/fma_small/` for a local non-committed full FMA-small pack.

## Processing Broker Smoke Flow

```sh
bash ./scripts/smoke/check-processing-flow.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-processing-flow.ps1
```

This smoke flow verifies all of the following:

- The `processing` service passes `preflight` before the bounded run starts.
- `processing` stays up as a long-lived Compose consumer while `ingestion` feeds Kafka one-shot.
- Kafka receives real `audio.features` and `processing`-owned `system.metrics` messages for the active `RUN_ID`.
- The Python verifier, not the sample topic printout, is the authority for exact current-run `audio.features`, `processing_ms`, and `silent_ratio` counts.
- `audio.features` stays keyed by `track_id` and keeps the locked `(mel_bins=128, mel_frames=300)` summary shape.
- `system.metrics` stays keyed by `service_name=processing`, with per-segment `processing_ms` labels and `silent_ratio` `run_total` snapshots.
- Healthy smoke runs do not emit `feature_errors`.
- Structured processing logs expose `trace_id`, `run_id`, `track_id`, `segment_idx`, and `silent_flag` for current-run success paths.
- The default wrapper is portable against committed fixtures, while `scripts/demo/run-local-fma-burst.*` targets the repo-local `tests/fixtures/audio/tracks.csv` plus `tests/fixtures/audio/fma_small/` layout for a bounded multi-segment burst.

## Processing To Writer Smoke Flow

```sh
bash ./scripts/smoke/check-processing-writer-flow.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-processing-writer-flow.ps1
```

This smoke flow verifies all of the following:

- `writer` passes `preflight` before the bounded run starts.
- `processing` and `writer` both stay up as long-lived Compose consumers while `ingestion` feeds Kafka one-shot.
- TimescaleDB receives current-run `track_metadata`, `audio_features`, and the processing-owned `system.metrics` emitted on Kafka.
- TimescaleDB also receives the writer-owned direct metrics `write_ms` and `rows_upserted`, while healthy runs keep `write_failures=0`.
- `run_checkpoints` advances for the writer topics exercised by the current run.
- Structured writer logs expose current-run `trace_id` context on healthy persistence paths.

The smoke flow proves healthy-path persistence into TimescaleDB, not broader replay/restart hardening under real producer traffic.

## Restart / Replay Smoke Flow

```sh
bash ./scripts/smoke/check-restart-replay-flow.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-restart-replay-flow.ps1
```

This smoke flow verifies all of the following:

- Kafka and TimescaleDB can start without topic bootstrap while service preflights fail clearly.
- `ingestion`, `processing`, and `writer` all report explicit missing-topic startup failures before bootstrap.
- The same services pass `preflight` after topic bootstrap on the same Compose stack.
- A first bounded broker-backed run can persist `track_metadata`, `audio_features`, and `system_metrics`.
- Restarting long-lived `processing` and `writer` with the same `RUN_ID` keeps `track_metadata`, `audio_features`, and replay-stable `silent_ratio` snapshots stable.
- Append-only `processing_ms`, `write_ms`, and `rows_upserted` counts advance exactly once for the bounded rerun.
- Writer checkpoint offsets advance for the exercised topics.
- Processing restart-recovery state under `artifacts/runs/<run_id>/state/processing_metrics.json` keeps the same logical segment count and `silent_ratio`.
- Evidence artifacts are written under `artifacts/demo/week8/`.

This path is bounded to the committed smoke fixtures. It does not replace larger-run benchmark evidence or DLQ failure-path testing.

## Dashboard Demo Evidence

```sh
bash ./scripts/demo/generate-dashboard-evidence.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-dashboard-evidence.ps1
```

This dashboard-evidence path verifies all of the following:

- `docker compose config` remains valid before the demo run starts.
- the read-only `review` service starts against the same TimescaleDB and `artifacts/` truth as the rest of the stack
- Grafana starts with the file-provisioned TimescaleDB datasource plus the `Audio Quality` and `System Health` dashboards already loaded.
- The bounded Compose-backed run populates TimescaleDB with real dashboard data, not placeholders.
- The deterministic demo pack produces:
  - `week7-high-energy`
  - `week7-silent-oriented`
  - `week7-validation-failure`
- The database-side verifier confirms that:
  - the silent-oriented run has a non-zero `silent_ratio`
  - the energetic run has a higher average RMS than the silent-oriented run
  - the validation-failure run has `validation_status=silent`, zero persisted segments, and non-zero error rate
- Screenshot artifacts are captured under `artifacts/demo/week7/`.
- The review API snapshot and review-console screenshot are captured under `artifacts/demo/week7/`.
- `artifacts/demo/week7/demo-artifact-notes.md` is generated alongside the screenshots so presentation notes stay aligned with the current dashboard panels.

This path is the authoritative dashboard-facing evidence check. It does not replace replay/restart hardening or benchmark-scale validation.

## Final Demo Evidence Bundle

```sh
bash ./scripts/demo/generate-demo-evidence.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-demo-evidence.ps1
```

This path runs the bounded restart/replay smoke and the dashboard evidence script sequentially, then writes `artifacts/demo/week8/evidence-index.md`.

Use it as the final project handoff command when you need:

- fail-fast startup evidence
- bounded same-`run_id` restart/replay evidence
- dashboard screenshots and Grafana provisioning evidence
- one stable index that points to the relevant reliability and dashboard artifact files

## Repo-Local FMA-small Burst

Place the non-committed FMA-small pack at:

- `tests/fixtures/audio/tracks.csv`
- `tests/fixtures/audio/fma_small/...`

Then run:

```sh
bash ./scripts/demo/run-local-fma-burst.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\run-local-fma-burst.ps1
```

This helper expects the stack to already be up through `run-demo.*`, keeps the repo-local path stable across machines, and defaults to a bounded `100`-track burst unless `INGESTION_MAX_TRACKS` is overridden.

## PowerShell Wrapper Reference

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-tree.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-compose.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-imports.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-ingestion-flow.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-processing-flow.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-processing-writer-flow.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\observe-topic.ps1 audio.metadata 5
```

Do not claim full correctness from these checks alone. They validate the bootstrap, the bounded ingestion runtime path, the bounded processing runtime path, the fake-event writer path, and the bounded processing-to-writer persistence path only.
