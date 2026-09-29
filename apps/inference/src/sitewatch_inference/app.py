"""Private HTTP adapter for synchronous image inference."""

import asyncio
import hashlib
import hmac
import json
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from .model import InferenceEngine, PredictionError
from .settings import CLASSIFIER_SHA256, DETECTOR_SHA256, REJECT_SHA256, Settings

RESULT_CACHE_SIZE = 512


def cache_folder(config: Settings) -> Path | None:
    """Disk copy of the results, one folder per set of pinned weights and detector limits."""
    if config.cache_dir is None:
        return None
    pinned = [
        DETECTOR_SHA256,
        CLASSIFIER_SHA256,
        REJECT_SHA256,
        config.detection_score,
        config.max_detections,
        config.max_image_pixels,
    ]
    return (
        config.cache_dir
        / hashlib.sha256(json.dumps(pinned, sort_keys=True).encode()).hexdigest()[:16]
    )


def load_results(folder: Path | None) -> OrderedDict:
    results: OrderedDict = OrderedDict()
    if folder is None or not folder.is_dir():
        return results
    files = sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime)
    for path in files[-RESULT_CACHE_SIZE:]:
        digest, _, mode = path.stem.rpartition("-")
        try:
            results[(digest, mode)] = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
    return results


def save_result(folder: Path | None, key: tuple[str, str], result: dict) -> None:
    if folder is None:
        return
    try:
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / f".{key[0]}-{key[1]}.tmp"
        temporary.write_text(json.dumps(result))
        temporary.replace(folder / f"{key[0]}-{key[1]}.json")
    except OSError:
        pass  # the disk copy only speeds up restarts; a prediction must not fail because of it


def create_app(settings: Settings | None = None, engine: InferenceEngine | None = None) -> FastAPI:
    config = settings or Settings.from_environment()
    folder = cache_folder(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = engine or await run_in_threadpool(InferenceEngine, config)
        app.state.predict_lock = asyncio.Lock()
        # Same bytes and mode give the same answer: repeated frames skip the models.
        app.state.results = load_results(folder)
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
    def ready() -> dict[str, object]:
        if getattr(app.state, "engine", None) is None:
            raise HTTPException(status_code=503, detail="Model unavailable")
        return {
            "status": "ready",
            "model_version": app.state.engine.model_version,
            "recognition_modes": ["640", "960"],
        }

    @app.post("/v1/predict")
    async def predict(
        image: Annotated[UploadFile, File()],
        recognition_mode: Annotated[Literal["640", "960"], Form()] = "640",
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
        key = (hashlib.sha256(data).hexdigest(), recognition_mode)
        cached = app.state.results.get(key)
        if cached is not None:
            app.state.results.move_to_end(key)
            return JSONResponse(cached, headers={"Cache-Control": "no-store"})
        try:
            async with app.state.predict_lock:
                result = await run_in_threadpool(app.state.engine.predict, data, recognition_mode)
        except PredictionError as exc:
            raise HTTPException(status_code=422, detail=exc.message) from exc
        app.state.results[key] = result
        save_result(folder, key, result)
        if len(app.state.results) > RESULT_CACHE_SIZE:
            app.state.results.popitem(last=False)
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    return app
