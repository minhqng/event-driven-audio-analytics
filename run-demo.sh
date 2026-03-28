#!/usr/bin/env sh
set -eu

echo "Starting event-driven-audio-analytics demo stack..."
docker compose up --build -d

echo "Creating Kafka topics..."
sh ./infra/kafka/create-topics.sh

echo "Demo bootstrap completed."
echo "Grafana: http://localhost:${GRAFANA_PORT:-3000}"
echo "TimescaleDB: localhost:${TIMESCALEDB_PORT:-5432}"
echo "Kafka bootstrap (host): localhost:${KAFKA_BROKER_PORT:-9092}"
echo "Kafka bootstrap (containers): ${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}"
echo "Scaffold services currently emit startup logs and exit 0 until continuous runtime loops are implemented."
