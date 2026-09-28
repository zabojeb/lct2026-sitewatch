"""Private HTTP adapter for synchronous image inference."""

import asyncio
import hmac
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from .model import InferenceEngine, PredictionError
from .settings import Settings


def create_app(settings: Settings | None = None, engine: InferenceEngine | None = None) -> FastAPI:
    config = settings or Settings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = engine or await run_in_threadpool(InferenceEngine, config)
        app.state.predict_lock = asyncio.Lock()
        yield
        app.state.engine = None

    app = FastAPI(
        title="SiteWatch private inference",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        if getattr(app.state, "engine", None) is None:
            raise HTTPException(status_code=503, detail="Model unavailable")
        return {"status": "ready", "model_version": app.state.engine.model_version}

    @app.post("/v1/predict")
    async def predict(
        image: Annotated[UploadFile, File()],
        authorization: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        candidate = authorization.removeprefix("Bearer ") if authorization else ""
        if (
            not authorization
            or not authorization.startswith("Bearer ")
            or not hmac.compare_digest(candidate, config.internal_token)
        ):
            raise HTTPException(status_code=401, detail="Unauthorized")
        if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(status_code=415, detail="JPEG, PNG or WebP image required")
        data = await image.read(config.max_upload_bytes + 1)
        if len(data) > config.max_upload_bytes:
            raise HTTPException(status_code=413, detail="Image exceeds upload limit")
        try:
            async with app.state.predict_lock:
                result = await run_in_threadpool(app.state.engine.predict, data)
        except PredictionError as exc:
            raise HTTPException(status_code=422, detail=exc.message) from exc
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    return app
