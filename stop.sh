#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
docker compose --env-file .env.demo -f compose.demo.yaml down
