#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
share_mode=false
if [[ "${1:-}" == '--share' ]]; then
  share_mode=true
elif [[ $# -ne 0 ]]; then
  echo "Usage: bash scripts/demo-live.sh [--share]" >&2
  exit 2
fi

for artifact in models/sitewatch-v1/detector.pt models/sitewatch-v1/classifier.pth; do
  if [[ ! -r "$artifact" ]]; then
    echo "Missing private model artifact: $artifact" >&2
    echo "See docs/model-serving.md for the expected paths." >&2
    exit 1
  fi
done
if [[ ! -x apps/inference/.venv/bin/uvicorn ]]; then
  echo "Inference environment is missing. Run: make inference-check" >&2
  exit 1
fi
if [[ ! -x apps/web/node_modules/.bin/vite ]]; then
  echo "Web dependencies are missing. Run: pnpm install" >&2
  exit 1
fi
if ! command -v openssl >/dev/null || ! command -v cargo >/dev/null; then
  echo "The local demo requires openssl and cargo." >&2
  exit 1
fi
if [[ "$share_mode" == true ]] && ! command -v ssh >/dev/null; then
  echo "A share link requires the system SSH client. See docs/model-serving.md." >&2
  exit 1
fi

for port in 8083 8084 5174; do
  if command -v lsof >/dev/null && lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Stop that process before starting the demo." >&2
    exit 1
  fi
done

cargo build -q -p sitewatch-deviations
if [[ "$share_mode" == true ]]; then
  pnpm --filter @sitewatch/web build
  umask 077
fi

demo_token="$(openssl rand -hex 32)"
export SITEWATCH_INTERNAL_TOKEN="$demo_token"
export DETECTOR_WEIGHTS="$project_root/models/sitewatch-v1/detector.pt"
export CLASSIFIER_WEIGHTS="$project_root/models/sitewatch-v1/classifier.pth"
export DEVIATIONS_HTTP_ADDR="127.0.0.1:8084"
export DEVIATIONS_URL="http://127.0.0.1:8084"
export INFERENCE_URL="http://127.0.0.1:8083"
export INFERENCE_DEMO_ENABLED=true
export YOLO_CONFIG_DIR="${TMPDIR:-/tmp}/sitewatch-yolo-config"

inference_pid=''
deviations_pid=''
web_pid=''
tunnel_pid=''
tunnel_log=''
cleanup() {
  for pid in "$tunnel_pid" "$web_pid" "$deviations_pid" "$inference_pid"; do
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  for pid in "$tunnel_pid" "$web_pid" "$deviations_pid" "$inference_pid"; do
    if [[ -n "$pid" ]]; then
      wait "$pid" 2>/dev/null || true
    fi
  done
  if [[ -n "$tunnel_log" ]]; then
    rm -f -- "$tunnel_log"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

apps/inference/.venv/bin/uvicorn sitewatch_inference.app:create_app \
  --factory --host 127.0.0.1 --port 8083 &
inference_pid=$!
target/debug/sitewatch-deviations &
deviations_pid=$!

echo "Loading the private model and starting the rule service…"
ready=false
for _ in {1..120}; do
  if ! kill -0 "$inference_pid" 2>/dev/null || ! kill -0 "$deviations_pid" 2>/dev/null; then
    echo "A backend service stopped during startup." >&2
    exit 1
  fi
  if curl -fsS http://127.0.0.1:8083/health/ready >/dev/null 2>&1 &&
     curl -fsS http://127.0.0.1:8084/health/ready >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then
  echo "The model or rule service did not become ready within two minutes." >&2
  exit 1
fi

if [[ "$share_mode" == true ]]; then
  tunnel_log="$(mktemp "${TMPDIR:-/tmp}/sitewatch-tunnel.XXXXXX")"
  ssh -T -p 443 -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -R0:127.0.0.1:5174 a.pinggy.io >"$tunnel_log" 2>&1 &
  tunnel_pid=$!
  tunnel_origin=''
  for _ in {1..60}; do
    tunnel_origin="$(grep -Eo 'https://[a-zA-Z0-9-]+\.run\.pinggy-free\.link' "$tunnel_log" | head -n 1 || true)"
    if [[ -n "$tunnel_origin" ]]; then
      break
    fi
    if ! kill -0 "$tunnel_pid" 2>/dev/null; then
      echo "The temporary SSH tunnel could not start." >&2
      grep -Ei 'error|denied|timed out|closed|refused|unable' "$tunnel_log" | tail -n 8 >&2 || true
      exit 1
    fi
    sleep 1
  done
  if [[ -z "$tunnel_origin" ]]; then
    echo "The tunnel did not provide a share URL within one minute." >&2
    grep -Ei 'error|denied|timed out|closed|refused|unable' "$tunnel_log" | tail -n 8 >&2 || true
    exit 1
  fi

  export SITEWATCH_SHARE_TOKEN="$(openssl rand -hex 32)"
  export HOST=127.0.0.1 PORT=5174 ORIGIN="$tunnel_origin" BODY_SIZE_LIMIT=13M
  (cd apps/web && exec node build) &
  web_pid=$!
  web_ready=false
  for _ in {1..30}; do
    response_code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5174/app/model || true)"
    if [[ "$response_code" == 403 ]]; then
      web_ready=true
      break
    fi
    if ! kill -0 "$web_pid" 2>/dev/null; then
      echo "The production web server stopped during startup." >&2
      exit 1
    fi
    sleep 1
  done
  if [[ "$web_ready" != true ]]; then
    echo "The protected web server did not become ready." >&2
    exit 1
  fi
  public_ready=false
  for _ in {1..60}; do
    response_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
      "$tunnel_origin/app/model?access=$SITEWATCH_SHARE_TOKEN" || true)"
    if [[ "$response_code" == 303 ]]; then
      public_ready=true
      break
    fi
    if ! kill -0 "$tunnel_pid" 2>/dev/null; then
      echo "The tunnel stopped before the link was reachable." >&2
      grep -Ei 'error|denied|timed out|closed|refused|unable' "$tunnel_log" | tail -n 8 >&2 || true
      exit 1
    fi
    sleep 1
  done
  if [[ "$public_ready" != true ]]; then
    echo "The link did not become reachable through the tunnel." >&2
    grep -Ei 'error|denied|timed out|closed|refused|unable' "$tunnel_log" | tail -n 8 >&2 || true
    exit 1
  fi
  echo "SHARE_LINK=$tunnel_origin/app/model?access=$SITEWATCH_SHARE_TOKEN"
  echo "Anyone with this secret link can use the demo. Free tunnel sessions expire after 60 minutes."
  echo "Only the website goes through the tunnel; model and rule services stay on 127.0.0.1."
  while kill -0 "$web_pid" 2>/dev/null && kill -0 "$tunnel_pid" 2>/dev/null; do
    sleep 5
  done
  echo "The website or tunnel stopped; ending this sharing session." >&2
  exit 1
else
  (cd apps/web && exec node_modules/.bin/vite dev --host 127.0.0.1 --port 5174 --strictPort) &
  web_pid=$!
  echo "SiteWatch local demo: http://127.0.0.1:5174/app/model"
  echo "This is an operator preview, not a persisted alert system. Press Ctrl+C to stop."
  wait "$web_pid"
fi
