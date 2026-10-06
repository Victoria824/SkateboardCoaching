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


@dataclass(frozen=True)
class ExtractedFrame:
    path: Path
    timestamp_ms: int


def select_motion_indices(
    grayscale_frames: List[bytes],
    analysis_fps: int = 5,
    threshold: float = 0.75,
    burst_radius: int = 2,
) -> List[int]:
    if not grayscale_frames:
        return []
    selected = set(range(0, len(grayscale_frames), analysis_fps))
    for index in range(1, len(grayscale_frames)):
        previous, current = grayscale_frames[index - 1], grayscale_frames[index]
        difference = sum(abs(left - right) for left, right in zip(previous, current)) / max(
            1, len(current)
        )
        if difference >= threshold:
            selected.update(
                range(max(0, index - burst_radius), min(len(grayscale_frames), index + burst_radius + 1))
            )
    return sorted(selected)


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

    def extract_motion_aware_frames(
        self,
        video_path: Path,
        output_dir: Path,
        action_fps: int = 5,
        threshold: float = 0.75,
    ) -> List[ExtractedFrame]:
        width, height = 64, 36
        analysis_command = [
            settings.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-vf",
            "fps={},scale={}:{},format=gray".format(action_fps, width, height),
            "-f",
            "rawvideo",
            "pipe:1",
        ]
        raw = self._run_binary(analysis_command, "MOTION_ANALYSIS_FAILED").stdout
        frame_size = width * height
        grayscale_frames = [
            raw[offset : offset + frame_size]
            for offset in range(0, len(raw) - frame_size + 1, frame_size)
        ]
        selected_indices = select_motion_indices(
            grayscale_frames, analysis_fps=action_fps, threshold=threshold
        )
        if not selected_indices:
            raise MediaProcessingError("NO_FRAMES_EXTRACTED", "Motion analysis produced no frames")

        candidate_dir = output_dir / "_motion_candidates"
        candidates = self.extract_frames(video_path, candidate_dir, action_fps)
        output_dir.mkdir(parents=True, exist_ok=True)
        for existing in output_dir.glob("frame-*.jpg"):
            existing.unlink()
        extracted = []
        for output_index, candidate_index in enumerate(selected_indices, start=1):
            if candidate_index >= len(candidates):
                continue
            destination = output_dir / "frame-{:06d}.jpg".format(output_index)
            candidates[candidate_index].replace(destination)
            extracted.append(
                ExtractedFrame(
                    path=destination,
                    timestamp_ms=round(candidate_index / action_fps * 1000),
                )
            )
        for candidate in candidate_dir.glob("frame-*.jpg"):
            candidate.unlink()
        candidate_dir.rmdir()
        return extracted

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

    @staticmethod
    def _run_binary(command: List[str], error_code: str) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(command, check=True, capture_output=True, timeout=1800)
        except FileNotFoundError:
            raise MediaProcessingError(error_code, "Required binary is not installed: {}".format(command[0]))
        except subprocess.TimeoutExpired:
            raise MediaProcessingError(error_code, "Media command timed out")
        except subprocess.CalledProcessError as error:
            message = (error.stderr or error.stdout or bytes(str(error), "utf-8"))[-2000:]
            raise MediaProcessingError(error_code, message.decode("utf-8", errors="replace").strip())
