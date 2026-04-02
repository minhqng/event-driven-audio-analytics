#!/usr/bin/env sh
set -eu

echo "Starting event-driven-audio-analytics demo stack..."
docker compose up --build -d kafka timescaledb grafana

echo "Creating Kafka topics..."
sh ./infra/kafka/create-topics.sh

echo "Starting runtime services..."
docker compose up --build -d ingestion processing writer

echo "Demo bootstrap completed."
echo "Grafana: http://localhost:${GRAFANA_PORT:-3000}"
echo "TimescaleDB: localhost:${TIMESCALEDB_PORT:-5432}"
echo "Kafka bootstrap (host): localhost:${KAFKA_BROKER_PORT:-9092}"
echo "Kafka bootstrap (containers): ${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}"
echo "Writer now stays up as a minimal Kafka-to-TimescaleDB consumer."
echo "Ingestion and processing remain scaffold-only until their runtime loops are implemented."
