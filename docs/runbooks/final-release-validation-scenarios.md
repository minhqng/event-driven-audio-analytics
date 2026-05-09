# Final Release Validation Scenarios

Use this scenario scan before calling the bounded FMA-Small release complete.
It validates the final product shape after dataset-exporter, MinIO claim-check
storage, evaluation evidence, and the K3s deployment variant are present.

Audience: an operator or reviewer validating the thesis-aligned release.

Post-read action: choose the highest-priority scenarios, run the quick
verification steps, and record evidence or failures without expanding scope.

## Boundaries

- Scope is FMA-Small only.
- Do not add new datasets, model training, model serving, or new platform
  features while executing these checks.
- Treat Docker Compose local storage as the deterministic default path.
- Treat MinIO and K3s as bounded private-cloud variants, not production HA.
- Treat evaluation outputs as bounded local evidence, not benchmark-scale
  performance claims.
- Dataset-exporter outputs must come from persisted truth and must not
  fabricate tensor data.

## Scenario Matrix

| ID | Priority | Goal | Setup / Trigger | Expected Behavior | Failure Signal | Quick Verification |
|---|---|---|---|---|---|---|
| S01 | P0 | Prove one exported FMA-Small bundle is complete and schema-valid | Run `dataset-exporter export --run-id <run_id>` after a successful accepted run | Bundle contains manifest, dataset card, quality summary, accepted/rejected CSVs, split Parquet files, split manifest, and stats JSON | Missing `splits/*`, missing `stats/normalization-stats.json`, malformed manifest, or empty files when accepted segments exist | Check `artifacts/datasets/<run_id>/dataset-build-manifest.json` lists every expected relative file |
| S02 | P0 | Ensure accepted tracks and accepted segments are exported only from persisted truth | Use a run with accepted tracks and persisted segment features | `accepted-tracks.csv` matches accepted track metadata; `accepted-segments.csv` has one row per accepted persisted segment | Segment rows exist for rejected tracks, or accepted track counts differ from review/DB summary | Compare exporter counts against `vw_dashboard_run_summary` and review API track/segment counts |
| S03 | P0 | Ensure rejected tracks are represented but excluded from training-oriented split files | Use deterministic demo run containing validation failures | `rejected-tracks.csv` includes rejection reason; rejected tracks have no rows in `splits/train.parquet`, `validation.parquet`, or `test.parquet` | Rejected `track_id` appears in any split Parquet | Query split Parquet `track_id`s and compare against `rejected-tracks.csv` |
| S04 | P0 | Ensure rejected or failed segments are not exported as accepted segment references | Use a run where some segments fail validation/processing or checksum | Rejected segment table records failures; accepted segment outputs contain only valid artifact references | Failed segment appears in `accepted-segments.csv` or training split | Compare rejected segment IDs against accepted segment IDs and split rows |
| S05 | P0 | Detect artifact URI and storage backend mismatch | Persist `s3://...` artifact URIs, then run processing/export with local-only assumptions | Services either dispatch by persisted URI to MinIO or fail fast with a clear backend/config error | Raw path resolution attempt, path traversal acceptance, silent missing audio, or misleading local path in export | Run MinIO smoke; confirm persisted artifact URIs stay `s3://fma-small-artifacts/runs/<run_id>/...` |
| S06 | P0 | Validate local backend backward compatibility | Run deterministic demo with default `STORAGE_BACKEND=local` | Existing local artifact URIs under `/artifacts/runs/<run_id>/...` remain readable by processing, review, and exporter | Default demo fails, media endpoint 404s, or exported references become malformed | Run default demo/export verifier and confirm no MinIO env is required |
| S07 | P0 | Validate MinIO credential failure is explicit | Set wrong `MINIO_ACCESS_KEY` or `MINIO_SECRET_KEY` and run MinIO smoke | Ingestion/processing/review readiness fails with actionable auth/storage error | Hang, partial success, empty artifact manifest, or generic traceback without config context | Run `scripts/smoke/check-minio-claim-check-flow.*` with bad credentials and inspect failure text |
| S08 | P0 | Validate MinIO bucket missing behavior | Run MinIO backend with bucket absent and bucket creation disabled | Writer/reader preflight fails fast, except explicit bucket-init path creates bucket | Review readiness creates bucket implicitly, or ingestion silently writes nowhere | Confirm `MINIO_CREATE_BUCKET=false` for review/K3s shared config; run bucket-init explicitly |
| S09 | P0 | Validate checksum integrity across upload/download | Upload artifact through local and MinIO backends, then process/export | SHA-256 is computed from stored bytes and verified before decoding/export validation | Processing accepts corrupted bytes, exporter validates wrong checksum, or mismatch is ignored | Tamper one object or expected checksum in a controlled fixture and expect failure |
| S10 | P0 | Validate restart/replay idempotency before dataset export | Run restart/replay smoke, then export same run | Replayed messages do not duplicate track/segment rows; exported bundle counts remain stable | Duplicate accepted segments, duplicate writer records, or bundle counts increase after replay | Compare `restart-replay-summary.json`, DB counts, and dataset manifest counts |
| S11 | P0 | Validate dataset-exporter idempotency after replay | Export same run twice after restart/replay | Bundle is replaced atomically; stale files do not survive; stable persisted truth produces stable outputs | Old `splits/normalization-stats.json` survives, duplicate output rows, or manifest checksum drift without DB change | Run export twice and compare bundle file list plus row counts |
| S12 | P0 | Validate review console and dataset output consistency | Use deterministic demo runs and exported bundles | Review API track statuses, segment counts, labels, and artifact URIs match dataset bundle contents | Review shows accepted track but exporter omits it, or dataset includes row not visible in review | Compare `/api/runs/<run_id>/tracks` and `/api/runs/<run_id>/segments` with exported CSV/Parquet |
| S13 | P1 | Validate split manifest semantics | Export run with multiple artists | `split-manifest.json` records split type, counts, label distribution, tensor limitation, and files with checksums | Missing split type, missing tensor limitation, or file counts disagree with Parquet rows | Inspect `splits/split-manifest.json` and count rows in `train/validation/test.parquet` |
| S14 | P1 | Validate artist-aware leakage prevention | Use accepted run with repeated `artist_id` across tracks | Each `artist_id` appears in only one split; all segments inherit their track split | Same artist appears in train and validation/test | Group split Parquet rows by `artist_id` and assert one split per artist |
| S15 | P1 | Validate tiny-run split degradation | Export deterministic demo or tiny FMA burst with too few artists | Empty validation/test splits are allowed and documented; train stats still use train only | Export fails solely because a split is empty, or manifest hides empty split behavior | Inspect split counts and `split_type`/manifest notes |
| S16 | P1 | Validate normalization stats use train split only | Create/export run where validation/test scalar values differ from train | `normalization-stats.json` summarizes only `splits/train.parquet` | Stats include validation/test values or invent tensor stats | Recompute stats from train Parquet and compare JSON |
| S17 | P1 | Validate empty accepted output behavior | Export run with only rejected tracks | Empty accepted/split files are schema-valid; stats status is `not_available` with reason | Export crashes, writes fake values, or omits required files | Run export on validation-failure demo and inspect bundle |
| S18 | P1 | Validate evaluation latency metrics are internally consistent | Run evaluation script on deterministic demo or skipped local FMA scenario | `latency-summary.json` contains scenario status, wall-clock, DB span, artifact read/write, processing, writer stats | Negative durations, missing status, or percentile fields inconsistent with counts | Run `python -m event_driven_audio_analytics.evaluation.collect` and inspect latency JSON |
| S19 | P1 | Validate evaluation throughput metrics use bounded scenario duration | Run `fma-small-burst-5` evaluation | Throughput derives from observed duration and persisted accepted counts | Tracks/minute or segments/minute inconsistent with counts/duration | Recalculate `segments_persisted / duration_s * 60` from JSON |
| S20 | P1 | Validate evaluation skipped scenarios are explicit | Remove or hide local FMA data and run evaluation | FMA burst scenarios are present with `status="skipped"` and clear reason | Scenario silently omitted or reported as passed with zero data | Inspect all five evaluation files under `artifacts/evidence/final-demo/evaluation/` |
| S21 | P1 | Validate resource usage parsing stays bounded | Run evaluation with Docker stats sampling | `resource-usage-summary.json` records sampled containers and CPU/memory summaries without claiming benchmark scale | Missing container summaries, parse failure, or benchmark wording in report | Inspect resource summary and `evaluation-report.md` limitations |
| S22 | P1 | Validate scaling evidence caveat | Run scaling scenario with processing replicas 1, 2, 3 | `scaling-summary.json` records runs and explicitly notes single Kafka partition limitation | Report claims linear scaling or omits partition-bound caveat | Search report for partition limitation and compare replica rows |
| S23 | P0 | Validate K3s base manifests apply independently from one-shot jobs | Run `kubectl kustomize deploy/k8s` or dry-run apply | Base includes namespace/config/platform services only; ingestion/export jobs remain explicit | One-shot jobs run during base apply, or required long-lived services missing | `kubectl kustomize deploy/k8s` and inspect resource kinds |
| S24 | P0 | Validate K3s secrets/config mistakes fail clearly | Apply K3s base without creating real `secrets.yaml` or with wrong MinIO/Postgres secret values | Missing secrets prevent pods from becoming ready; wrong secrets fail readiness/preflight | Pods appear ready but cannot process artifacts or persist DB rows | `kubectl describe pod` and readiness probe logs |
| S25 | P0 | Validate K3s MinIO bucket-init ordering | Start K3s base and wait review before bucket init | Review should not create bucket; bucket-init job must be run before review readiness in MinIO mode | Review mutates MinIO or becomes ready despite missing bucket | Follow runbook order and verify `job/minio-bucket-init` completes before review ready |
| S26 | P1 | Validate K3s Kafka topic bootstrap ordering | Start processing/writer before topic bootstrap | Services fail readiness or log clear Kafka/topic dependency until bootstrap completes | Silent message loss, no DLQ/topic creation, or unclear crash loop | Apply `kafka/topic-bootstrap.yaml` and verify five topics before demo jobs |
| S27 | P1 | Validate K3s demo input preparation | Run deterministic ingestion jobs before `review-demo-input-prep` | Ingestion fails clearly because metadata/audio inputs are missing | Job succeeds with empty or wrong input path | Inspect ingestion job logs and then rerun after prep job |
| S28 | P1 | Validate K3s artifact PVC requirement in MinIO mode | Run K3s with MinIO but without `artifacts-pvc` | Pods requiring demo inputs/state/dataset outputs do not become correctly ready | Dataset/export state disappears or demo prep cannot write inputs | Check processing/review/dataset-exporter mounts and PVC bound state |
| S29 | P1 | Validate operator run-id mistakes are rejected | Use invalid `RUN_ID` with path traversal, spaces, or unexpected characters | Strict run ID validation rejects it before writing artifacts/events | Artifact path/object key escapes run namespace | Trigger ingestion/export with invalid `RUN_ID` and inspect fail-fast error |
| S30 | P1 | Validate operator track-count mistakes remain bounded | Run local FMA burst with unavailable metadata/audio path or excessive `INGESTION_MAX_TRACKS` | Missing local FMA data skips/fails clearly; bounded runs do not expand dataset scope | Generic stack trace, silent zero-track success, or non-FMA data accepted | Run burst script with missing `data/local` and inspect status/error |
| S31 | P2 | Validate Grafana remains corroboration only | Run final demo and inspect report/docs/evidence | Review console and dataset bundles remain primary outputs; Grafana dashboards reflect persisted DB rows | Demo wording or validation treats Grafana as front door/product truth | Review `evidence-index.md`, demo runbook, and dashboard notes |
| S32 | P2 | Validate generated evidence index matches produced artifacts | Run final demo evidence script | `evidence-index.md` references only files that exist or are clearly optional | Broken artifact references or stale filenames | Compare markdown file paths against `artifacts/evidence/final-demo/` |
| S33 | P2 | Validate MinIO endpoint alias precedence | Set canonical and alias env vars consistently, then inconsistently | Canonical/alias mapping works; conflicting values fail fast | Alias silently overrides canonical or ambiguity is accepted | Run storage settings unit path with `MINIO_ENDPOINT_URL`/`MINIO_ENDPOINT` and `MINIO_BUCKET`/`ARTIFACT_BUCKET` |
| S34 | P2 | Validate historical local rows remain readable after MinIO release | Keep old local run in DB/artifacts and set new service default to MinIO | Read paths dispatch by persisted URI family where supported; old local review/export still works | Old local media/export breaks because current default is MinIO | Open review media and export bundle for old local run |
| S35 | P2 | Validate docs do not overclaim final release | Search README/docs/evidence outputs | Docs describe bounded FMA-Small research system, not production HA or benchmark-scale platform | Production-ready, benchmark-scale, generic dataset, or model-training claims appear | `rg "production-ready|benchmark-scale|new datasets|model serving|training"` and inspect context |

## Recommended Execution Order

1. Run P0 local path scenarios first: S01-S06, S10-S12, S23-S26.
2. Run P0 MinIO path scenarios next: S05, S07-S09, S25.
3. Run P1 dataset, evaluation, and K3s hardening: S13-S22, S27-S30.
4. Run P2 narrative and backward-compatibility checks before final report packaging: S31-S35.

## Evidence Notes

- Record the command used, run ID, storage backend, and output path for each
  executed scenario.
- If a scenario is intentionally skipped, record the skip reason. Do not omit it
  from final validation notes.
- Prefer existing smoke scripts, demo scripts, review API checks, dataset bundle
  manifests, evaluation summaries, and K3s runbook commands over ad hoc checks.
