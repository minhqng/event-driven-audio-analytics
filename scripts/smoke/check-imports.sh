#!/usr/bin/env sh
set -eu

python -m compileall src tests >/dev/null
echo "Import and syntax compilation checks passed."
