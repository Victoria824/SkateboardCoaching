import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import List, Optional

from .config import settings


class MediaProcessingError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class VideoMetadata:
    duration_ms: int
    fps: float
    width: int
    height: int
    codec: str
    frame_count: Optional[int]


def parse_frame_rate(value: str) -> float:
    try:
        rate = float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        raise MediaProcessingError("INVALID_FRAME_RATE", "Invalid frame rate: {}".format(value))
    if rate <= 0:
        raise MediaProcessingError("INVALID_FRAME_RATE", "Frame rate must be positive")
    return rate


def parse_probe_payload(payload: dict) -> VideoMetadata:
    streams = payload.get("streams") or []
    stream = next((item for item in streams if item.get("codec_type") == "video"), None)
    if not stream:
        raise MediaProcessingError("NO_VIDEO_STREAM", "The uploaded file has no video stream")

    duration_value = stream.get("duration") or (payload.get("format") or {}).get("duration")
    if duration_value is None:
        raise MediaProcessingError("MISSING_DURATION", "FFprobe did not return video duration")

    fps = parse_frame_rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0")
    duration_ms = max(1, round(float(duration_value) * 1000))
    frame_count_value = stream.get("nb_frames")
    frame_count = int(frame_count_value) if frame_count_value and str(frame_count_value).isdigit() else None
    if frame_count is None:
        frame_count = max(1, round((duration_ms / 1000) * fps))

    return VideoMetadata(
        duration_ms=duration_ms,
        fps=fps,
        width=int(stream.get("width") or 0),
        height=int(stream.get("height") or 0),
        codec=str(stream.get("codec_name") or "unknown"),
        frame_count=frame_count,
    )


class FFmpegProcessor:
    def probe(self, video_path: Path) -> VideoMetadata:
        command = [
            settings.ffprobe_binary,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]
        result = self._run(command, "FFPROBE_FAILED")
        try:
            return parse_probe_payload(json.loads(result.stdout))
        except json.JSONDecodeError as error:
            raise MediaProcessingError("INVALID_FFPROBE_OUTPUT", str(error))

    def extract_frames(self, video_path: Path, output_dir: Path, sample_fps: float) -> List[Path]:
        if sample_fps <= 0:
            raise ValueError("sample_fps must be positive")
        output_dir.mkdir(parents=True, exist_ok=True)
        for existing in output_dir.glob("frame-*.jpg"):
            existing.unlink()

        pattern = output_dir / "frame-%06d.jpg"
        command = [
            settings.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            "fps={}".format(sample_fps),
            "-q:v",
            "2",
            str(pattern),
        ]
        self._run(command, "FRAME_EXTRACTION_FAILED")
        frames = sorted(output_dir.glob("frame-*.jpg"))
        if not frames:
            raise MediaProcessingError("NO_FRAMES_EXTRACTED", "FFmpeg produced no frames")
        return frames

    @staticmethod
    def _run(command: List[str], error_code: str) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(command, check=True, capture_output=True, text=True, timeout=1800)
        except FileNotFoundError:
            raise MediaProcessingError(error_code, "Required binary is not installed: {}".format(command[0]))
        except subprocess.TimeoutExpired:
            raise MediaProcessingError(error_code, "Media command timed out")
        except subprocess.CalledProcessError as error:
            message = (error.stderr or error.stdout or str(error)).strip()
            raise MediaProcessingError(error_code, message[-2000:])

