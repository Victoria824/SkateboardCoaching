import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Protocol

from .config import settings


class InferenceError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class PredictionOutput:
    label: str
    confidence: float
    annotation_type: str
    geometry: Dict[str, Any]


class PredictionProvider(Protocol):
    runtime_version: str

    def infer_frame(
        self, image_path: Path, model_kind: str, confidence_threshold: float, device: str
    ) -> List[PredictionOutput]:
        ...


POSE_KEYPOINTS = {
    0: "head",
    5: "left_shoulder",
    6: "right_shoulder",
    7: "left_elbow",
    8: "right_elbow",
    9: "left_wrist",
    10: "right_wrist",
    11: "left_hip",
    12: "right_hip",
    13: "left_knee",
    14: "right_knee",
    15: "left_ankle",
    16: "right_ankle",
}


class UltralyticsProvider:
    def __init__(self, model_name: str):
        config_directory = settings.media_root.parent / "ultralytics"
        config_directory.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("YOLO_CONFIG_DIR", str(config_directory))
        try:
            import ultralytics
            from ultralytics import YOLO
        except ImportError as error:
            raise InferenceError(
                "ML_DEPENDENCY_MISSING",
                "Install requirements-ml.txt to run Ultralytics inference",
            ) from error
        self.runtime_version = ultralytics.__version__
        try:
            self.model = YOLO(model_name)
        except Exception as error:
            raise InferenceError("MODEL_LOAD_FAILED", str(error)) from error

    def infer_frame(
        self, image_path: Path, model_kind: str, confidence_threshold: float, device: str
    ) -> List[PredictionOutput]:
        try:
            result = self.model.predict(
                source=str(image_path), conf=confidence_threshold, device=device, verbose=False
            )[0]
        except Exception as error:
            raise InferenceError("INFERENCE_FAILED", str(error)) from error
        if model_kind == "pose":
            return self._pose_outputs(result)
        return self._detection_outputs(result)

    @staticmethod
    def _detection_outputs(result) -> List[PredictionOutput]:
        outputs: List[PredictionOutput] = []
        if result.boxes is None:
            return outputs
        image_height, image_width = result.orig_shape
        boxes = result.boxes.xyxy.cpu().tolist()
        classes = result.boxes.cls.cpu().tolist()
        confidences = result.boxes.conf.cpu().tolist()
        for coordinates, class_id, confidence in zip(boxes, classes, confidences):
            label = str(result.names[int(class_id)])
            if label not in {"person", "snowboard"}:
                continue
            x1, y1, x2, y2 = coordinates
            outputs.append(
                PredictionOutput(
                    label="rider" if label == "person" else label,
                    confidence=float(confidence),
                    annotation_type="bbox",
                    geometry={
                        "x": max(0.0, x1 / image_width),
                        "y": max(0.0, y1 / image_height),
                        "width": min(1.0, x2 / image_width) - max(0.0, x1 / image_width),
                        "height": min(1.0, y2 / image_height) - max(0.0, y1 / image_height),
                    },
                )
            )
        return outputs

    @staticmethod
    def _pose_outputs(result) -> List[PredictionOutput]:
        outputs: List[PredictionOutput] = []
        if result.keypoints is None or result.keypoints.xyn is None:
            return outputs
        coordinates = result.keypoints.xyn.cpu().tolist()
        visibility = (
            result.keypoints.conf.cpu().tolist()
            if result.keypoints.conf is not None
            else [[1.0] * len(points) for points in coordinates]
        )
        box_confidences = (
            result.boxes.conf.cpu().tolist() if result.boxes is not None else [1.0] * len(coordinates)
        )
        for pose, point_confidences, confidence in zip(coordinates, visibility, box_confidences):
            points = []
            for index, name in POSE_KEYPOINTS.items():
                if index >= len(pose):
                    continue
                x, y = pose[index]
                point_confidence = point_confidences[index]
                if x == 0 and y == 0:
                    continue
                points.append(
                    {
                        "name": name,
                        "x": min(1.0, max(0.0, float(x))),
                        "y": min(1.0, max(0.0, float(y))),
                        "visible": float(point_confidence) >= 0.25,
                    }
                )
            if points:
                outputs.append(
                    PredictionOutput(
                        label="rider_pose",
                        confidence=float(confidence),
                        annotation_type="keypoints",
                        geometry={"points": points},
                    )
                )
        return outputs
