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
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-minio-claim-check-flow.ps1
```

Bash:

```sh
bash ./scripts/smoke/check-ingestion-flow.sh
bash ./scripts/smoke/check-processing-flow.sh
bash ./scripts/smoke/check-processing-writer-flow.sh
bash ./scripts/smoke/check-restart-replay-flow.sh
bash ./scripts/smoke/check-minio-claim-check-flow.sh
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

## Bounded Evaluation Evidence

Phase 6 evaluation evidence is generated separately from the front-door demo so
the demo remains deterministic and each evaluation scenario can be marked as a
bounded local measurement.

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\evaluation\run-evaluation.ps1
```

Bash:

```sh
bash ./scripts/evaluation/run-evaluation.sh
```

Expected outputs:

- `artifacts/evidence/final-demo/evaluation/latency-summary.json`
- `artifacts/evidence/final-demo/evaluation/throughput-summary.json`
- `artifacts/evidence/final-demo/evaluation/resource-usage-summary.json`
- `artifacts/evidence/final-demo/evaluation/scaling-summary.json`
- `artifacts/evidence/final-demo/evaluation/evaluation-report.md`

The evaluator uses persisted TimescaleDB truth, checksum-verified claim-check
artifact reads, script wall-clock timing, and bounded `docker stats` samples. It
does not claim benchmark-scale or production performance.

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

## MinIO Claim-Check Variant

Local filesystem claim-check remains the default:

```powershell
$env:STORAGE_BACKEND="local"
```

Canonical MinIO env names are:

- `MINIO_ENDPOINT_URL`
- `MINIO_BUCKET`

If `MINIO_ENDPOINT_URL` is left unset, the services derive the default endpoint
from `MINIO_SECURE`: `http://minio:9000` when false, `https://minio:9000` when
true.

Prompt-compatible aliases are also accepted:

- `MINIO_ENDPOINT` -> `MINIO_ENDPOINT_URL`
- `ARTIFACT_BUCKET` -> `MINIO_BUCKET`

If both the canonical name and alias are set, they must match exactly.

For the bounded private-cloud variant, set the MinIO backend and initialize the bucket:

```powershell
$env:STORAGE_BACKEND="minio"
$env:MINIO_CREATE_BUCKET="true"
$env:MINIO_ENDPOINT_URL="http://minio:9000"
$env:MINIO_BUCKET="fma-small-artifacts"
docker compose up -d minio minio-init
```

```sh
export STORAGE_BACKEND=minio
export MINIO_CREATE_BUCKET=true
export MINIO_ENDPOINT_URL=http://minio:9000
export MINIO_BUCKET=fma-small-artifacts
docker compose up -d minio minio-init
```

The official bounded MinIO smoke/evidence path is:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-minio-claim-check-flow.ps1
```

```sh
bash ./scripts/smoke/check-minio-claim-check-flow.sh
```

This starts Kafka, TimescaleDB, MinIO, processing, writer, and review; runs a bounded ingestion flow; exports the dataset bundle; and writes a verification summary under:

```text
artifacts/evidence/minio-claim-check/<run_id>-summary.json
```

MinIO-backed claim-check artifact URIs use:

```text
s3://fma-small-artifacts/runs/<run_id>/segments/<track_id>/<segment_idx>.wav
s3://fma-small-artifacts/runs/<run_id>/manifests/segments.parquet
```

Existing local runs with `/artifacts/runs/...` URIs remain readable with
`STORAGE_BACKEND=local`. Do not mix backends inside one persisted run.

If `processing` stays on `STORAGE_BACKEND=local` but you expect it to replay
historical `s3://...` claim-check events, also set:

```powershell
$env:PROCESSING_PROBE_S3_REPLAY_READINESS="true"
```

```sh
export PROCESSING_PROBE_S3_REPLAY_READINESS=true
```

This keeps the default local demo independent from MinIO, but makes processing
preflight fail fast when S3 replay support is expected and the MinIO backend is
not reachable.
