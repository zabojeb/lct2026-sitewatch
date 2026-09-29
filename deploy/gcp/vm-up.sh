#!/usr/bin/env bash
# Runs on the VM from the unpacked repository: installs Docker once, checks the weights, starts the demo.
set -euo pipefail
cd "$(dirname "$0")/../.."
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sudo sh
sha256sum -c MODEL_SHA256SUMS.txt
test -f deploy/gcp/.env || { echo 'deploy/gcp/.env is missing' >&2; exit 1; }
sudo docker compose --env-file deploy/gcp/.env -f compose.demo.yaml -f deploy/gcp/compose.gcp.yaml up --build -d
sudo docker compose --env-file deploy/gcp/.env -f compose.demo.yaml -f deploy/gcp/compose.gcp.yaml ps
