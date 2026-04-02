# Local Demo Runbook

## Prerequisites

- Docker with Compose support.
- A copied `.env` file based on `.env.example`.
- `bash` for the host-side helper scripts.
- Commands are expected to run from the repository root.

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

4. To validate the first Kafka -> writer -> DB path, run:

   ```sh
   bash ./scripts/smoke/check-writer-flow.sh
   ```

5. To inspect the writer manually after the stack is up, use:

   ```sh
   docker compose logs -f writer
   ```

6. To confirm the smoke path in TimescaleDB manually, use:

   ```sh
   docker compose exec -T timescaledb psql -U audio_analytics -d audio_analytics -c "SELECT run_id, track_id, validation_status FROM track_metadata;"
   docker compose exec -T timescaledb psql -U audio_analytics -d audio_analytics -c "SELECT run_id, track_id, segment_idx, artifact_uri FROM audio_features;"
   docker compose exec -T timescaledb psql -U audio_analytics -d audio_analytics -c "SELECT consumer_group, topic_name, partition_id, run_id, last_committed_offset FROM run_checkpoints ORDER BY topic_name;"
   ```

   The Week 2 smoke path is healthy when `track_metadata` contains `demo-run / 2`, `audio_features` contains `demo-run / 2 / 0`, and `run_checkpoints` contains rows for `audio.metadata` and `audio.features`.

7. Kafka is reachable as `localhost:9092` from the host and `kafka:29092` from other containers.
8. Open Grafana on `http://localhost:3000`.

## Notes

- The demo flow now covers a minimal real Kafka -> writer -> TimescaleDB path for fake metadata and feature events.
- The repository still does not claim full DSP or end-to-end audio analytics behavior.
- The application code itself executes inside Linux containers; the host only runs Docker Compose helpers.
- Dashboard JSON and datasource provisioning are placeholders that must load cleanly, but they do not imply real analytics queries exist yet.
- The `ingestion` and `processing` containers currently emit scaffold logs and exit with code `0`; this is expected until their runtime loops are implemented.
