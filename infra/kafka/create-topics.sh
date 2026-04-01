#!/usr/bin/env sh
set -eu

bootstrap_server="${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}"
kafka_topics="/opt/bitnami/kafka/bin/kafka-topics.sh"

create_topic() {
  topic_name="$1"
  docker compose exec -T kafka "$kafka_topics" \
    --bootstrap-server "$bootstrap_server" \
    --create \
    --if-not-exists \
    --topic "$topic_name" \
    --partitions 1 \
    --replication-factor 1
}

create_topic "audio.metadata"
create_topic "audio.segment.ready"
create_topic "audio.features"
create_topic "system.metrics"

echo "Current Kafka topics:"
docker compose exec -T kafka "$kafka_topics" --bootstrap-server "$bootstrap_server" --list

echo "Kafka topics ensured."
