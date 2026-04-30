# Validation Runbook

Run commands from the repository root.

## Prompt Guardrails

Apply these scope rules before running follow-on implementation, validation, or
demo prompts.

### Target End State

- Lift the current repo from an event-driven audio pipeline plus review/Grafana
  evidence into a bounded event-driven FMA-Small audio analytics system.
- The target state must end with reusable FMA-Small dataset/analytics outputs,
  an object-storage-backed claim-check path, evaluation evidence, and a bounded
  private-cloud deployment variant.

### Invariants To Keep

- Preserve the `ingestion -> processing -> writer -> review/Grafana` shape.
- Kafka remains small-event transport only.
- Audio artifacts cross service boundaries through claim-check only.
- The review console remains read-only.
- Grafana remains corroboration, not the front door.
- Keep the topic centered on FMA-Small only.
- Do not expand scope to other datasets.
- Do not claim fully production-ready completeness.
- Do not add training or model serving unless that is explicitly scoped.

### Required Additions In Scope

- Final FMA-Small dataset/analytics outputs that downstream steps can consume.
- MinIO or another S3-compatible object-storage backend for claim-check
  artifacts.
- An evaluation framework and evidence path specific to FMA-Small.
- A bounded K3s/Kubernetes deployment variant for private-cloud demonstration.
- Final docs and demo story aligned with the FMA-Small title and boundaries.

## Fast Local Checks

```powershell
docker compose config
python -m compileall -q src tests
python -m pytest tests/unit/test_prepare_review_demo_inputs.py tests/unit/test_verify_review_api.py tests/unit/test_restart_replay_smoke_verify.py tests/unit/test_dataset_exporter.py tests/unit/test_dataset_demo_output_verify.py -q --basetemp .pytest_cache/productization-tests
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

This produces the deterministic review runs and supporting Grafana evidence without the restart/replay wrapper or the dataset-export step.

## Full Final Demo Evidence

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-demo-evidence.ps1
```

Bash:

```sh
bash ./scripts/demo/generate-demo-evidence.sh
```

This is the full bounded evidence path. It keeps the review/Grafana story,
keeps restart/replay evidence, and also exports and verifies the deterministic
FMA-Small dataset bundles for the demo runs.

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

## Dataset Export Verification

After a run has persisted metadata and features, export the final dataset bundle:

```powershell
docker compose run --rm dataset-exporter export --run-id fma-small-live
```

```sh
docker compose run --rm dataset-exporter export --run-id fma-small-live
```

The output is written under `artifacts/datasets/<run_id>/`. It is generated from
TimescaleDB persisted truth plus claim-check artifact metadata and does not mutate
writer, review, Kafka, or the original `artifacts/runs/<run_id>/` state.

Expected training-oriented split outputs live under `artifacts/datasets/<run_id>/splits/`:

- `split-manifest.json`
- `train.parquet`
- `validation.parquet`
- `test.parquet`

Expected normalization output lives under `artifacts/datasets/<run_id>/stats/`:

- `normalization-stats.json`

These files contain FMA-Small metadata, labels, artifact references, and scalar
summaries only. They do not contain log-mel tensors.
