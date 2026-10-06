import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.utcnow()


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(Text, unique=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    codec: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_frame_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sampling_profile: Mapped[str] = mapped_column(String(50), default="overview", index=True)
    sample_fps: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(50), default="UPLOADING", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    frames: Mapped[List["Frame"]] = relationship(
        back_populates="video", cascade="all, delete-orphan", order_by="Frame.frame_number"
    )
    jobs: Mapped[List["ProcessingJob"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    annotation_tasks: Mapped[List["AnnotationTask"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    model_runs: Mapped[List["ModelRun"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    review_items: Mapped[List["ReviewItem"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class Frame(Base):
    __tablename__ = "frames"
    __table_args__ = (UniqueConstraint("video_id", "frame_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    frame_number: Mapped[int] = mapped_column(Integer)
    timestamp_ms: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(Text, unique=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    video: Mapped[Video] = relationship(back_populates="frames")
    annotations: Mapped[List["Annotation"]] = relationship(
        back_populates="frame", cascade="all, delete-orphan"
    )
    model_predictions: Mapped[List["ModelPrediction"]] = relationship(
        back_populates="frame", cascade="all, delete-orphan"
    )
    review_items: Mapped[List["ReviewItem"]] = relationship(
        back_populates="frame", cascade="all, delete-orphan"
    )


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(50), default="VIDEO_INGESTION", index=True)
    model_run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    state: Mapped[str] = mapped_column(String(50), default="QUEUED", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    video: Mapped[Video] = relationship(back_populates="jobs")
    model_run: Mapped[Optional["ModelRun"]] = relationship(back_populates="job")


class AnnotationTask(Base):
    __tablename__ = "annotation_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    video: Mapped[Video] = relationship(back_populates="annotation_tasks")
    annotations: Mapped[List["Annotation"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    propagations: Mapped[List["AnnotationPropagation"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    activity_events: Mapped[List["AnnotationActivity"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("annotation_tasks.id", ondelete="CASCADE"), index=True)
    frame_id: Mapped[str] = mapped_column(ForeignKey("frames.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    annotation_type: Mapped[str] = mapped_column(String(50))
    geometry: Mapped[Dict[str, Any]] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(50), default="human")
    model_prediction_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("model_predictions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    propagation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("annotation_propagations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    task: Mapped[AnnotationTask] = relationship(back_populates="annotations")
    frame: Mapped[Frame] = relationship(back_populates="annotations")
    propagation: Mapped[Optional["AnnotationPropagation"]] = relationship(
        back_populates="annotations"
    )


class AnnotationPropagation(Base):
    __tablename__ = "annotation_propagations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("annotation_tasks.id", ondelete="CASCADE"), index=True
    )
    model_run_id: Mapped[str] = mapped_column(
        ForeignKey("model_runs.id", ondelete="CASCADE"), index=True
    )
    source_prediction_id: Mapped[str] = mapped_column(
        ForeignKey("model_predictions.id", ondelete="CASCADE"), index=True
    )
    source_frame_id: Mapped[str] = mapped_column(
        ForeignKey("frames.id", ondelete="CASCADE"), index=True
    )
    track_id: Mapped[str] = mapped_column(String(100), index=True)
    start_frame_number: Mapped[int] = mapped_column(Integer)
    end_frame_number: Mapped[int] = mapped_column(Integer)
    source_geometry: Mapped[Dict[str, Any]] = mapped_column(JSON)
    correction_delta: Mapped[Dict[str, Any]] = mapped_column(JSON)
    generated_count: Mapped[int] = mapped_column(Integer, default=0)
    reviewer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    task: Mapped[AnnotationTask] = relationship(back_populates="propagations")
    annotations: Mapped[List[Annotation]] = relationship(back_populates="propagation")


class AnnotationActivity(Base):
    __tablename__ = "annotation_activity"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("annotation_tasks.id", ondelete="CASCADE"), index=True)
    frame_id: Mapped[str] = mapped_column(ForeignKey("frames.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(50))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    annotation_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    task: Mapped[AnnotationTask] = relationship(back_populates="activity_events")


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    model_kind: Mapped[str] = mapped_column(String(50), index=True)
    provider: Mapped[str] = mapped_column(String(100))
    model_name: Mapped[str] = mapped_column(String(255))
    model_version: Mapped[str] = mapped_column(String(100))
    device: Mapped[str] = mapped_column(String(50), default="cpu")
    parameters: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="QUEUED", index=True)
    total_frames: Mapped[int] = mapped_column(Integer, default=0)
    processed_frames: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    video: Mapped[Video] = relationship(back_populates="model_runs")
    job: Mapped[Optional[ProcessingJob]] = relationship(back_populates="model_run", uselist=False)
    predictions: Mapped[List["ModelPrediction"]] = relationship(
        back_populates="model_run", cascade="all, delete-orphan"
    )
    review_items: Mapped[List["ReviewItem"]] = relationship(
        back_populates="model_run", cascade="all, delete-orphan"
    )


class ModelPrediction(Base):
    __tablename__ = "model_predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_run_id: Mapped[str] = mapped_column(ForeignKey("model_runs.id", ondelete="CASCADE"), index=True)
    frame_id: Mapped[str] = mapped_column(ForeignKey("frames.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(100), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    annotation_type: Mapped[str] = mapped_column(String(50))
    geometry: Mapped[Dict[str, Any]] = mapped_column(JSON)
    track_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    associated_prediction_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("model_predictions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    association_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    association_ambiguous: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    model_run: Mapped[ModelRun] = relationship(back_populates="predictions")
    frame: Mapped[Frame] = relationship(back_populates="model_predictions")
    decisions: Mapped[List["PredictionDecision"]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan"
    )
    review_items: Mapped[List["ReviewItem"]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan"
    )


class PredictionDecision(Base):
    __tablename__ = "prediction_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    prediction_id: Mapped[str] = mapped_column(
        ForeignKey("model_predictions.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("annotation_tasks.id", ondelete="CASCADE"), index=True
    )
    annotation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("annotations.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), index=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    prediction: Mapped[ModelPrediction] = relationship(back_populates="decisions")


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    frame_id: Mapped[str] = mapped_column(ForeignKey("frames.id", ondelete="CASCADE"), index=True)
    model_run_id: Mapped[str] = mapped_column(
        ForeignKey("model_runs.id", ondelete="CASCADE"), index=True
    )
    prediction_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("model_predictions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    reason: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="MEDIUM", index=True)
    status: Mapped[str] = mapped_column(String(30), default="OPEN", index=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    video: Mapped[Video] = relationship(back_populates="review_items")
    frame: Mapped[Frame] = relationship(back_populates="review_items")
    model_run: Mapped[ModelRun] = relationship(back_populates="review_items")
    prediction: Mapped[Optional[ModelPrediction]] = relationship(back_populates="review_items")
    events: Mapped[List["ReviewEvent"]] = relationship(
        back_populates="review_item", cascade="all, delete-orphan"
    )


class ReviewEvent(Base):
    __tablename__ = "review_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    review_item_id: Mapped[str] = mapped_column(
        ForeignKey("review_items.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(50), index=True)
    reviewer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    review_item: Mapped[ReviewItem] = relationship(back_populates="events")
