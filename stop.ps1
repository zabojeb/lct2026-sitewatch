$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
docker compose --env-file .env.demo -f compose.demo.yaml down
if ($LASTEXITCODE -ne 0) { throw 'Не удалось остановить контейнеры.' }
