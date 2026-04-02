# Lightweight Validation

Use lightweight checks that match the current Week 2 baseline.
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
- `run_checkpoints` is updated for the exercised writer topics.
- Replaying the same fake feature event keeps the natural-key row count at `1`.

The smoke flow does **not** prove Kafka offset ordering under failure.
Keep that guarantee covered by unit tests around the writer pipeline and commit logic.

## Legacy PowerShell Wrappers

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-tree.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-compose.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-imports.ps1
```

Do not claim full correctness from these checks alone.
They validate the bootstrap, shared layer, and first writer persistence path only.
