#!/usr/bin/env bash
# One-time setup: downloads Scotland's map data, scores every road, and prepares routing.
# Takes roughly 10-20 minutes on a decent PC. Re-run any time to refresh the map data.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data

if command -v podman >/dev/null; then D=podman; elif command -v docker >/dev/null; then D=docker
else echo "Install podman first:  sudo dnf install podman"; exit 1; fi
IMG=ghcr.io/project-osrm/osrm-backend:latest
PBF=scotland-latest.osm.pbf

echo "==> 1/4 Downloading Scotland map data (~250 MB)"
if [ ! -f "data/$PBF" ] || [ "${REFRESH:-0}" = 1 ]; then
  curl -L --fail -o "data/$PBF" "https://download.geofabrik.de/europe/united-kingdom/$PBF"
fi

echo "==> 2/4 Installing the map reader (Python)"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip osmium

echo "==> 3/4 Scoring every road for bends and views"
.venv/bin/python score_roads.py "data/$PBF" data

echo "==> 4/4 Preparing turn-by-turn routing (OSRM)"
$D pull $IMG
$D run --rm -v "$PWD/data:/data:Z" $IMG osrm-extract -p /opt/car.lua "/data/$PBF"
$D run --rm -v "$PWD/data:/data:Z" $IMG osrm-partition /data/scotland-latest.osrm
$D run --rm -v "$PWD/data:/data:Z" $IMG osrm-customize /data/scotland-latest.osrm

echo
echo "Setup complete. Now run:  ./start.sh"
