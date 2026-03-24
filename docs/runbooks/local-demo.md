# Local Demo Runbook

## Prerequisites

- Docker with Compose support.
- A copied `.env` file based on `.env.example`.

## Demo Steps

1. Review `docs/architecture/system-overview.md`.
2. Start infrastructure and service containers:

   ```sh
   docker compose up --build -d
   ```

3. Create the required Kafka topics:

   ```sh
   ./infra/kafka/create-topics.sh
   ```

4. Run the convenience script:

   ```sh
   ./run-demo.sh
   ```

5. Open Grafana on `http://localhost:3000`.

## Notes

- The scaffold does not implement full DSP or persistence behavior yet.
- The demo flow is for bootstrapping the stack and confirming configuration wiring only.
