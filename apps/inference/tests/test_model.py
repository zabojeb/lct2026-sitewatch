import io

import numpy as np
import pytest
from PIL import Image

from sitewatch_inference.model import PredictionError, decode_image, letterbox_crop, normalized_box


def test_letterbox_matches_supplied_preprocessing() -> None:
    image = np.full((100, 200, 3), (255, 0, 0), dtype=np.uint8)
    result = letterbox_crop(image, 224, np.zeros(3, dtype=np.float32), np.ones(3, dtype=np.float32))
    assert result.shape == (3, 224, 224)
    assert result[0, 112, 112] == pytest.approx(1.0)
    assert result[0, 0, 0] == pytest.approx(114 / 255)


def test_exif_transpose_before_inference() -> None:
    image = Image.new("RGB", (4, 2), "red")
    metadata = Image.Exif()
    metadata[274] = 6
    output = io.BytesIO()
    image.save(output, format="JPEG", exif=metadata)
    assert decode_image(output.getvalue(), 100).shape[:2] == (4, 2)


def test_invalid_and_oversized_image_rejected() -> None:
    with pytest.raises(PredictionError):
        decode_image(b"not an image", 100)
    output = io.BytesIO()
    Image.new("RGB", (11, 10)).save(output, format="PNG")
    with pytest.raises(PredictionError):
        decode_image(output.getvalue(), 100)


def test_bbox_is_normalized_and_invalid_boxes_removed() -> None:
    assert normalized_box([-5, 10, 110, 40], 100, 50) == {
        "x_min": 0,
        "y_min": 0.2,
        "x_max": 1,
        "y_max": 0.8,
    }
    assert normalized_box([10, 10, 10, 40], 100, 50) is None
    assert normalized_box([float("nan"), 10, 20, 40], 100, 50) is None
