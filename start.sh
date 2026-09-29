#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo 'Нужен запущенный Docker Desktop или Docker Engine с Compose v2.' >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo 'Нужен openssl для генерации внутреннего токена.' >&2
  exit 1
fi
if [[ ! -f .env.demo ]]; then
  echo 'Нет .env.demo с настройками модели описания (см. README_FIRST.md).' >&2
  exit 1
fi

export SITEWATCH_INTERNAL_TOKEN="$(openssl rand -hex 32)"
docker compose --env-file .env.demo -f compose.demo.yaml up --build -d

port="$(sed -n 's/^SITEWATCH_WEB_PORT=//p' .env.demo | tail -n 1)"
port="${port:-3000}"
echo "SiteWatch: http://localhost:${port}/"
echo "Анализ сцен: http://localhost:${port}/app/model"
echo 'Первый запуск скачивает зависимости и собирает контейнеры; повторный быстрее.'
