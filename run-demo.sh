#!/usr/bin/env sh
set -eu

echo "Starting event-driven-audio-analytics demo stack..."
docker compose up --build -d kafka timescaledb grafana processing writer

echo "Creating Kafka topics..."
sh ./infra/kafka/create-topics.sh

echo "Demo bootstrap completed."
echo "Grafana: http://localhost:${GRAFANA_PORT:-3000}"
echo "TimescaleDB: localhost:${TIMESCALEDB_PORT:-5432}"
echo "Kafka bootstrap (host): localhost:${KAFKA_BROKER_PORT:-9092}"
echo "Kafka bootstrap (containers): ${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}"
echo "Grafana auto-loads the file-provisioned TimescaleDB datasource and the Week 7 dashboards."
echo "Run 'bash ./scripts/demo/generate-week7-dashboard-evidence.sh' for the recommended Week 7.5 intermediate-demo path."
echo "See './docs/runbooks/intermediate-demo.md' for the live demo sequence and panel interpretation."
echo "Run 'bash ./scripts/smoke/check-ingestion-flow.sh' for the Week 4 broker-backed ingestion smoke path."
echo "Run 'bash ./scripts/smoke/check-processing-flow.sh' for the Week 5 broker-backed processing smoke path."
echo "Run 'bash ./scripts/smoke/check-processing-writer-flow.sh' for the Week 6 broker-backed persistence smoke path."
echo "Run 'bash ./scripts/smoke/check-pytest.sh' for the official containerized pytest path."
