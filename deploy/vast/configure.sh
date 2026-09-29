#!/usr/bin/env bash
# Writes deploy/vast/env once: public origin, OpenRouter key from .env.demo, fresh tokens.
# Tokens are kept on later runs so the shared link survives restarts.
set -euo pipefail
cd "$(dirname "$0")"
origin="${1:?usage: configure.sh http://PUBLIC_IP:PORT}"
touch env && chmod 600 env
keep() { sed -n "s/^$1=//p" env | tail -n 1; }
internal="$(keep SITEWATCH_INTERNAL_TOKEN)"; share="$(keep SITEWATCH_SHARE_TOKEN)"
key="$(sed -n 's/^OPENROUTER_API_KEY=//p' ../../.env.demo | tail -n 1)"
cat > env <<ENV
ORIGIN=$origin
SITEWATCH_INTERNAL_TOKEN=${internal:-$(openssl rand -hex 32)}
SITEWATCH_SHARE_TOKEN=${share:-$(openssl rand -hex 32)}
SITEWATCH_SHARE_TTL_HOURS=336
OPENROUTER_API_KEY=$key
ENV
echo "env written for $origin"
