from types import SimpleNamespace

import pytest

from scripts.export_pii_gold_manifest import normalized_bbox


def test_gold_export_uses_tight_bbox_from_privacy_mask():
    annotation = SimpleNamespace(
        id="mask-1",
        annotation_type="mask",
        geometry={
            "encoding": "row-major-rle-v1",
            "width": 128,
            "height": 128,
            "rle": [100, 20, 16264],
            "bbox": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        },
    )

    assert normalized_bbox(annotation) == {
        "x": 0.1,
        "y": 0.2,
        "width": 0.3,
        "height": 0.4,
    }


def test_gold_export_rejects_out_of_bounds_geometry():
    annotation = SimpleNamespace(
        id="box-1",
        annotation_type="bbox",
        geometry={"x": 0.9, "y": 0.2, "width": 0.2, "height": 0.4},
    )

    with pytest.raises(ValueError, match="invalid normalized geometry"):
        normalized_bbox(annotation)
