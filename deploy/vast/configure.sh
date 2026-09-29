#!/usr/bin/env bash
# Writes deploy/vast/env once: public origin, description model settings from .env.demo, fresh tokens.
# Tokens are kept on later runs so the shared link survives restarts.
set -euo pipefail
cd "$(dirname "$0")"
origin="${1:?usage: configure.sh http://PUBLIC_IP:PORT}"
touch env && chmod 600 env
keep() { sed -n "s/^$1=//p" env | tail -n 1; }
internal="$(keep SITEWATCH_INTERNAL_TOKEN)"; share="$(keep SITEWATCH_SHARE_TOKEN)"
describe="$(grep -E '^DESCRIBE_(API_URL|API_KEY|MODEL)=' ../../.env.demo || true)"
cat > env <<ENV
ORIGIN=$origin
SITEWATCH_INTERNAL_TOKEN=${internal:-$(openssl rand -hex 32)}
SITEWATCH_SHARE_TOKEN=${share:-$(openssl rand -hex 32)}
SITEWATCH_SHARE_TTL_HOURS=336
$describe
ENV
echo "env written for $origin"
