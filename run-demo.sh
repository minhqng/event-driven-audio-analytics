#!/usr/bin/env sh
set -eu

echo "Starting event-driven-audio-analytics demo stack..."
docker compose up --build -d

echo "Creating Kafka topics..."
./infra/kafka/create-topics.sh

echo "Demo stack is up."
echo "Grafana: http://localhost:${GRAFANA_PORT:-3000}"
echo "TimescaleDB: localhost:${TIMESCALEDB_PORT:-5432}"
echo "Kafka bootstrap: localhost:${KAFKA_BROKER_PORT:-9092}"
