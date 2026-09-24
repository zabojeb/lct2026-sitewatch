# SiteWatch

Интеллектуальный контроль строительной площадки: система обнаруживает технику на снимках,
сопоставляет наблюдение с активными этапами календарного плана и формирует объяснимые
предупреждения с доказательствами.

Целевая архитектура: независимые Rust-микросервисы в Kubernetes, NATS JetStream и отдельные БД/роли
сервисов внутри одного PostgreSQL-кластера. Решение закреплено в
[ADR 0005](docs/adr/0005-microservices-and-kubernetes.md). `apps/schedule` — первый выделенный
сервис с собственной БД, ревизиями плана и JetStream outbox. Остальные бизнес-сервисы ещё не
реализованы; `apps/api` и общая миграция остаются прежним bootstrap-каркасом.

## Что уже заложено

- типизированный Rust-домен: проекты, зоны, камеры, этапы, правила, наблюдения и отклонения;
- OpenAPI 3.1 и AsyncAPI-контракты с версионированием и идемпотентностью;
- PostgreSQL/PostGIS-схема с временными интервалами, геометрией зон и immutable snapshots правил;
- transactional outbox для безопасной публикации событий;
- Redis для короткоживущего состояния и окон наблюдений;
- S3/MinIO для исходных и аннотированных снимков;
- NATS JetStream для конвейера `observation → inference → rule engine`;
- Rust/Axum API с liveness, readiness и встроенной Swagger UI;
- SvelteKit-лендинг и отдельный интерактивный демонстрационный пульт;
- Docker Compose для локальной разработки и Kustomize-оверлеи для Kubernetes;
- нативный multi-arch образ PostgreSQL/PostGIS для Apple Silicon и x86_64;
- CI для Rust, SvelteKit, контрактов и Kubernetes-манифестов.
- воспроизводимый CV/MLOps-контур: DVC, Label Studio, Dagster, MLflow Model Registry и quality gates.
- отдельный Rust-сервис графика: импорт и чтение неизменяемых ревизий, источники правил,
  идемпотентность, монотонный номер активации, минимальные права runtime-роли и доставка событий.

## Быстрый запуск

### Лендинг и пульт без инфраструктуры

```bash
pnpm install --frozen-lockfile
pnpm dev
```

Лендинг: `http://localhost:5173/`, пульт: `http://localhost:5173/app`.
Работают поиск, фильтры, разбор наблюдения, локальное сохранение решений, календарный план,
экспорт JSON, тёмная/светлая тема и локальный предпросмотр изображений. Все площадки и наблюдения
синтетические; изображения сгенерированы, разметка задана вручную. Бизнес-API и ML ещё не подключены.
Демо не обращается к инфраструктуре и не отправляет загруженные изображения на сервер.

Live-сервис графика запускается отдельно и пока намеренно не подключён к браузерному демо:
для этого нужен авторизованный gateway/BFF и выбор OIDC-провайдера. Запуск, контракты и границы —
в [runbook сервиса графика](docs/schedule-service.md).

В пульте также доступны редактор обязательной/возможной техники и сроков, импорт плана JSON,
ручная схема зон с соседними этапами и обзором, аналитика, семь тестовых сценариев и сводка с
черновиком алерта. Настройки изолированы по площадкам. Процент готовности вводится вручную с
источником; отставание и дата завершения рассчитываются по явно указанному линейному сценарию,
не ML-моделью. [Полный объём и границы реализации](docs/web-masha-scope.md).

Проверки: `pnpm check`, `pnpm build`, `pnpm test:web`. Перед первым E2E-прогоном установите браузер:
`pnpm --filter @sitewatch/web exec playwright install chromium --only-shell`.
Если загрузка браузера недоступна, можно указать установленный Chrome через переменную
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` с абсолютным путём к исполняемому файлу.
E2E-тесты используют production-сборку, поэтому перед ними выполняйте `pnpm build`.

### Существующий инфраструктурный bootstrap

Требования: Rust 1.97+, Node.js 24+, pnpm 11+, Docker Compose.

```bash
cp .env.example .env
make bootstrap
make infra-up
make dev
```

После запуска:

- UI: `http://localhost:3000`
- API: `http://localhost:8080`
- Swagger UI: `http://localhost:8080/docs`
- MinIO console: `http://localhost:9001`
- NATS monitoring: `http://localhost:8222`

Локальные реквизиты предназначены только для Docker Compose и не используются в Kubernetes.
Если порт уже занят, его можно переопределить через `.env`, например `WEB_PORT=13000`.

## Команды

```bash
make check          # clippy, Svelte checks, OpenAPI lint
make test           # Rust unit tests
make contracts      # lint OpenAPI + regenerate TypeScript types
make db-migrate     # apply PostgreSQL migrations
make k8s-validate   # render dev and prod Kustomize overlays
make ml-bootstrap   # locked Python 3.12 ML environment
make ml-data        # reproduce dataset manifests and log audit to MLflow
make mlops-up       # PostgreSQL + MinIO + MLflow + Dagster
make labeling-up    # Label Studio on port 8081
```

## Структура

```text
apps/
  api/              Rust/Axum control plane
  schedule/         Isolated schedule service, migration and outbox publisher
  web/              SvelteKit operator interface
crates/
  domain/           Product language and invariants
  contracts/        HTTP/event DTOs
  platform/         Configuration, telemetry and infrastructure clients
contracts/          OpenAPI, AsyncAPI, JSON Schema and examples
migrations/         Versioned PostgreSQL/PostGIS schema
deploy/
  compose.yaml      Local full stack
  k8s/              Base manifests and dev/prod overlays
docs/
  adr/              Architecture decisions
  architecture.md   System boundaries and request/event flows
ml/
  config/           Dataset taxonomy and versioned experiment definitions
  src/sitewatch_ml/ Data quality, splitting, training and promotion pipeline
```

Исходные материалы организаторов остаются в корне неизменёнными. Большие изображения, датасеты,
модели и runtime-артефакты не попадают в Git.

## Данные и доказательная часть защиты

- [Реестр внешних источников](ml/config/external-sources.json): версии, заявленные лицензии,
  ссылки на архивы и ограничения допуска; скачивание не означает готовность к обучению.
- [Аудит внешних данных](docs/external-data-audit.md): фактические количества, целостность
  разметки, различия доменов и следующие проверки.
- [Метрики, гипотезы и план блока презентации](docs/analysis-and-evaluation-plan.md):
  протокол до обучения, независимый holdout, mAP по базовым классам и отдельная оценка
  предупреждений. Результаты обучения пока не получены.

## Архитектурные правила

1. `domain` не знает о PostgreSQL, HTTP, NATS и S3.
2. PostgreSQL — источник истины. Redis не хранит данные, потеря которых ломает аудит.
3. Снимки не проходят через JSON или PostgreSQL: браузер загружает их напрямую по presigned URL.
4. Любое предупреждение содержит снимок правила, наблюдаемый факт и ссылку на доказательства.
5. Повторный HTTP-запрос с тем же `Idempotency-Key` не создаёт дубликат.
6. Событие публикуется из transactional outbox, а consumer обязан быть идемпотентным.
7. Несовместимое изменение создаёт `/api/v2` или новый subject с суффиксом `.v2`.

Подробнее: [архитектура](docs/architecture.md) и [модель данных](docs/data-model.md).

ML-контур, от исходного архива до alias `champion`, описан в [MLOps runbook](docs/mlops.md); текущие
проверенные характеристики входного датасета — в [dataset audit](docs/dataset-audit.md).
