#!/usr/bin/env bash
# One-time native build of the demo inside a vast.ai container: vast instances are
# containers themselves, so compose.demo.yaml cannot run there. Mirrors the Dockerfiles.
set -euo pipefail
cd "$(dirname "$0")/../.."
export DEBIAN_FRONTEND=noninteractive PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/node/bin:$PATH"

apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  libglib2.0-0 libgl1 curl ca-certificates xz-utils openssl build-essential pkg-config supervisor >/dev/null

sha256sum -c MODEL_SHA256SUMS.txt

command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/0.9.22/install.sh | sh
(cd apps/inference && uv sync --frozen --no-dev --extra serve && uv cache clean)

if [[ "$(node -v 2>/dev/null)" != v24.* ]]; then
  file="$(curl -fsSL https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt | awk '/linux-x64\.tar\.xz$/ {print $2}')"
  curl -fsSL "https://nodejs.org/dist/latest-v24.x/$file" | tar -xJ -C /opt
  ln -sfn "/opt/${file%.tar.xz}" /opt/node
fi
corepack enable
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
pnpm install --frozen-lockfile
pnpm --filter @sitewatch/web check || echo 'svelte-check reported problems (build continues)'
pnpm --filter @sitewatch/web build

command -v cargo >/dev/null || curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none
cargo build --locked --release -p sitewatch-deviations
echo 'setup done'
