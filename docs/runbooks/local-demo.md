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

## Notes

- The scaffold does not implement full DSP or persistence behavior yet.
- The demo flow is for bootstrapping the stack and confirming configuration wiring only.
- The application code itself executes inside Linux containers; the host only runs Docker Compose helpers.
- Dashboard JSON and datasource provisioning are placeholders that must load cleanly, but they do not imply real analytics queries exist yet.
- The `ingestion`, `processing`, and `writer` containers currently emit scaffold logs and exit with code `0`; this is expected until the runtime loops are implemented.
