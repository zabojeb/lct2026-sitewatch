#!/usr/bin/env bash
# Runs every demo frame through both recognition modes once, so the demo scenes answer from the cache.
set -euo pipefail
cd "$(dirname "$0")/../.."
token=$(sed -n 's/^SITEWATCH_INTERNAL_TOKEN=//p' deploy/gcp/.env)
host=$(sudo docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$(sudo docker ps -qf name=inference)")
for mode in 640 960; do
  for image in apps/web/static/demo-scenes/media/*.webp; do
    curl -fsS -o /dev/null -H "Authorization: Bearer $token" \
      -F "image=@$image;type=image/webp" -F "recognition_mode=$mode" "http://$host:8083/v1/predict"
  done
  echo "mode $mode warmed"
done
