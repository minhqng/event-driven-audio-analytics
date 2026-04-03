#!/usr/bin/env sh
set -eu

topic_name="${1:-}"
max_messages="${2:-5}"

if [ -z "$topic_name" ]; then
  echo "Usage: sh ./scripts/smoke/observe-topic.sh <topic> [max_messages]" >&2
  exit 1
fi

docker compose exec -T kafka /opt/bitnami/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server "${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}" \
  --topic "$topic_name" \
  --from-beginning \
  --max-messages "$max_messages" \
  --timeout-ms 10000 \
  --property print.key=true \
  --property key.separator='|'
