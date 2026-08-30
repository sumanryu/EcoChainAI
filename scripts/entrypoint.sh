#!/usr/bin/env bash
# Entrypoint = runs FIRST, every time the container starts, before CMD.
# The difference from CMD: ENTRYPOINT is for setup/prep work that should
# always happen; CMD (or docker-compose's `command:`) is the actual "main
# job" that varies per service (dashboard vs agents).
#
# `exec "$@"` at the end hands control over to whatever CMD/command was
# specified — this replaces this shell script's process with the real one
# (important so Docker's stop/restart signals reach the actual app, not a
# wrapper script sitting in front of it).

set -e

echo "== Fetching data from S3 =="
python scripts/fetch_data_from_s3.py

echo "== Starting: $@ =="
exec "$@"
