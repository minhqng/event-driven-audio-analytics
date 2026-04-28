# Validation Runbook

Run commands from the repository root.

## Fast Local Checks

```powershell
docker compose config
python -m compileall -q src tests
python -m pytest tests/unit/test_prepare_review_demo_inputs.py tests/unit/test_verify_review_api.py tests/unit/test_restart_replay_smoke_verify.py -q --basetemp .pytest_cache/productization-tests
```

## Official Test Path

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1
```

Bash:

```sh
bash ./scripts/smoke/check-pytest.sh
```

The containerized path is the authoritative test entrypoint because it runs against image-bundled repo contents and avoids host dependency drift.

## Targeted Smoke Paths

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-ingestion-flow.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-processing-flow.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-processing-writer-flow.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-restart-replay-flow.ps1
```

Bash:

```sh
bash ./scripts/smoke/check-ingestion-flow.sh
bash ./scripts/smoke/check-processing-flow.sh
bash ./scripts/smoke/check-processing-writer-flow.sh
bash ./scripts/smoke/check-restart-replay-flow.sh
```

## Review/Dashboard Evidence Only

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-dashboard-evidence.ps1
```

Bash:

```sh
bash ./scripts/demo/generate-dashboard-evidence.sh
```

This produces the deterministic review runs and supporting Grafana evidence without the restart/replay wrapper.

## Local FMA-small Burst

Place local data under:

```text
data/local/fma_metadata/tracks.csv
data/local/fma_small/<prefix>/<track_id>.mp3
```

Then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\run-local-fma-burst.ps1
```

or:

```sh
bash ./scripts/demo/run-local-fma-burst.sh
```

The local burst is operator-supplied runtime input and is not committed evidence.
