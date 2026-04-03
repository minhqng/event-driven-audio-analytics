# Lightweight Validation

Use lightweight checks that match the current bounded runtime baseline.
Run them from the repository root.

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

## Minimal Test Hooks

```sh
docker compose run --rm --entrypoint python writer -m unittest discover -s tests -p "test_*.py"
```

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

The smoke flow does **not** prove Kafka offset ordering under failure.
Keep that guarantee covered by unit tests around the writer pipeline and commit logic.

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
- The Python verifier, not the sample topic printout, is the authority for exact current-run message counts by `RUN_ID`.
- `audio.metadata` and `audio.segment.ready` stay keyed by `track_id`.
- `system.metrics` stays keyed by `service_name=ingestion`.
- Reject-path track `666` stays metadata-only with `validation_status=probe_failed`.
- Claim-check artifacts are written under the shared `artifacts/` bind mount.
- The run manifest exists under `/artifacts/runs/<run_id>/manifests/segments.parquet` and matches the published `audio.segment.ready` artifact URIs plus checksums.
- Structured ingestion logs expose `trace_id`, `run_id`, and `track_id` for one success case and one reject case.
- Override `RUN_ID` if needed; the shell and PowerShell wrappers now clean artifacts and validate logs for the current run, not only `demo-run`.

## Legacy PowerShell Wrappers

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-tree.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-compose.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-imports.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-ingestion-flow.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\observe-topic.ps1 audio.metadata 5
```

Do not claim full correctness from these checks alone.
They validate the bootstrap, the bounded Week 4 ingestion runtime path, and the first writer persistence path only.
