import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


PII_LABELS = {"face", "license_plate", "screen"}


@dataclass(frozen=True)
class BlurSegment:
    annotation_id: str
    label: str
    start_seconds: float
    end_seconds: float
    x: int
    y: int
    width: int
    height: int


def build_blur_segments(video, annotations: Sequence[Any]) -> List[BlurSegment]:
    frames = list(video.frames)
    positions = {frame.id: index for index, frame in enumerate(frames)}
    segments = []
    for annotation in annotations:
        index = positions[annotation.frame_id]
        frame = frames[index]
        previous_ms = frames[index - 1].timestamp_ms if index > 0 else 0
        next_ms = (
            frames[index + 1].timestamp_ms
            if index + 1 < len(frames)
            else (video.duration_ms or frame.timestamp_ms + round(1000 / video.sample_fps))
        )
        start_ms = 0 if index == 0 else round((previous_ms + frame.timestamp_ms) / 2)
        end_ms = round((frame.timestamp_ms + next_ms) / 2)
        geometry = annotation.geometry
        width = max(2, round(float(geometry["width"]) * video.width))
        height = max(2, round(float(geometry["height"]) * video.height))
        x = min(video.width - width, max(0, round(float(geometry["x"]) * video.width)))
        y = min(video.height - height, max(0, round(float(geometry["y"]) * video.height)))
        segments.append(
            BlurSegment(
                annotation_id=annotation.id,
                label=annotation.label,
                start_seconds=start_ms / 1000,
                end_seconds=end_ms / 1000,
                x=x,
                y=y,
                width=width,
                height=height,
            )
        )
    return segments


def build_ffmpeg_blur_filter(segments: Sequence[BlurSegment]) -> Tuple[str, str]:
    chains = []
    current = "[0:v]"
    for index, segment in enumerate(segments):
        base, crop, blurred, output = (
            "base{}".format(index),
            "crop{}".format(index),
            "blur{}".format(index),
            "privacy{}".format(index),
        )
        chains.append("{}split=2[{}][{}]".format(current, base, crop))
        chains.append(
            "[{}]crop={}:{}:{}:{},boxblur=10:2[{}]".format(
                crop, segment.width, segment.height, segment.x, segment.y, blurred
            )
        )
        chains.append(
            "[{}][{}]overlay={}:{}:enable='between(t,{:.3f},{:.3f})'[{}]".format(
                base,
                blurred,
                segment.x,
                segment.y,
                segment.start_seconds,
                segment.end_seconds,
                output,
            )
        )
        current = "[{}]".format(output)
    return ";".join(chains), current


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def segment_manifest(segment: BlurSegment) -> Dict[str, Any]:
    return {
        "annotation_id": segment.annotation_id,
        "label": segment.label,
        "start_ms": round(segment.start_seconds * 1000),
        "end_ms": round(segment.end_seconds * 1000),
        "pixel_geometry": {
            "x": segment.x,
            "y": segment.y,
            "width": segment.width,
            "height": segment.height,
        },
    }
