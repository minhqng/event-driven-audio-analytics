# Local Demo Runbook

## Prerequisites

- Docker with Compose support.
- A copied `.env` file based on `.env.example`.
- `bash` for the host-side helper scripts.

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
6. For a Week 3 ingestion-only broker smoke run that writes artifacts and prints observed topic messages, use:

   ```sh
   bash ./scripts/smoke/check-ingestion-flow.sh
   ```

## Notes

- The scaffold does not implement full DSP or persistence behavior yet.
- `ingestion` is now containerized for a bounded Compose replay path and no longer just prints scaffold steps.
- The application code itself executes inside Linux containers; the host only runs Docker Compose helpers.
- Dashboard JSON and datasource provisioning are placeholders that must load cleanly, but they do not imply real analytics queries exist yet.
- The default ingestion smoke path uses committed synthetic fixtures mounted read-only into the container. Override `METADATA_CSV_PATH` and `AUDIO_ROOT_PATH` to point at a local FMA-small pack when needed.
- `processing` is still placeholder. `writer` remains the persistence path for later cross-service validation.
