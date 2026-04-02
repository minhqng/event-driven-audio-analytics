#!/usr/bin/env sh
set -eu

required_paths="
README.md
docker-compose.yml
pyproject.toml
infra/kafka/create-topics.sh
infra/kafka/create-topics.ps1
infra/sql/002_core_tables.sql
scripts/smoke/check-writer-flow.sh
run-demo.ps1
src/event_driven_audio_analytics/smoke/publish_fake_events.py
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
