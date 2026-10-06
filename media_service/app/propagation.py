from typing import Any, Dict


BBOX_FIELDS = ("x", "y", "width", "height")


def bbox_delta(
    prediction_geometry: Dict[str, Any], corrected_geometry: Dict[str, Any]
) -> Dict[str, float]:
    return {
        field: float(corrected_geometry[field]) - float(prediction_geometry[field])
        for field in BBOX_FIELDS
    }


def apply_bbox_delta(
    geometry: Dict[str, Any], delta: Dict[str, float]
) -> Dict[str, float]:
    width = min(1.0, max(0.005, float(geometry["width"]) + delta["width"]))
    height = min(1.0, max(0.005, float(geometry["height"]) + delta["height"]))
    x = min(1.0 - width, max(0.0, float(geometry["x"]) + delta["x"]))
    y = min(1.0 - height, max(0.0, float(geometry["y"]) + delta["y"]))
    return {"x": x, "y": y, "width": width, "height": height}


def has_correction(delta: Dict[str, float], tolerance: float = 1e-6) -> bool:
    return any(abs(value) > tolerance for value in delta.values())
