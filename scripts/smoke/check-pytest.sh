#!/usr/bin/env sh
set -eu

echo "Building pytest image..."
docker compose build pytest

if [ "$#" -gt 0 ]; then
  echo "Running pytest with explicit arguments..."
  docker compose run --rm pytest "$@"
else
  echo "Running full pytest suite..."
  docker compose run --rm pytest
fi
