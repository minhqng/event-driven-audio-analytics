# Local Demo Runbook

## Prerequisites

- Docker with Compose support.
- A copied `.env` file based on `.env.example`.
- `bash` or PowerShell for the host-side helper scripts.

## Demo Steps

1. Review `docs/architecture/system-overview.md`.
2. For the bounded Week 8 final demo, use the single-command evidence path:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-week8-evidence.ps1
   ```

   ```sh
   bash ./scripts/demo/generate-week8-evidence.sh
   ```

   See `docs/runbooks/final-demo.md` for the recommended talk track, reliability notes, artifact layout, and honest limits.

3. If you only want the dashboard-facing artifact path, use:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-week7-dashboard-evidence.ps1
   ```

   ```sh
   bash ./scripts/demo/generate-week7-dashboard-evidence.sh
   ```

   See `docs/runbooks/intermediate-demo.md` for the dashboard-specific talk track, panel meaning, and generated artifact files.

4. If you want to start the local scaffold without running the bounded demo inputs yet, use:

   ```sh
   bash ./run-demo.sh
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\run-demo.ps1
   ```

5. If you want to bootstrap topics without starting the full demo helper, use:

   ```sh
   sh ./infra/kafka/create-topics.sh
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\infra\kafka\create-topics.ps1
   ```

6. Kafka is reachable as `localhost:9092` from the host and `kafka:29092` from other containers.
7. Open Grafana on `http://localhost:3000`.
8. For a Week 4 ingestion-only broker smoke run that exercises preflight, writes artifacts, verifies exact current-run messages plus the run manifest against the currently configured input selection, and prints observed topic samples, use:

   ```sh
   bash ./scripts/smoke/check-ingestion-flow.sh
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-ingestion-flow.ps1
   ```

9. For a Week 5 processing broker smoke run that starts `processing`, feeds Kafka from a one-shot `ingestion` run, verifies exact current-run `audio.features` plus processing-owned `system.metrics`, and prints observed topic samples, use:

   ```sh
   bash ./scripts/smoke/check-processing-flow.sh
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-processing-flow.ps1
   ```

10. For a Week 6 broker smoke run that starts both `processing` and `writer`, feeds Kafka from a one-shot `ingestion` run, and verifies current-run persistence in TimescaleDB, use:

   ```sh
   bash ./scripts/smoke/check-processing-writer-flow.sh
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-processing-writer-flow.ps1
   ```

11. For the Week 8 restart/replay reliability path that proves fail-fast preflights, service restarts, same-`run_id` replay, checkpoint advancement, and replay-stable run state, use:

   ```sh
   bash ./scripts/smoke/check-restart-replay-flow.sh
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-restart-replay-flow.ps1
   ```

12. For the Week 7 dashboard evidence path that auto-loads the provisioned dashboards, runs three deterministic demo cases, verifies dashboard-facing TimescaleDB data, captures screenshots, and writes demo artifact notes, use:

   ```sh
   bash ./scripts/demo/generate-week7-dashboard-evidence.sh
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-week7-dashboard-evidence.ps1
   ```

13. For a bounded repo-local FMA-small burst after the stack is already running, place the dataset at:

   - `tests/fixtures/audio/tracks.csv`
   - `tests/fixtures/audio/fma_small/...`

   Then use:

   ```sh
   bash ./scripts/demo/run-repo-local-fma-burst.sh
   ```

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\demo\run-repo-local-fma-burst.ps1
   ```

   Defaults:

   - `RUN_ID=fma-small-live`
   - `INGESTION_MAX_TRACKS=100`
   - `TRACK_ID_ALLOWLIST` unset or empty, so the repo-local metadata selection is not forced back to `2,666`

## Notes

- The default Grafana stack now auto-loads the file-provisioned dashboards backed by real TimescaleDB queries.
- The final Week 8 evidence script runs the restart/replay smoke first, then refreshes the dashboard evidence artifacts.
- `ingestion` is now containerized for a bounded Compose replay path, performs a startup preflight/readiness gate, and no longer just prints scaffold steps.
- `processing` is now containerized as a long-lived Kafka consumer, performs a startup preflight/readiness gate, and no longer stays at placeholder-only runtime behavior.
- `processing` and `writer` now close their Kafka consumers gracefully on `SIGTERM` / `SIGINT`, which keeps the bounded restart/replay path practical under `docker compose restart`.
- The ingestion smoke wrappers respect `RUN_ID`; the default remains `demo-run` when `RUN_ID` is unset.
- The processing smoke wrappers also respect `RUN_ID`; the default remains `demo-run` when `RUN_ID` is unset.
- The application code itself executes inside Linux containers; the host only runs Docker Compose helpers.
- The default ingestion smoke path uses committed synthetic fixtures mounted read-only into the container from `smoke_tracks.csv` plus `smoke_fma_small/`, and the Python verifier derives expected outputs from the active metadata/audio inputs.
- The default processing smoke path uses the same committed synthetic fixtures, while the repo-local FMA helper uses `tests/fixtures/audio/tracks.csv` plus `tests/fixtures/audio/fma_small/` for bounded real-data bursts.
- `writer` is now part of both the bounded broker-backed smoke path and the Week 7 dashboard evidence path into TimescaleDB.
