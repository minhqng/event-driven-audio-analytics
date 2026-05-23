# Codebase Map

Generated: 2026-05-23T10:14:00Z | Files: 297 | Described: 0/297
<!-- gsd:codebase-meta {"generatedAt":"2026-05-23T10:14:00Z","fingerprint":"2ff0b15b14d1fc0d4d84a02d6f1e3eff0b0e515a","fileCount":297,"truncated":false} -->

### (root)/
- `.dockerignore`
- `.env.example`
- `.gitattributes`
- `.gitignore`
- `docker-compose.yml`
- `LICENSE`
- `pyproject.toml`
- `README.md`
- `run-demo.ps1`
- `run-demo.sh`

### .gsd.migrating/
- `.gsd.migrating/gsd.db`
- `.gsd.migrating/gsd.db-shm`
- `.gsd.migrating/gsd.db-wal`
- `.gsd.migrating/notifications.jsonl`

### .gsd.migrating/runtime/
- `.gsd.migrating/runtime/write-gate-state.json`

### artifacts/
- `artifacts/README.md`

### artifacts/evidence/final-demo/
- `artifacts/evidence/final-demo/evidence-index.md`

### artifacts/evidence/final-demo/dataset-exports/
- `artifacts/evidence/final-demo/dataset-exports/dataset-export-summary.json`

### artifacts/evidence/final-demo/evaluation/
- `artifacts/evidence/final-demo/evaluation/evaluation-report.md`
- `artifacts/evidence/final-demo/evaluation/latency-summary.json`
- `artifacts/evidence/final-demo/evaluation/resource-usage-summary.json`
- `artifacts/evidence/final-demo/evaluation/scaling-summary.json`
- `artifacts/evidence/final-demo/evaluation/throughput-summary.json`

### artifacts/evidence/final-demo/evaluation/resource-samples/
- `artifacts/evidence/final-demo/evaluation/resource-samples/eval-deterministic-review-demo.jsonl`
- `artifacts/evidence/final-demo/evaluation/resource-samples/eval-fma-100.jsonl`
- `artifacts/evidence/final-demo/evaluation/resource-samples/eval-fma-5.jsonl`
- `artifacts/evidence/final-demo/evaluation/resource-samples/eval-scale-r1.jsonl`
- `artifacts/evidence/final-demo/evaluation/resource-samples/eval-scale-r2.jsonl`
- `artifacts/evidence/final-demo/evaluation/resource-samples/eval-scale-r3.jsonl`

### artifacts/evidence/final-demo/restart-replay/
- `artifacts/evidence/final-demo/restart-replay/preflight-fail-fast.txt`
- `artifacts/evidence/final-demo/restart-replay/restart-replay-baseline.json`
- `artifacts/evidence/final-demo/restart-replay/restart-replay-summary.json`

### artifacts/evidence/final-demo/review-dashboard/
- `artifacts/evidence/final-demo/review-dashboard/grafana-api.json`
- `artifacts/evidence/final-demo/review-dashboard/review-api.json`
- `artifacts/evidence/final-demo/review-dashboard/review-dashboard-notes.md`
- `artifacts/evidence/final-demo/review-dashboard/review-dashboard-summary.json`

### artifacts/evidence/minio-claim-check/
- `artifacts/evidence/minio-claim-check/minio-smoke-summary.json`

### artifacts/runs/
- `artifacts/runs/.gitkeep`

### artifacts/shared/
- `artifacts/shared/.gitkeep`

### data/
- `data/README.md`

### deploy/k3s/
- `deploy/k3s/artifacts-pvc.yaml`
- `deploy/k3s/configmap.yaml`
- `deploy/k3s/kustomization.yaml`
- `deploy/k3s/namespace.yaml`
- `deploy/k3s/README.md`
- `deploy/k3s/secrets.example.yaml`

### deploy/k3s/dataset-exporter/
- `deploy/k3s/dataset-exporter/demo-high-energy.yaml`
- `deploy/k3s/dataset-exporter/demo-silent-oriented.yaml`
- `deploy/k3s/dataset-exporter/demo-validation-failure.yaml`
- `deploy/k3s/dataset-exporter/fma-small-live.yaml`

### deploy/k3s/grafana/
- `deploy/k3s/grafana/deployment.yaml`
- `deploy/k3s/grafana/service.yaml`

### deploy/k3s/grafana/config/dashboards/
- `deploy/k3s/grafana/config/dashboards/audio_quality.json`
- `deploy/k3s/grafana/config/dashboards/system_health.json`

### deploy/k3s/grafana/config/provisioning/dashboards/
- `deploy/k3s/grafana/config/provisioning/dashboards/dashboards.yaml`

### deploy/k3s/grafana/config/provisioning/datasources/
- `deploy/k3s/grafana/config/provisioning/datasources/timescaledb.yaml`

### deploy/k3s/ingestion/
- `deploy/k3s/ingestion/demo-high-energy.yaml`
- `deploy/k3s/ingestion/demo-silent-oriented.yaml`
- `deploy/k3s/ingestion/demo-validation-failure.yaml`
- `deploy/k3s/ingestion/fma-burst-100.yaml`
- `deploy/k3s/ingestion/fma-burst-5.yaml`
- `deploy/k3s/ingestion/fma-input-pvc.yaml`
- `deploy/k3s/ingestion/review-demo-input-prep.yaml`

### deploy/k3s/kafka/
- `deploy/k3s/kafka/headless-service.yaml`
- `deploy/k3s/kafka/service.yaml`
- `deploy/k3s/kafka/statefulset.yaml`
- `deploy/k3s/kafka/topic-bootstrap.yaml`

### deploy/k3s/minio/
- `deploy/k3s/minio/bucket-init.yaml`
- `deploy/k3s/minio/pvc.yaml`
- `deploy/k3s/minio/service.yaml`
- `deploy/k3s/minio/statefulset.yaml`

### deploy/k3s/processing/
- `deploy/k3s/processing/deployment.yaml`

### deploy/k3s/review/
- `deploy/k3s/review/deployment.yaml`
- `deploy/k3s/review/service.yaml`

### deploy/k3s/timescaledb/
- `deploy/k3s/timescaledb/pvc.yaml`
- `deploy/k3s/timescaledb/service.yaml`
- `deploy/k3s/timescaledb/statefulset.yaml`

### deploy/k3s/timescaledb/config/
- `deploy/k3s/timescaledb/config/001_extensions.sql`
- `deploy/k3s/timescaledb/config/002_core_tables.sql`
- `deploy/k3s/timescaledb/config/003_operational_views.sql`
- `deploy/k3s/timescaledb/config/004_review_views.sql`

### deploy/k3s/writer/
- `deploy/k3s/writer/deployment.yaml`

### docs/
- `docs/README.md`

### docs/architecture/
- `docs/architecture/system-overview.md`

### docs/runbooks/
- `docs/runbooks/demo.md`
- `docs/runbooks/final-release-validation-scenarios.md`
- `docs/runbooks/k3s.md`
- `docs/runbooks/validation.md`

### infra/grafana/dashboards/
- `infra/grafana/dashboards/audio_quality.json`
- `infra/grafana/dashboards/system_health.json`

### infra/grafana/provisioning/dashboards/
- `infra/grafana/provisioning/dashboards/dashboards.yaml`

### infra/grafana/provisioning/datasources/
- `infra/grafana/provisioning/datasources/timescaledb.yaml`

### infra/kafka/
- `infra/kafka/create-topics.ps1`
- `infra/kafka/create-topics.sh`

### infra/sql/
- `infra/sql/001_extensions.sql`
- `infra/sql/002_core_tables.sql`
- `infra/sql/003_operational_views.sql`
- `infra/sql/004_review_views.sql`

### references/
- `references/.gitkeep`

### schemas/
- `schemas/envelope.v1.json`

### schemas/events/
- `schemas/events/audio.features.v1.json`
- `schemas/events/audio.metadata.v1.json`
- `schemas/events/audio.segment.ready.v1.json`
- `schemas/events/system.metrics.v1.json`

### scripts/demo/
- `scripts/demo/generate-dashboard-evidence.ps1`
- `scripts/demo/generate-dashboard-evidence.sh`
- `scripts/demo/generate-demo-evidence.ps1`
- `scripts/demo/generate-demo-evidence.sh`
- `scripts/demo/run-local-fma-burst.ps1`
- `scripts/demo/run-local-fma-burst.sh`

### scripts/evaluation/
- `scripts/evaluation/run-evaluation.ps1`
- `scripts/evaluation/run-evaluation.sh`

### scripts/smoke/
- *(22 files: 11 .ps1, 11 .sh)*

### services/dataset-exporter/
- `services/dataset-exporter/Dockerfile`

### services/ingestion/
- `services/ingestion/Dockerfile`
- `services/ingestion/entrypoint.sh`

### services/processing/
- `services/processing/Dockerfile`
- `services/processing/entrypoint.sh`

### services/pytest/
- `services/pytest/Dockerfile`
- `services/pytest/Dockerfile.dockerignore`

### services/review/
- `services/review/Dockerfile`
- `services/review/entrypoint.sh`

### services/writer/
- `services/writer/Dockerfile`
- `services/writer/entrypoint.sh`

### src/event_driven_audio_analytics/
- `src/event_driven_audio_analytics/__init__.py`

### src/event_driven_audio_analytics/dataset_exporter/
- `src/event_driven_audio_analytics/dataset_exporter/__init__.py`
- `src/event_driven_audio_analytics/dataset_exporter/app.py`
- `src/event_driven_audio_analytics/dataset_exporter/config.py`
- `src/event_driven_audio_analytics/dataset_exporter/exporter.py`

### src/event_driven_audio_analytics/evaluation/
- `src/event_driven_audio_analytics/evaluation/__init__.py`
- `src/event_driven_audio_analytics/evaluation/collect.py`
- `src/event_driven_audio_analytics/evaluation/report.py`
- `src/event_driven_audio_analytics/evaluation/resources.py`
- `src/event_driven_audio_analytics/evaluation/stats.py`

### src/event_driven_audio_analytics/ingestion/
- `src/event_driven_audio_analytics/ingestion/__init__.py`
- `src/event_driven_audio_analytics/ingestion/app.py`
- `src/event_driven_audio_analytics/ingestion/config.py`
- `src/event_driven_audio_analytics/ingestion/pipeline.py`

### src/event_driven_audio_analytics/ingestion/modules/
- `src/event_driven_audio_analytics/ingestion/modules/__init__.py`
- `src/event_driven_audio_analytics/ingestion/modules/artifact_writer.py`
- `src/event_driven_audio_analytics/ingestion/modules/audio_validator.py`
- `src/event_driven_audio_analytics/ingestion/modules/metadata_loader.py`
- `src/event_driven_audio_analytics/ingestion/modules/metrics.py`
- `src/event_driven_audio_analytics/ingestion/modules/publisher.py`
- `src/event_driven_audio_analytics/ingestion/modules/runtime.py`
- `src/event_driven_audio_analytics/ingestion/modules/segmenter.py`

### src/event_driven_audio_analytics/processing/
- `src/event_driven_audio_analytics/processing/__init__.py`
- `src/event_driven_audio_analytics/processing/app.py`
- `src/event_driven_audio_analytics/processing/config.py`
- `src/event_driven_audio_analytics/processing/pipeline.py`

### src/event_driven_audio_analytics/processing/modules/
- `src/event_driven_audio_analytics/processing/modules/__init__.py`
- `src/event_driven_audio_analytics/processing/modules/artifact_loader.py`
- `src/event_driven_audio_analytics/processing/modules/log_mel.py`
- `src/event_driven_audio_analytics/processing/modules/metrics.py`
- `src/event_driven_audio_analytics/processing/modules/publisher.py`
- `src/event_driven_audio_analytics/processing/modules/rms.py`
- `src/event_driven_audio_analytics/processing/modules/runtime.py`
- `src/event_driven_audio_analytics/processing/modules/silence_gate.py`
- `src/event_driven_audio_analytics/processing/modules/welford.py`

### src/event_driven_audio_analytics/review/
- `src/event_driven_audio_analytics/review/__init__.py`
- `src/event_driven_audio_analytics/review/app.py`
- `src/event_driven_audio_analytics/review/config.py`
- `src/event_driven_audio_analytics/review/queries.py`
- `src/event_driven_audio_analytics/review/runtime.py`
- `src/event_driven_audio_analytics/review/schemas.py`

### src/event_driven_audio_analytics/review/static/
- `src/event_driven_audio_analytics/review/static/app.js`
- `src/event_driven_audio_analytics/review/static/index.html`
- `src/event_driven_audio_analytics/review/static/styles.css`

### src/event_driven_audio_analytics/shared/
- `src/event_driven_audio_analytics/shared/__init__.py`
- `src/event_driven_audio_analytics/shared/audio.py`
- `src/event_driven_audio_analytics/shared/checksum.py`
- `src/event_driven_audio_analytics/shared/db.py`
- `src/event_driven_audio_analytics/shared/ids.py`
- `src/event_driven_audio_analytics/shared/kafka.py`
- `src/event_driven_audio_analytics/shared/logging.py`
- `src/event_driven_audio_analytics/shared/metric_labels.py`
- `src/event_driven_audio_analytics/shared/settings.py`
- `src/event_driven_audio_analytics/shared/shutdown.py`
- `src/event_driven_audio_analytics/shared/storage.py`

### src/event_driven_audio_analytics/shared/contracts/
- `src/event_driven_audio_analytics/shared/contracts/__init__.py`
- `src/event_driven_audio_analytics/shared/contracts/topics.py`

### src/event_driven_audio_analytics/shared/models/
- `src/event_driven_audio_analytics/shared/models/__init__.py`
- `src/event_driven_audio_analytics/shared/models/audio_features.py`
- `src/event_driven_audio_analytics/shared/models/audio_metadata.py`
- `src/event_driven_audio_analytics/shared/models/audio_segment_ready.py`
- `src/event_driven_audio_analytics/shared/models/envelope.py`
- `src/event_driven_audio_analytics/shared/models/payload_validation.py`
- `src/event_driven_audio_analytics/shared/models/system_metrics.py`

### src/event_driven_audio_analytics/smoke/
- `src/event_driven_audio_analytics/smoke/__init__.py`
- `src/event_driven_audio_analytics/smoke/prepare_review_demo_inputs.py`
- `src/event_driven_audio_analytics/smoke/publish_fake_events.py`
- `src/event_driven_audio_analytics/smoke/verify_dashboard_demo.py`
- `src/event_driven_audio_analytics/smoke/verify_dataset_demo_outputs.py`
- `src/event_driven_audio_analytics/smoke/verify_ingestion_flow.py`
- `src/event_driven_audio_analytics/smoke/verify_minio_claim_check_flow.py`
- `src/event_driven_audio_analytics/smoke/verify_processing_flow.py`
- `src/event_driven_audio_analytics/smoke/verify_restart_replay_flow.py`
- `src/event_driven_audio_analytics/smoke/verify_review_api.py`
- `src/event_driven_audio_analytics/smoke/verify_writer_flow.py`

### src/event_driven_audio_analytics/writer/
- `src/event_driven_audio_analytics/writer/__init__.py`
- `src/event_driven_audio_analytics/writer/app.py`
- `src/event_driven_audio_analytics/writer/config.py`
- `src/event_driven_audio_analytics/writer/pipeline.py`

### src/event_driven_audio_analytics/writer/modules/
- `src/event_driven_audio_analytics/writer/modules/__init__.py`
- `src/event_driven_audio_analytics/writer/modules/checkpoint_store.py`
- `src/event_driven_audio_analytics/writer/modules/consumer.py`
- `src/event_driven_audio_analytics/writer/modules/metrics.py`
- `src/event_driven_audio_analytics/writer/modules/offset_manager.py`
- `src/event_driven_audio_analytics/writer/modules/persistence.py`
- `src/event_driven_audio_analytics/writer/modules/runtime.py`
- `src/event_driven_audio_analytics/writer/modules/upsert_features.py`
- `src/event_driven_audio_analytics/writer/modules/upsert_metadata.py`
- `src/event_driven_audio_analytics/writer/modules/write_metrics.py`

### tests/
- `tests/__init__.py`

### tests/fixtures/audio/
- `tests/fixtures/audio/corrupt_audio.mp3`
- `tests/fixtures/audio/fixture_manifest.json`
- `tests/fixtures/audio/README.md`
- `tests/fixtures/audio/short_tone_mono_32k.wav`
- `tests/fixtures/audio/silent_mono_32k.wav`
- `tests/fixtures/audio/smoke_tracks.csv`
- `tests/fixtures/audio/valid_synthetic_stereo_44k1.mp3`

### tests/fixtures/audio/fma_small/
- `tests/fixtures/audio/fma_small/.gitkeep`

### tests/fixtures/audio/smoke_fma_small/000/
- `tests/fixtures/audio/smoke_fma_small/000/000002.mp3`
- `tests/fixtures/audio/smoke_fma_small/000/000666.mp3`

### tests/fixtures/events/v1/
- `tests/fixtures/events/v1/audio.features.valid.json`
- `tests/fixtures/events/v1/audio.features.version-mismatch.json`
- `tests/fixtures/events/v1/audio.metadata.missing-trace-id.json`
- `tests/fixtures/events/v1/audio.metadata.run-id-mismatch.json`
- `tests/fixtures/events/v1/audio.metadata.valid.json`
- `tests/fixtures/events/v1/audio.segment.ready.payload-type-mismatch.json`
- `tests/fixtures/events/v1/audio.segment.ready.valid.json`
- `tests/fixtures/events/v1/system.metrics.payload-type-mismatch.json`
- `tests/fixtures/events/v1/system.metrics.run_total.valid.json`
- `tests/fixtures/events/v1/system.metrics.valid.json`

### tests/integration/
- `tests/integration/__init__.py`
- `tests/integration/test_contract_fixtures.py`
- `tests/integration/test_processing_reference_parity.py`
- `tests/integration/test_review_views.py`
- `tests/integration/test_writer_schema_contract.py`

### tests/unit/
- *(37 files: 37 .py)*
