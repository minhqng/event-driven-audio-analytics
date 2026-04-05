# Local Demo Runbook

## Prerequisites

- Docker with Compose support.
- A copied `.env` file based on `.env.example`.
- `bash` or PowerShell for the host-side helper scripts.

## Demo Steps

1. Review `docs/architecture/system-overview.md`.
2. Start the local scaffold with:

   ```sh
   bash ./run-demo.sh
   ```

3. If you want to bootstrap topics without starting the full demo helper, use:

   ```sh
   sh ./infra/kafka/create-topics.sh
   ```

4. Kafka is reachable as `localhost:9092` from the host and `kafka:29092` from other containers.
5. Open Grafana on `http://localhost:3000`.
6. For a Week 4 ingestion-only broker smoke run that exercises preflight, writes artifacts, verifies exact current-run messages plus the run manifest against the currently configured input selection, and prints observed topic samples, use:

   ```sh
   bash ./scripts/smoke/check-ingestion-flow.sh
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-ingestion-flow.ps1
   ```

7. For a Week 5 processing broker smoke run that starts `processing`, feeds Kafka from a one-shot `ingestion` run, verifies exact current-run `audio.features` plus processing-owned `system.metrics`, and prints observed topic samples, use:

   ```sh
   bash ./scripts/smoke/check-processing-flow.sh
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-processing-flow.ps1
   ```

8. For a Week 6 broker smoke run that starts both `processing` and `writer`, feeds Kafka from a one-shot `ingestion` run, and verifies current-run persistence in TimescaleDB, use:

   ```sh
   bash ./scripts/smoke/check-processing-writer-flow.sh
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-processing-writer-flow.ps1
   ```

9. For the Week 7 dashboard evidence path that auto-loads the provisioned dashboards, runs three deterministic demo cases, verifies dashboard-facing TimescaleDB data, and captures screenshots, use:

   ```sh
   bash ./scripts/demo/generate-week7-dashboard-evidence.sh
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-week7-dashboard-evidence.ps1
   ```

## Notes

- The default Grafana stack now auto-loads the file-provisioned dashboards backed by real TimescaleDB queries.
- `ingestion` is now containerized for a bounded Compose replay path, performs a startup preflight/readiness gate, and no longer just prints scaffold steps.
- `processing` is now containerized as a long-lived Kafka consumer, performs a startup preflight/readiness gate, and no longer stays at placeholder-only runtime behavior.
- The ingestion smoke wrappers respect `RUN_ID`; the default remains `demo-run` when `RUN_ID` is unset.
- The processing smoke wrappers also respect `RUN_ID`; the default remains `demo-run` when `RUN_ID` is unset.
- The application code itself executes inside Linux containers; the host only runs Docker Compose helpers.
- The default ingestion smoke path uses committed synthetic fixtures mounted read-only into the container, and the Python verifier derives expected outputs from the active metadata/audio inputs. Override `METADATA_CSV_PATH` and `AUDIO_ROOT_PATH` to point at a local FMA-small pack when needed.
- The default processing smoke path uses the same committed synthetic fixtures, while the same wrapper can be reused with local FMA-small overrides to observe a bounded multi-segment burst through the consumer.
- `writer` is now part of both the bounded broker-backed smoke path and the Week 7 dashboard evidence path into TimescaleDB.
