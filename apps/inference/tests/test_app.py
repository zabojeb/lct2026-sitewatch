import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from sitewatch_inference.app import create_app
from sitewatch_inference.settings import Settings


class FakeEngine:
    model_version = "test-detector+test-classifier"

    def predict(self, image: bytes, recognition_mode: str = "640") -> dict[str, object]:
        assert image
        return {
            "schema": "sitewatch.inference.v1",
            "recognition_mode": recognition_mode,
            "detections": [],
        }


class BrokenEngine(FakeEngine):
    def predict(self, image: bytes, recognition_mode: str = "640") -> dict[str, object]:
        raise AssertionError("cached frames must not reach the models")


def settings(cache_dir: Path | None = None) -> Settings:
    return Settings(
        Path("unused-640.pt"),
        Path("unused-960.pt"),
        Path("unused.pth"),
        Path("reject.json"),
        "t" * 32,
        cache_dir=cache_dir,
    )


def client(cache_dir: Path | None = None) -> TestClient:
    return TestClient(create_app(settings(cache_dir), FakeEngine()))


def test_authentication_and_health() -> None:
    with client() as api:
        assert api.get("/health/live").status_code == 200
        assert api.get("/health/ready").json()["model_version"] == FakeEngine.model_version
        assert api.get("/health/ready").json()["recognition_modes"] == ["640", "960"]
        assert (
            api.post("/v1/predict", files={"image": ("test.jpg", b"abc", "image/jpeg")}).status_code
            == 401
        )


def test_upload_validation_and_prediction() -> None:
    output = io.BytesIO()
    Image.new("RGB", (12, 12)).save(output, format="JPEG")
    headers = {"Authorization": f"Bearer {'t' * 32}"}
    with client() as api:
        assert (
            api.post(
                "/v1/predict", headers=headers, files={"image": ("test.txt", b"text", "text/plain")}
            ).status_code
            == 415
        )
        result = api.post(
            "/v1/predict",
            headers=headers,
            files={"image": ("test.jpg", output.getvalue(), "image/jpeg")},
            data={"recognition_mode": "960"},
        )
        assert result.status_code == 200
        assert result.json()["schema"] == "sitewatch.inference.v1"
        assert result.json()["recognition_mode"] == "960"
        assert result.headers["cache-control"] == "no-store"
        assert (
            api.post(
                "/v1/predict",
                headers=headers,
                files={"image": ("test.jpg", output.getvalue(), "image/jpeg")},
                data={"recognition_mode": "unsupported"},
            ).status_code
            == 422
        )


def test_results_survive_restart(tmp_path: Path) -> None:
    output = io.BytesIO()
    Image.new("RGB", (12, 12)).save(output, format="JPEG")
    headers = {"Authorization": f"Bearer {'t' * 32}"}
    upload = {"image": ("test.jpg", output.getvalue(), "image/jpeg")}
    with client(tmp_path) as api:
        first = api.post(
            "/v1/predict", headers=headers, files=upload, data={"recognition_mode": "960"}
        )
    with TestClient(create_app(settings(tmp_path), BrokenEngine())) as api:
        again = api.post(
            "/v1/predict", headers=headers, files=upload, data={"recognition_mode": "960"}
        )
    assert again.status_code == 200
    assert again.json() == first.json()
