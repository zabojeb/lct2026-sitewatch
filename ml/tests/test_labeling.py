from pathlib import Path

from PIL import Image

from sitewatch_ml.labeling import create_label_studio_tasks


def test_label_studio_task_uses_scoped_local_file_url(tmp_path: Path) -> None:
    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (16, 16), "black").save(images / "frame.png")

    tasks = create_label_studio_tasks(images, tmp_path / "tasks.json")

    assert tasks == [
        {
            "data": {"image": "/data/local-files/?d=frame.png"},
            "meta": {"relative_path": "frame.png", "source": "organizer"},
        }
    ]
