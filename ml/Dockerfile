FROM ghcr.io/astral-sh/uv:0.11.7 AS uv

FROM python:3.12.12-slim-bookworm
COPY --from=uv /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/workspace/ml/.venv/bin:$PATH"

ARG SITEWATCH_CODE_REVISION=uncommitted
ENV SITEWATCH_CODE_REVISION=${SITEWATCH_CODE_REVISION}

WORKDIR /workspace/ml
COPY ml/pyproject.toml ml/uv.lock ml/README.md ./
RUN uv sync --frozen --no-dev --extra orchestration --no-install-project

COPY ml/ ./
RUN uv sync --frozen --no-dev --extra orchestration \
    && chown -R 65532:65532 /workspace/ml

USER 65532:65532
CMD ["dagster", "api", "grpc-health-check", "-p", "4000"]
