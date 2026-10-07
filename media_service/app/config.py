import os
from dataclasses import dataclass
from pathlib import Path


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    database_url: str
    media_root: Path
    public_media_url: str
    max_upload_bytes: int
    frame_sample_fps: float
    worker_poll_seconds: float
    worker_lease_seconds: int
    queue_backend: str
    redis_url: str
    ffmpeg_binary: str
    ffprobe_binary: str
    pii_screen_model: str
    residual_pii_scan_enabled: bool
    residual_pii_scan_fps: float
    residual_pii_confidence: float
    residual_pii_mask_coverage: float
    storage_backend: str
    s3_endpoint_url: str
    s3_public_endpoint_url: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str
    s3_presign_ttl_seconds: int
    s3_presign_get_ttl_seconds: int
    cors_origins: tuple

    def __post_init__(self) -> None:
        if not 0 < self.residual_pii_scan_fps <= 30:
            raise ValueError("MEDIA_RESIDUAL_PII_SCAN_FPS must be greater than 0 and at most 30")
        if not 0 <= self.residual_pii_confidence <= 1:
            raise ValueError("MEDIA_RESIDUAL_PII_CONFIDENCE must be between 0 and 1")
        if not 0 <= self.residual_pii_mask_coverage <= 1:
            raise ValueError("MEDIA_RESIDUAL_PII_MASK_COVERAGE must be between 0 and 1")

    @classmethod
    def from_environment(cls) -> "Settings":
        root = _repository_root()
        return cls(
            database_url=os.getenv(
                "MEDIA_DATABASE_URL",
                "sqlite:///{}".format(root / "media_service" / "data" / "media.db"),
            ),
            media_root=Path(
                os.getenv("MEDIA_STORAGE_ROOT", str(root / "media_service" / "data" / "media"))
            ).resolve(),
            public_media_url=os.getenv("MEDIA_PUBLIC_URL", "/media").rstrip("/"),
            max_upload_bytes=int(os.getenv("MEDIA_MAX_UPLOAD_BYTES", str(250 * 1024 * 1024))),
            frame_sample_fps=float(os.getenv("MEDIA_FRAME_SAMPLE_FPS", "1")),
            worker_poll_seconds=float(os.getenv("MEDIA_WORKER_POLL_SECONDS", "1")),
            worker_lease_seconds=int(os.getenv("MEDIA_WORKER_LEASE_SECONDS", "1800")),
            queue_backend=os.getenv("MEDIA_QUEUE_BACKEND", "database").lower(),
            redis_url=os.getenv("MEDIA_REDIS_URL", "redis://localhost:6379/0"),
            ffmpeg_binary=os.getenv("FFMPEG_BINARY", "ffmpeg"),
            ffprobe_binary=os.getenv("FFPROBE_BINARY", "ffprobe"),
            pii_screen_model=os.getenv("MEDIA_PII_SCREEN_MODEL", "yolo11n.pt"),
            residual_pii_scan_enabled=os.getenv("MEDIA_RESIDUAL_PII_SCAN", "true").lower()
            in {"1", "true", "yes", "on"},
            residual_pii_scan_fps=float(os.getenv("MEDIA_RESIDUAL_PII_SCAN_FPS", "5")),
            residual_pii_confidence=float(
                os.getenv("MEDIA_RESIDUAL_PII_CONFIDENCE", "0.25")
            ),
            residual_pii_mask_coverage=float(
                os.getenv("MEDIA_RESIDUAL_PII_MASK_COVERAGE", "0.8")
            ),
            storage_backend=os.getenv("MEDIA_STORAGE_BACKEND", "local").lower(),
            s3_endpoint_url=os.getenv("S3_ENDPOINT_URL", ""),
            s3_public_endpoint_url=os.getenv("S3_PUBLIC_ENDPOINT_URL", ""),
            s3_bucket=os.getenv("S3_BUCKET", "snowboard-media"),
            s3_access_key=os.getenv("S3_ACCESS_KEY", ""),
            s3_secret_key=os.getenv("S3_SECRET_KEY", ""),
            s3_region=os.getenv("S3_REGION", "us-east-1"),
            s3_presign_ttl_seconds=int(os.getenv("S3_PRESIGN_TTL_SECONDS", "900")),
            s3_presign_get_ttl_seconds=int(
                os.getenv("S3_PRESIGN_GET_TTL_SECONDS", "3600")
            ),
            cors_origins=tuple(
                origin.strip()
                for origin in os.getenv("MEDIA_CORS_ORIGINS", "http://localhost:3000").split(",")
                if origin.strip()
            ),
        )


settings = Settings.from_environment()
