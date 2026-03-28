# Local Demo Runbook

## Prerequisites

- Docker with Compose support.
- A copied `.env` file based on `.env.example`.
- PowerShell on Windows or `bash` for the POSIX wrappers.

## Demo Steps

1. Review `docs/architecture/system-overview.md`.
2. On Windows PowerShell, start the local scaffold with:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\run-demo.ps1
   ```

3. On POSIX shells, the equivalent command is:

   ```sh
   bash ./run-demo.sh
   ```

4. If you want to bootstrap topics without starting the full demo helper, use:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\infra\kafka\create-topics.ps1
   ```

5. Kafka is reachable as `localhost:9092` from the host and `kafka:29092` from other containers.
6. Open Grafana on `http://localhost:3000`.

## Notes

- The scaffold does not implement full DSP or persistence behavior yet.
- The demo flow is for bootstrapping the stack and confirming configuration wiring only.
- Dashboard JSON and datasource provisioning are placeholders that must load cleanly, but they do not imply real analytics queries exist yet.
- The `ingestion`, `processing`, and `writer` containers currently emit scaffold logs and exit with code `0`; this is expected until the runtime loops are implemented.
