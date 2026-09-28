import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from sitewatch_inference.app import create_app
from sitewatch_inference.settings import Settings


class FakeEngine:
    model_version = "test-detector+test-classifier"

    def predict(self, image: bytes) -> dict[str, object]:
        assert image
        return {"schema": "sitewatch.inference.v1", "detections": []}


def client() -> TestClient:
    settings = Settings(Path("unused.pt"), Path("unused.pth"), "t" * 32)
    return TestClient(create_app(settings, FakeEngine()))


def test_authentication_and_health() -> None:
    with client() as api:
        assert api.get("/health/live").status_code == 200
        assert api.get("/health/ready").json()["model_version"] == FakeEngine.model_version
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
        )
        assert result.status_code == 200
        assert result.json()["schema"] == "sitewatch.inference.v1"
        assert result.headers["cache-control"] == "no-store"
