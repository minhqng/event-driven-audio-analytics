#!/usr/bin/env sh
set -eu

bootstrap_server="${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}"
kafka_topics="/opt/bitnami/kafka/bin/kafka-topics.sh"

wait_for_broker() {
  attempt=0
  until docker compose exec -T kafka "$kafka_topics" --bootstrap-server "$bootstrap_server" --list >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
      echo "Kafka broker did not become ready in time." >&2
      exit 1
    fi
    sleep 2
  done
}

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

wait_for_broker

create_topic "audio.metadata"
create_topic "audio.segment.ready"
create_topic "audio.features"
create_topic "system.metrics"
create_topic "audio.dlq"

echo "Current Kafka topics:"
docker compose exec -T kafka "$kafka_topics" --bootstrap-server "$bootstrap_server" --list

echo "Current Kafka topics:"
docker compose exec -T kafka "$kafka_topics" --bootstrap-server "$bootstrap_server" --list

echo "Kafka topics ensured."
