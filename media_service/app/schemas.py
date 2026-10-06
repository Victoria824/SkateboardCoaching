from datetime import datetime
import math
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    video_id: str
    frame_number: int
    timestamp_ms: int
    image_url: str
    width: Optional[int] = None
    height: Optional[int] = None


class VideoResponse(BaseModel):
    id: str
    filename: str
    mime_type: Optional[str]
    file_size: int
    duration_ms: Optional[int]
    fps: Optional[float]
    width: Optional[int]
    height: Optional[int]
    codec: Optional[str]
    source_frame_count: Optional[int]
    sampling_profile: str
    sample_fps: float
    status: str
    created_at: datetime
    frames: List[FrameResponse] = Field(default_factory=list)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    video_id: str
    state: str
    progress: int
    attempts: int
    max_attempts: int
    error_code: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class SanitizedExportRequest(BaseModel):
    task_id: str
    reviewer: str = Field(min_length=1, max_length=255)
    labels: List[Literal["face", "license_plate", "screen"]] = Field(
        default_factory=lambda: ["face", "license_plate", "screen"]
    )


class SanitizedExportResponse(BaseModel):
    id: str
    video_id: str
    task_id: str
    status: str
    labels: List[str]
    source_annotation_count: int
    video_url: Optional[str]
    manifest_url: Optional[str]
    output_sha256: Optional[str]
    reviewer: Optional[str]
    processing_ms: Optional[int]
    error_code: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


class SanitizedExportCreatedResponse(BaseModel):
    sanitized_export: SanitizedExportResponse
    job: JobResponse


class UploadResponse(BaseModel):
    video: VideoResponse
    job: JobResponse


class AnnotationInput(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    annotation_type: Literal["bbox", "keypoints"]
    geometry: Dict[str, Any]
    source: Literal["human", "model", "model_corrected", "track_propagated"] = "human"
    model_prediction_id: Optional[str] = None
    propagation_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_geometry(self):
        if self.annotation_type == "bbox":
            required = ("x", "y", "width", "height")
            if any(name not in self.geometry for name in required):
                raise ValueError("Bounding boxes require x, y, width, and height")
            values = {name: self.geometry[name] for name in required}
            if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in values.values()):
                raise ValueError("Bounding box coordinates must be finite numbers")
            if values["width"] <= 0 or values["height"] <= 0:
                raise ValueError("Bounding box dimensions must be positive")
            if values["x"] < 0 or values["y"] < 0 or values["x"] + values["width"] > 1 or values["y"] + values["height"] > 1:
                raise ValueError("Bounding box coordinates must be normalized to the image")
        else:
            points = self.geometry.get("points")
            if not isinstance(points, list) or not points:
                raise ValueError("Keypoint geometry requires a non-empty points array")
            for point in points:
                if not isinstance(point, dict) or not isinstance(point.get("name"), str):
                    raise ValueError("Each keypoint requires a name")
                x, y = point.get("x"), point.get("y")
                if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not 0 <= x <= 1 or not 0 <= y <= 1:
                    raise ValueError("Keypoint coordinates must be normalized to the image")
        return self


class AnnotationSaveRequest(BaseModel):
    annotations: List[AnnotationInput]
    duration_ms: Optional[int] = Field(default=None, ge=0)


class AnnotationResponse(AnnotationInput):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    frame_id: str
    created_at: datetime
    updated_at: datetime


class AnnotationTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    video_id: str
    assigned_to: Optional[str]
    status: str
    priority: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


class AnnotationTaskDetail(AnnotationTaskResponse):
    video: VideoResponse


class AnnotationSaveResponse(BaseModel):
    annotations: List[AnnotationResponse]
    saved_count: int


class ModelRunRequest(BaseModel):
    model_kind: Literal["detection", "pose", "pii"] = "detection"
    provider: Literal["ultralytics", "opencv+ultralytics"] = "ultralytics"
    model_name: Optional[str] = None
    model_version: str = "pretrained"
    device: str = "cpu"
    confidence_threshold: float = Field(default=0.25, ge=0, le=1)


class ModelRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    video_id: str
    model_kind: str
    provider: str
    model_name: str
    model_version: str
    device: str
    parameters: Dict[str, Any]
    status: str
    total_frames: int
    processed_frames: int
    latency_ms: Optional[int]
    error_code: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class ModelRunCreatedResponse(BaseModel):
    model_run: ModelRunResponse
    job: JobResponse


class ModelPredictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model_run_id: str
    frame_id: str
    label: str
    confidence: float
    annotation_type: str
    geometry: Dict[str, Any]
    track_id: Optional[str]
    associated_prediction_id: Optional[str]
    association_score: Optional[float]
    association_ambiguous: bool
    status: str
    model_name: str
    model_version: str
    created_at: datetime
    resolved_at: Optional[datetime]


class PredictionRejectRequest(BaseModel):
    task_id: str
    duration_ms: Optional[int] = Field(default=None, ge=0)


class PredictionDecisionResponse(BaseModel):
    prediction_id: str
    status: str


class TrackPropagationRequest(BaseModel):
    task_id: str
    start_frame_number: int = Field(ge=1)
    end_frame_number: int = Field(ge=1)
    geometry: Dict[str, Any]
    reviewer: Optional[str] = Field(default=None, max_length=255)
    duration_ms: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_propagation(self):
        if self.start_frame_number > self.end_frame_number:
            raise ValueError("start_frame_number must not exceed end_frame_number")
        AnnotationInput(
            label="propagated",
            annotation_type="bbox",
            geometry=self.geometry,
            source="model_corrected",
        )
        return self


class TrackPropagationResponse(BaseModel):
    propagation_id: str
    track_id: str
    start_frame_number: int
    end_frame_number: int
    generated_count: int
    corrected: bool
    frame_ids: List[str]


class ModelMetricsResponse(BaseModel):
    model_run_id: str
    total_predictions: int
    pending: int
    accepted: int
    corrected: int
    rejected: int
    acceptance_rate: float
    correction_rate: float
    rejection_rate: float
    average_decision_time_ms: Optional[float]
    by_label: Dict[str, Dict[str, int]]


class ReviewItemResponse(BaseModel):
    id: str
    video_id: str
    frame_id: str
    model_run_id: str
    prediction_id: Optional[str]
    reason: str
    severity: str
    status: str
    score: Optional[float]
    details: Dict[str, Any]
    frame_number: int
    timestamp_ms: int
    image_url: str
    prediction_label: Optional[str]
    prediction_confidence: Optional[float]
    prediction_track_id: Optional[str]
    association_score: Optional[float]
    annotation_task_id: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]


class ReviewResolveRequest(BaseModel):
    action: Literal["APPROVED", "DISMISSED", "ESCALATED", "NEEDS_CORRECTION"]
    reviewer: Optional[str] = Field(default=None, max_length=255)
    note: Optional[str] = Field(default=None, max_length=2000)


class AgreementResponse(BaseModel):
    video_id: Optional[str]
    bbox_comparisons: int
    mean_bbox_iou: Optional[float]
    keypoint_comparisons: int
    mean_keypoint_pck: Optional[float]


class DatasetHealthResponse(BaseModel):
    video_id: Optional[str]
    videos: int
    frames: int
    annotated_frames: int
    propagated_annotations: int
    propagation_operations: int
    reviewed_frames: int
    pending_tasks: int
    completed_tasks: int
    total_predictions: int
    accepted_predictions: int
    corrected_predictions: int
    rejected_predictions: int
    pending_predictions: int
    model_acceptance_rate: float
    model_correction_rate: float
    model_rejection_rate: float
    low_confidence_predictions: int
    tracked_predictions: int
    tracks: int
    associated_snowboards: int
    unassociated_snowboards: int
    open_review_items: int
    resolved_review_items: int
    average_annotation_time_ms: Optional[float]
    annotation_throughput_per_hour: Optional[float]
    label_distribution: Dict[str, int]
    review_reason_distribution: Dict[str, int]
    agreement: AgreementResponse
