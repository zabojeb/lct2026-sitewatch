.DEFAULT_GOAL := help

.PHONY: help bootstrap dev infra-up infra-down check fmt test contracts db-migrate k8s-validate \
	ml-bootstrap ml-check ml-data ml-import-labels mlops-up labeling-up mlops-down inference-check \
	demo-live demo-share demo-share-status demo-share-stop

help:
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z_-]+:.*## / {printf "%-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

bootstrap: ## Install frontend dependencies and generate typed API contracts
	pnpm install
	pnpm contracts:generate

ml-bootstrap: ## Install the locked ML development and data toolchain
	cd ml && uv sync --frozen --group dev --extra data

ml-check: ## Lint, type-check and test the ML pipeline
	cd ml && uv run ruff check src tests
	cd ml && uv run ruff format --check src tests
	cd ml && uv run pyright
	cd ml && uv run pytest
	cd ml && uv run --extra orchestration dagster definitions validate \
		-m sitewatch_ml.orchestration.definitions

inference-check: ## Lint and test the private model-serving service
	cd apps/inference && uv sync --frozen --group dev --extra serve
	cd apps/inference && uv run ruff check src tests
	cd apps/inference && uv run ruff format --check src tests
	cd apps/inference && uv run pytest -q

demo-live: ## Run the real-model local demo at http://127.0.0.1:5174/app/model
	bash scripts/demo-live.sh

demo-share: ## Start a protected temporary HTTPS link to the Mac-hosted demo
	bash scripts/demo-share-control.sh start

demo-share-status: ## Print the current temporary share link
	bash scripts/demo-share-control.sh status

demo-share-stop: ## Stop the temporary share link and local demo services
	bash scripts/demo-share-control.sh stop

ml-data: ## Reproduce ingestion, audit, safe split and labeling tasks with DVC
	cd ml && uv run --extra data dvc repro ../dvc.yaml
	cd ml && uv run sitewatch-ml experiment-audit

ml-import-labels: ## Import LABEL_EXPORT into YOLO and rerun data quality gates
	test -n "$(LABEL_EXPORT)" || (echo "usage: make ml-import-labels LABEL_EXPORT=/path/export.json"; exit 2)
	cd ml && uv run sitewatch-ml import-labels --export "$(LABEL_EXPORT)"
	cd ml && uv run --extra data dvc add ../data/ml/annotations
	cd ml && uv run --extra data dvc repro ../dvc.yaml
	cd ml && uv run sitewatch-ml experiment-audit

mlops-up: ## Start MLflow and Dagster with PostgreSQL and MinIO
	docker compose -f deploy/compose.yaml --profile mlops up -d --build \
		mlops-postgres minio minio-init mlflow dagster-webserver dagster-daemon

labeling-up: ## Start the pinned Label Studio annotator
	docker compose -f deploy/compose.yaml --profile labeling up -d label-studio

mlops-down: ## Stop local containers while preserving their volumes
	docker compose -f deploy/compose.yaml down

infra-up: ## Start PostgreSQL, Redis, NATS and MinIO
	docker compose -f deploy/compose.yaml up -d postgres redis nats minio minio-init

infra-down: ## Stop local infrastructure
	docker compose -f deploy/compose.yaml down

dev: ## Start the Rust API and SvelteKit UI
	docker compose -f deploy/compose.yaml up --build api web

fmt: ## Format Rust and frontend sources
	cargo fmt --all
	pnpm format

check: ## Run static checks for every workspace
	cargo clippy --workspace --all-targets --all-features -- -D warnings
	pnpm contracts:lint
	pnpm check
	$(MAKE) ml-check

test: ## Run unit tests
	cargo test --workspace

contracts: ## Validate OpenAPI and regenerate the TypeScript client types
	pnpm contracts:lint
	pnpm contracts:generate

db-migrate: ## Apply PostgreSQL migrations
	cargo run -p sitewatch-api --bin migrate

k8s-validate: ## Render both Kubernetes overlays
	kubectl kustomize deploy/k8s/overlays/dev >/dev/null
	kubectl kustomize deploy/k8s/overlays/prod >/dev/null
	kubectl kustomize deploy/k8s/overlays/gpu >/dev/null
	kubectl kustomize deploy/k8s/jobs >/dev/null
