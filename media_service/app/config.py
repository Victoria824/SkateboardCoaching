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
    ffmpeg_binary: str
    ffprobe_binary: str
    cors_origins: tuple

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
            ffmpeg_binary=os.getenv("FFMPEG_BINARY", "ffmpeg"),
            ffprobe_binary=os.getenv("FFPROBE_BINARY", "ffprobe"),
            cors_origins=tuple(
                origin.strip()
                for origin in os.getenv("MEDIA_CORS_ORIGINS", "http://localhost:3000").split(",")
                if origin.strip()
            ),
        )


settings = Settings.from_environment()

