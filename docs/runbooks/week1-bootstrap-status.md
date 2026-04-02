# Week 1 Bootstrap Status

The Week 1 bootstrap foundation remains the base local environment for this repository.
That baseline is now exercised by the Week 2 writer smoke path instead of staying infrastructure-only.

## Verified

- Docker Compose config renders successfully.
- Kafka, TimescaleDB, and Grafana are the Week 1 foundation services.
- Kafka topic bootstrap is scripted for the Linux container runtime and host-side POSIX helpers.
- TimescaleDB init SQL defines the core tables, operational views, and the first Week 2 persistence snapshot table.
- Grafana datasource and dashboard provisioning are file-backed placeholders.
- Runtime services mount `artifacts/` as the local claim-check boundary.
- The `writer` service now stays up as a minimal Kafka-to-TimescaleDB consumer.
- Fake `audio.metadata` and `audio.features` events can be published and persisted to TimescaleDB with checkpoint updates.

## Current Scope

- `ingestion` and `processing` remain scaffold-only services.
- Dashboard panels are still placeholders and do not imply finished analytics queries.
- End-to-end audio analytics is still not claimed beyond the Week 2 fake-event writer path.

## Recommended Validation

- `bash ./scripts/smoke/check-compose.sh`
- `docker compose run --rm --entrypoint python writer -m unittest discover -s tests -p "test_*.py"`
- `bash ./scripts/smoke/check-writer-flow.sh`
