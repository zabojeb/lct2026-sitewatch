FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_PROGRESS=1 \
    YOLO_CONFIG_DIR=/tmp

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.22 /uv /usr/local/bin/uv
WORKDIR /app
COPY apps/inference/pyproject.toml apps/inference/uv.lock ./
COPY apps/inference/src ./src
RUN uv sync --frozen --no-dev --extra serve --no-install-project \
    && uv sync --frozen --no-dev --extra serve
RUN useradd --uid 10001 --create-home inference
USER inference
ENV PATH=/app/.venv/bin:$PATH
EXPOSE 8083
CMD ["uvicorn", "sitewatch_inference.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8083", "--workers", "1"]
