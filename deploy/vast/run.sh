#!/usr/bin/env bash
# Starts (or restarts) the three services under supervisord. Also the vast on-start hook.
set -euo pipefail
cd "$(dirname "$0")"
[[ -f env && -x ../../target/release/sitewatch-deviations && -d ../../apps/web/build ]] || {
  echo 'run setup.sh and configure.sh first' >&2
  exit 1
}
mkdir -p ../../logs
pid="$(cat ../../logs/supervisord.pid 2>/dev/null || true)"
if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
  supervisorctl -c supervisord.conf shutdown >/dev/null
  while kill -0 "$pid" 2>/dev/null; do sleep 1; done
fi
set -a
source ./env
set +a
supervisord -c supervisord.conf
echo 'started; supervisorctl -c deploy/vast/supervisord.conf status'
