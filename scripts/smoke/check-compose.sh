#!/usr/bin/env sh
set -eu

docker compose config >/dev/null
echo "Compose config rendered successfully."
