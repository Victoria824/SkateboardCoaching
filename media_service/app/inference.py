import os
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence

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
    external_track_id: Optional[int] = None


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

    def infer_frames(
        self,
        image_paths: Sequence[Path],
        model_kind: str,
        confidence_threshold: float,
        device: str,
    ) -> List[List[PredictionOutput]]:
        """Track an ordered frame sequence while keeping Ultralytics tracker state alive."""
        sequence: List[List[PredictionOutput]] = []
        for image_path in image_paths:
            try:
                result = self.model.track(
                    source=str(image_path),
                    conf=confidence_threshold,
                    device=device,
                    verbose=False,
                    persist=True,
                    tracker="bytetrack.yaml",
                )[0]
            except Exception as error:
                raise InferenceError("INFERENCE_FAILED", str(error)) from error
            sequence.append(
                self._pose_outputs(result)
                if model_kind == "pose"
                else self._detection_outputs(result)
            )
        return self._fill_missing_track_ids(sequence)

    @staticmethod
    def _output_box(output: PredictionOutput) -> Dict[str, float]:
        if output.annotation_type == "bbox":
            return {name: float(output.geometry[name]) for name in ("x", "y", "width", "height")}
        points = output.geometry.get("points", [])
        xs = [float(point["x"]) for point in points]
        ys = [float(point["y"]) for point in points]
        if not xs or not ys:
            return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
        return {
            "x": min(xs),
            "y": min(ys),
            "width": max(0.01, max(xs) - min(xs)),
            "height": max(0.01, max(ys) - min(ys)),
        }

    @staticmethod
    def _box_similarity(first: Dict[str, float], second: Dict[str, float]) -> float:
        first_right, first_bottom = first["x"] + first["width"], first["y"] + first["height"]
        second_right = second["x"] + second["width"]
        second_bottom = second["y"] + second["height"]
        intersection = max(0.0, min(first_right, second_right) - max(first["x"], second["x"])) * max(
            0.0, min(first_bottom, second_bottom) - max(first["y"], second["y"])
        )
        union = first["width"] * first["height"] + second["width"] * second["height"] - intersection
        iou = intersection / union if union > 0 else 0.0
        first_center = (first["x"] + first["width"] / 2, first["y"] + first["height"] / 2)
        second_center = (second["x"] + second["width"] / 2, second["y"] + second["height"] / 2)
        center_distance = math.hypot(
            first_center[0] - second_center[0], first_center[1] - second_center[1]
        )
        proximity = max(0.0, 1.0 - center_distance / 0.25) * 0.7
        return max(iou, proximity)

    @staticmethod
    def _fill_missing_track_ids(
        sequence: List[List[PredictionOutput]], max_gap: int = 3
    ) -> List[List[PredictionOutput]]:
        """Preserve ByteTrack IDs and fill unconfirmed detections with short-term geometry tracks."""
        tracks: Dict[str, Dict[int, tuple]] = {}
        next_track_id = 100000
        completed: List[List[PredictionOutput]] = []
        for frame_index, outputs in enumerate(sequence):
            updated = list(outputs)
            used_ids = {
                output.external_track_id
                for output in outputs
                if output.external_track_id is not None
            }
            for output in outputs:
                if output.external_track_id is None:
                    continue
                tracks.setdefault(output.label, {})[output.external_track_id] = (
                    UltralyticsProvider._output_box(output),
                    frame_index,
                )
                next_track_id = max(next_track_id, output.external_track_id + 1)

            for output_index, output in enumerate(outputs):
                if output.external_track_id is not None:
                    continue
                box = UltralyticsProvider._output_box(output)
                candidates = []
                for track_id, (previous_box, previous_frame) in tracks.get(output.label, {}).items():
                    if track_id in used_ids or frame_index - previous_frame > max_gap:
                        continue
                    candidates.append(
                        (UltralyticsProvider._box_similarity(previous_box, box), track_id)
                    )
                best_score, best_track_id = max(candidates, default=(0.0, None))
                if best_track_id is None or best_score < 0.25:
                    best_track_id = next_track_id
                    next_track_id += 1
                updated[output_index] = replace(output, external_track_id=best_track_id)
                tracks.setdefault(output.label, {})[best_track_id] = (box, frame_index)
                used_ids.add(best_track_id)
            completed.append(updated)
        return completed

    @staticmethod
    def _track_ids(result, count: int) -> List[Optional[int]]:
        if result.boxes is None or result.boxes.id is None:
            return [None] * count
        values = result.boxes.id.cpu().tolist()
        return [int(value) for value in values]

    @staticmethod
    def _detection_outputs(result) -> List[PredictionOutput]:
        outputs: List[PredictionOutput] = []
        if result.boxes is None:
            return outputs
        image_height, image_width = result.orig_shape
        boxes = result.boxes.xyxy.cpu().tolist()
        classes = result.boxes.cls.cpu().tolist()
        confidences = result.boxes.conf.cpu().tolist()
        track_ids = UltralyticsProvider._track_ids(result, len(boxes))
        for coordinates, class_id, confidence, track_id in zip(
            boxes, classes, confidences, track_ids
        ):
            label = str(result.names[int(class_id)])
            if label not in {"person", "snowboard"}:
                continue
            x1, y1, x2, y2 = coordinates
            outputs.append(
                PredictionOutput(
                    label=label,
                    confidence=float(confidence),
                    annotation_type="bbox",
                    geometry={
                        "x": max(0.0, x1 / image_width),
                        "y": max(0.0, y1 / image_height),
                        "width": min(1.0, x2 / image_width) - max(0.0, x1 / image_width),
                        "height": min(1.0, y2 / image_height) - max(0.0, y1 / image_height),
                    },
                    external_track_id=track_id,
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
        track_ids = UltralyticsProvider._track_ids(result, len(coordinates))
        for pose, point_confidences, confidence, track_id in zip(
            coordinates, visibility, box_confidences, track_ids
        ):
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
                        external_track_id=track_id,
                    )
                )
        return outputs
