import os
import inspect
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
        if model_kind == "segmentation":
            return self._segmentation_outputs(result)
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
            if model_kind == "pose":
                outputs = self._pose_outputs(result)
            elif model_kind == "segmentation":
                outputs = self._segmentation_outputs(result)
            else:
                outputs = self._detection_outputs(result)
            sequence.append(outputs)
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

    @staticmethod
    def _segmentation_outputs(result) -> List[PredictionOutput]:
        """Return normalized snowboard instance polygons from an Ultralytics seg result."""
        outputs: List[PredictionOutput] = []
        if result.boxes is None or result.masks is None or result.masks.xyn is None:
            return outputs
        polygons = result.masks.xyn
        classes = result.boxes.cls.cpu().tolist()
        confidences = result.boxes.conf.cpu().tolist()
        track_ids = UltralyticsProvider._track_ids(result, len(polygons))
        for polygon, class_id, confidence, track_id in zip(
            polygons, classes, confidences, track_ids
        ):
            if str(result.names[int(class_id)]) != "snowboard":
                continue
            raw_points = polygon.tolist() if hasattr(polygon, "tolist") else polygon
            points = [
                {
                    "x": min(1.0, max(0.0, float(point[0]))),
                    "y": min(1.0, max(0.0, float(point[1]))),
                }
                for point in raw_points
            ]
            if len(points) < 3:
                continue
            outputs.append(
                PredictionOutput(
                    label="snowboard",
                    confidence=float(confidence),
                    annotation_type="polygon",
                    geometry={"points": points},
                    external_track_id=track_id,
                )
            )
        return outputs


class OpenCVPIIProvider:
    """Detect faces/plates with OpenCV cascades and common screen devices with YOLO."""

    def __init__(self, screen_model_name: str = settings.pii_screen_model):
        try:
            import cv2
            import ultralytics
            from ultralytics import YOLO
        except ImportError as error:
            raise InferenceError(
                "ML_DEPENDENCY_MISSING",
                "Install requirements-ml.txt to run PII inference",
            ) from error
        self.cv2 = cv2
        self.runtime_version = "opencv-{}+ultralytics-{}".format(
            cv2.__version__, ultralytics.__version__
        )
        cascade_root = Path(cv2.data.haarcascades)
        self.face = cv2.CascadeClassifier(str(cascade_root / "haarcascade_frontalface_default.xml"))
        self.plate = cv2.CascadeClassifier(str(cascade_root / "haarcascade_russian_plate_number.xml"))
        if self.face.empty() or self.plate.empty():
            raise InferenceError("MODEL_LOAD_FAILED", "OpenCV PII cascades are unavailable")
        try:
            self.screen_model = YOLO(screen_model_name)
        except Exception as error:
            raise InferenceError("MODEL_LOAD_FAILED", str(error)) from error

    @staticmethod
    def _geometry(x: float, y: float, width: float, height: float, image_width: int, image_height: int):
        return {
            "x": max(0.0, x / image_width),
            "y": max(0.0, y / image_height),
            "width": min(1.0, (x + width) / image_width) - max(0.0, x / image_width),
            "height": min(1.0, (y + height) / image_height) - max(0.0, y / image_height),
        }

    def infer_frame(
        self, image_path: Path, model_kind: str, confidence_threshold: float, device: str
    ) -> List[PredictionOutput]:
        image = self.cv2.imread(str(image_path))
        if image is None:
            raise InferenceError("INVALID_FRAME", "Unable to read {}".format(image_path))
        image_height, image_width = image.shape[:2]
        gray = self.cv2.cvtColor(image, self.cv2.COLOR_BGR2GRAY)
        outputs: List[PredictionOutput] = []
        for label, detector, confidence in (
            ("face", self.face, 0.90),
            ("license_plate", self.plate, 0.80),
        ):
            for x, y, width, height in detector.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4, minSize=(20, 20)
            ):
                if confidence >= confidence_threshold:
                    outputs.append(
                        PredictionOutput(
                            label=label,
                            confidence=confidence,
                            annotation_type="bbox",
                            geometry=self._geometry(
                                x, y, width, height, image_width, image_height
                            ),
                        )
                    )
        try:
            result = self.screen_model.predict(
                source=str(image_path), conf=confidence_threshold, device=device, verbose=False
            )[0]
        except Exception as error:
            raise InferenceError("INFERENCE_FAILED", str(error)) from error
        if result.boxes is not None:
            for coordinates, class_id, confidence in zip(
                result.boxes.xyxy.cpu().tolist(),
                result.boxes.cls.cpu().tolist(),
                result.boxes.conf.cpu().tolist(),
            ):
                if str(result.names[int(class_id)]).lower() not in {"tv", "laptop", "cell phone"}:
                    continue
                x1, y1, x2, y2 = coordinates
                outputs.append(
                    PredictionOutput(
                        label="screen",
                        confidence=float(confidence),
                        annotation_type="bbox",
                        geometry=self._geometry(
                            x1, y1, x2 - x1, y2 - y1, image_width, image_height
                        ),
                    )
                )
        return outputs

    def infer_frames(
        self,
        image_paths: Sequence[Path],
        model_kind: str,
        confidence_threshold: float,
        device: str,
    ) -> List[List[PredictionOutput]]:
        sequence = [
            self.infer_frame(path, model_kind, confidence_threshold, device)
            for path in image_paths
        ]
        return UltralyticsProvider._fill_missing_track_ids(sequence, max_gap=3)


class GroundingDinoPIIProvider:
    """Independent open-vocabulary residual scanner backed by Grounding DINO."""

    provider_name = "huggingface-transformers-grounding-dino"
    prompt_labels = {
        "a human face": "face",
        "a vehicle license plate": "license_plate",
        "a computer monitor screen": "screen",
        "a laptop screen": "screen",
        "a smartphone screen": "screen",
    }

    def __init__(self, model_name: str, revision: str, device: str = "cpu"):
        # Keep weights on the shared worker staging volume so multiple workers reuse one snapshot.
        cache_directory = settings.media_root / ".cache" / "huggingface"
        cache_directory.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(cache_directory))
        try:
            import torch
            import transformers
            from PIL import Image
            from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        except ImportError as error:
            raise InferenceError(
                "ML_DEPENDENCY_MISSING",
                "Install requirements-ml.txt to run Grounding DINO residual inference",
            ) from error
        self.torch = torch
        self.Image = Image
        self.model_name = model_name
        self.model_revision = revision
        self.device = device
        self.runtime_version = "transformers-{}:{}@{}".format(
            transformers.__version__, model_name, revision
        )
        try:
            self.processor = AutoProcessor.from_pretrained(
                model_name, revision=revision, trust_remote_code=False
            )
            self.model = AutoModelForZeroShotObjectDetection.from_pretrained(
                model_name,
                revision=revision,
                trust_remote_code=False,
                use_safetensors=True,
            ).to(device)
            resolved_revision = getattr(self.model.config, "_commit_hash", None)
            if resolved_revision and resolved_revision != revision:
                raise ValueError(
                    "Resolved model revision {} does not match pinned {}".format(
                        resolved_revision, revision
                    )
                )
            self.model.eval()
            parameters = inspect.signature(
                self.processor.post_process_grounded_object_detection
            ).parameters
            self._box_threshold_parameter = (
                "box_threshold" if "box_threshold" in parameters else "threshold"
            )
        except Exception as error:
            raise InferenceError("MODEL_LOAD_FAILED", str(error)) from error

    @staticmethod
    def _canonical_label(text_label: str) -> Optional[str]:
        normalized = str(text_label).lower().strip().rstrip(".")
        if "license plate" in normalized or "number plate" in normalized:
            return "license_plate"
        if "face" in normalized:
            return "face"
        if any(value in normalized for value in ("screen", "monitor", "smartphone")):
            return "screen"
        return None

    @staticmethod
    def _iou(first: PredictionOutput, second: PredictionOutput) -> float:
        a, b = first.geometry, second.geometry
        left = max(float(a["x"]), float(b["x"]))
        top = max(float(a["y"]), float(b["y"]))
        right = min(float(a["x"]) + float(a["width"]), float(b["x"]) + float(b["width"]))
        bottom = min(float(a["y"]) + float(a["height"]), float(b["y"]) + float(b["height"]))
        intersection = max(0.0, right - left) * max(0.0, bottom - top)
        union = (
            float(a["width"]) * float(a["height"])
            + float(b["width"]) * float(b["height"])
            - intersection
        )
        return intersection / union if union > 0 else 0.0

    @classmethod
    def _deduplicate(cls, outputs: List[PredictionOutput], threshold: float = 0.7):
        kept: List[PredictionOutput] = []
        for candidate in sorted(outputs, key=lambda item: item.confidence, reverse=True):
            if any(
                candidate.label == existing.label and cls._iou(candidate, existing) >= threshold
                for existing in kept
            ):
                continue
            kept.append(candidate)
        return kept

    def infer_frame(
        self, image_path: Path, model_kind: str, confidence_threshold: float, device: str
    ) -> List[PredictionOutput]:
        try:
            image = self.Image.open(image_path).convert("RGB")
            prompt = ". ".join(self.prompt_labels) + "."
            inputs = self.processor(images=image, text=prompt, return_tensors="pt").to(self.device)
            with self.torch.no_grad():
                raw_outputs = self.model(**inputs)
            post_process_arguments = {
                self._box_threshold_parameter: confidence_threshold,
                "text_threshold": confidence_threshold,
                "target_sizes": [image.size[::-1]],
            }
            result = self.processor.post_process_grounded_object_detection(
                raw_outputs, inputs.input_ids, **post_process_arguments
            )[0]
        except Exception as error:
            raise InferenceError("INFERENCE_FAILED", str(error)) from error
        image_width, image_height = image.size
        text_labels = result.get("text_labels")
        if text_labels is None:
            text_labels = result.get("labels")
        if text_labels is None:
            text_labels = []
        outputs = []
        for box, score, text_label in zip(result["boxes"], result["scores"], text_labels):
            label = self._canonical_label(text_label)
            if label is None:
                continue
            coordinates = box.detach().cpu().tolist() if hasattr(box, "detach") else list(box)
            confidence = float(score.detach().cpu().item()) if hasattr(score, "detach") else float(score)
            x1, y1, x2, y2 = coordinates
            outputs.append(
                PredictionOutput(
                    label=label,
                    confidence=confidence,
                    annotation_type="bbox",
                    geometry=OpenCVPIIProvider._geometry(
                        x1, y1, x2 - x1, y2 - y1, image_width, image_height
                    ),
                )
            )
        return self._deduplicate(outputs)

    def infer_frames(
        self,
        image_paths: Sequence[Path],
        model_kind: str,
        confidence_threshold: float,
        device: str,
    ) -> List[List[PredictionOutput]]:
        return [
            self.infer_frame(path, model_kind, confidence_threshold, device)
            for path in image_paths
        ]


def create_residual_pii_provider() -> PredictionProvider:
    """Build the configured release-gate detector; unknown choices fail closed."""
    if settings.residual_pii_provider == "grounding-dino":
        return GroundingDinoPIIProvider(
            settings.residual_pii_model,
            settings.residual_pii_model_revision,
            settings.residual_pii_device,
        )
    if settings.residual_pii_provider == "opencv-yolo":
        return OpenCVPIIProvider(settings.pii_screen_model)
    raise InferenceError(
        "INVALID_RESIDUAL_PROVIDER",
        "Unsupported residual PII provider: {}".format(settings.residual_pii_provider),
    )
