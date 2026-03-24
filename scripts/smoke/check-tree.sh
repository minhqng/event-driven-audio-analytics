#!/usr/bin/env sh
set -eu

required_paths="
README.md
docker-compose.yml
pyproject.toml
infra/kafka/create-topics.sh
infra/sql/002_core_tables.sql
src/event_driven_audio_analytics/ingestion/app.py
src/event_driven_audio_analytics/processing/app.py
src/event_driven_audio_analytics/writer/app.py
"

for path in $required_paths; do
  if [ ! -e "$path" ]; then
    echo "Missing required path: $path" >&2
    exit 1
  fi
done

echo "Tree sanity check passed."
