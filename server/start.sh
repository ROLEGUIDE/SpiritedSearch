#!/usr/bin/env bash
# Starts routing (in a container) and the Twisty server. Leave this terminal open while you use the app.
set -euo pipefail
cd "$(dirname "$0")"
if command -v podman >/dev/null; then D=podman; else D=docker; fi
IMG=ghcr.io/project-osrm/osrm-backend:latest

if ! $D ps --format '{{.Names}}' | grep -qx twisty-osrm; then
  $D rm -f twisty-osrm >/dev/null 2>&1 || true
  echo "Starting routing engine..."
  $D run -d --name twisty-osrm -p 127.0.0.1:5000:5000 -v "$PWD/data:/data:Z" $IMG \
    osrm-routed --algorithm mld /data/scotland-latest.osrm >/dev/null
fi

echo "Starting Twisty server..."
exec .venv/bin/python serve.py
