$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Установите и запустите Docker Desktop.'
}
docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Нужен Docker Compose v2.' }
if (-not (Test-Path '.env.demo')) { throw 'Нет .env.demo с настройками модели описания (см. README_FIRST.md).' }

$bytes = New-Object byte[] 32
$random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $random.GetBytes($bytes) } finally { $random.Dispose() }
$env:SITEWATCH_INTERNAL_TOKEN = [System.BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()

docker compose --env-file .env.demo -f compose.demo.yaml up --build -d
if ($LASTEXITCODE -ne 0) { throw 'Не удалось запустить контейнеры. Смотрите логи Docker Compose.' }

$portLine = Get-Content '.env.demo' | Where-Object { $_ -match '^SITEWATCH_WEB_PORT=' } | Select-Object -Last 1
$port = if ($portLine) { ($portLine -split '=', 2)[1] } else { '3000' }
Write-Host "SiteWatch: http://localhost:$port/"
Write-Host "Анализ сцен: http://localhost:$port/app/model"
Write-Host 'Первый запуск скачивает зависимости и собирает контейнеры; повторный быстрее.'
