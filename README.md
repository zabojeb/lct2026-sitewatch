# SiteWatch

Интеллектуальный контроль строительной площадки: система обнаруживает технику на снимках,
сопоставляет наблюдение с активными этапами календарного плана и формирует объяснимые
предупреждения с доказательствами.

Целевая архитектура: независимые Rust-микросервисы в Kubernetes, NATS JetStream и отдельные БД/роли
сервисов внутри одного PostgreSQL-кластера. Решение закреплено в
[ADR 0005](docs/adr/0005-microservices-and-kubernetes.md). `apps/schedule` — первый выделенный
сервис с собственной БД, ревизиями плана и JetStream outbox. `apps/inference` — отдельный сервис
живого детектора и классификатора; он пока работает как приватный синхронный serving endpoint,
не как consumer наблюдений. `apps/deviations` считает только stateless-предпросмотр правил,
не хранит алерты. Остальные бизнес-сервисы ещё не реализованы; `apps/api` и общая
миграция остаются прежним bootstrap-каркасом.

## Прототип

Демо развёрнуто в Google Cloud: одна виртуальная машина в europe-north1, Docker Compose из
`compose.demo.yaml` и `deploy/gcp/compose.gcp.yaml`. Ссылка с доступом — в презентации команды.
Как развернуть заново — [deploy/gcp/README.md](deploy/gcp/README.md); что изменилось перед сдачей —
[CHANGES_2026-09-29.md](CHANGES_2026-09-29.md).

## Что уже заложено

- типизированный Rust-домен: проекты, зоны, камеры, этапы, правила, наблюдения и отклонения;
- OpenAPI 3.1 и AsyncAPI-контракты с версионированием и идемпотентностью;
- PostgreSQL/PostGIS-схема с временными интервалами, геометрией зон и immutable snapshots правил;
- transactional outbox для безопасной публикации событий;
- Redis-инфраструктура под короткоживущее состояние и окна наблюдений;
- S3/MinIO-инфраструктура под исходные и аннотированные снимки;
- контракты и NATS JetStream-инфраструктура под конвейер
  `observation → inference → rule engine` (потребители и сквозная обработка ещё не готовы);
- Rust/Axum API с liveness, readiness и встроенной Swagger UI;
- SvelteKit-лендинг и рабочий экран, показывающий состояние реально подключённых сервисов;
- Docker Compose для локальной разработки и Kustomize-оверлеи для Kubernetes;
- нативный multi-arch образ PostgreSQL/PostGIS для Apple Silicon и x86_64;
- CI для Rust, SvelteKit, контрактов и Kubernetes-манифестов.
- воспроизводимый CV/MLOps-контур: DVC, Label Studio, Dagster, MLflow Model Registry и quality gates.
- отдельный Rust-сервис графика: импорт и чтение неизменяемых ревизий, источники правил,
  идемпотентность, монотонный номер активации, минимальные права runtime-роли и доставка событий.
- приватный двухэтапный inference-сервис с проверкой хэшей весов, 22 сырыми классами,
  сопоставлением с таксономией правил и отдельным live-экраном загрузки кадра.
- отдельный Rust-сервис предпросмотра правил: несколько реальных кадров, источники, обзор,
  количество и ручной замер готовности; один кадр не становится алертом.

## Быстрый запуск

### Лендинг и интерфейс без инфраструктуры

```bash
pnpm install --frozen-lockfile
pnpm dev
```

Лендинг: `http://localhost:5173/`, пульт: `http://localhost:5173/app`, пульт площадки: `http://localhost:5173/app/site` — выбор камер, этап по технике, план и отставание, запретные зоны и журнал на реальных кадрах открытых датасетов ([описание](docs/site-console.md)).
Пульт больше не показывает вымышленные площадки, снимки или сигналы: он отображает состояние
сервисов и ведёт на `/app/model`. На этом экране работает реальный инференс на загруженном файле и
предпросмотр сопоставления нескольких кадров с вручную введённым планом, если сервисы запущены и
флаг `INFERENCE_DEMO_ENABLED=true`; по умолчанию загрузка отключена. Ввод этапа, дат, зоны, камеры и
источников обязателен — готовый демонстрационный план не подставляется. Изображения на лендинге
синтетические и служат иллюстрациями, не свидетельствами. [Запуск и ограничения](docs/model-serving.md).

Live-сервис графика запускается отдельно и пока намеренно не подключён к браузерному демо:
для этого нужен авторизованный gateway/BFF и выбор OIDC-провайдера. Запуск, контракты и границы —
в [runbook сервиса графика](docs/schedule-service.md).

Старый синтетический сценарий пульта убран из пользовательских маршрутов. Его исследовательские
модули остаются в `apps/web/src/lib/demo`, но не подключены к рабочему интерфейсу. Постоянного
архива снимков, решений ревьюера, потоковых камер и отправки алертов пока нет. Ручной замер
готовности с источником можно передать в сервис предпросмотра; расхождение рассчитывается по
явно линейной модели, а не нейросетью. Результат предпросмотра можно экспортировать в JSON вместе
с источниками и хэшами кадров, без исходных изображений. [Ограничения и план развития](docs/web-masha-scope.md).

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
Если порт уже занят, его можно переопределить через `.env`, например `WEB_PORT=13000`;
для загрузки кадра также задайте `WEB_ORIGIN=http://localhost:13000`.

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
make inference-check # lint and tests for model serving
make demo-live # local real-model demo at http://127.0.0.1:5174/app/model
make demo-share # temporary secret HTTPS link to this Mac for teammates
make demo-share-status # print the current link
make demo-share-stop # revoke the link and stop local services
```

## Структура

```text
apps/
  api/              Rust/Axum control plane
  schedule/         Isolated schedule service, migration and outbox publisher
  inference/        Private YOLO + ConvNeXt serving service
  deviations/       Stateless evidence-gated rule preview (not persistent alerting)
  web/              SvelteKit operator interface
crates/
  domain/           Product language and invariants
  contracts/        HTTP/event DTOs
  platform/         Configuration, telemetry and infrastructure clients
contracts/          OpenAPI, AsyncAPI, JSON Schema and examples
migrations/         Versioned PostgreSQL/PostGIS schema
deploy/
  compose.yaml      Local full stack
  k8s/              Base manifests and dev/prod/gpu overlays
docs/
  adr/              Architecture decisions
  architecture.md   System boundaries and request/event flows
ml/
  config/           Dataset taxonomy and versioned experiment definitions
  src/sitewatch_ml/ Data quality, splitting, training and promotion pipeline
  release/          Final model package: predict.py, SHA-256, unknown threshold (weights outside Git)
research/           ML experiments: YOLO comparison, augmentations, multi-camera stage inference
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
  предупреждений. Независимая оценка переданных весов ещё не проведена.

## Модели и исследования

- [Обоснование итоговых моделей](docs/Обоснование_моделей.pdf): почему YOLO26x + ConvNeXt-small,
  отбор 35 чекпойнтов, аугментации, метрики по источникам и на архиве кейса.
- [Пакет итоговых моделей](ml/release/jepa-models-2026-09-28): `predict.py`, SHA-256, порог unknown;
  веса передаются архивом, не через Git.
- [research/](research/README.md): сравнение YOLO и zero-shot на Kaggle, доменные аугментации,
  copy-paste синтез, свои архитектуры, определение этапа по технике с нескольких камер и сверка
  с планом ([research/docs/STAGE_FUSION.md](research/docs/STAGE_FUSION.md)).
- [Демо-сцены](ml/config/demo-scenes.json): 7 серий кадров кейса для сравнения «план × кадры».

## Архитектурные правила

1. `domain` не знает о PostgreSQL, HTTP, NATS и S3.
2. PostgreSQL — источник истины. Redis не хранит данные, потеря которых ломает аудит.
3. Боевые наблюдения не проводят байты снимков через JSON или PostgreSQL: браузер загружает их
   напрямую по presigned URL. Отдельная локальная `/app/model`-песочница передаёт файл через
   серверный прокси только для разового инференса и не сохраняет его.
4. Любое предупреждение содержит снимок правила, наблюдаемый факт и ссылку на доказательства.
5. Повторный HTTP-запрос с тем же `Idempotency-Key` не создаёт дубликат.
6. Событие публикуется из transactional outbox, а consumer обязан быть идемпотентным.
7. Несовместимое изменение создаёт `/api/v2` или новый subject с суффиксом `.v2`.

Подробнее: [архитектура](docs/architecture.md) и [модель данных](docs/data-model.md).

ML-контур, от исходного архива до alias `champion`, описан в [MLOps runbook](docs/mlops.md); текущие
проверенные характеристики входного датасета — в [dataset audit](docs/dataset-audit.md).
