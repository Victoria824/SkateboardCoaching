from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class UploadResponse(BaseModel):
    video: VideoResponse
    job: JobResponse
