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


@dataclass(frozen=True)
class MaskRectangle:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class MaskSegment:
    annotation_id: str
    label: str
    annotation_type: str
    start_seconds: float
    end_seconds: float
    rectangles: Tuple[MaskRectangle, ...]
    grid_width: int
    grid_height: int
    covered_cells: int
    edit_count: int = 0
    last_edit: str = "proposal"


def decode_mask_rle(geometry: Dict[str, Any]) -> List[int]:
    """Decode the platform's row-major, zero-first binary mask representation."""
    width = int(geometry["width"])
    height = int(geometry["height"])
    counts = geometry["rle"]
    pixels: List[int] = []
    value = 0
    for count in counts:
        pixels.extend([value] * int(count))
        value = 1 - value
    if len(pixels) != width * height:
        raise ValueError("Mask RLE does not match its declared dimensions")
    return pixels


def _frame_interval(video, frame_index: int) -> Tuple[float, float]:
    frames = list(video.frames)
    frame = frames[frame_index]
    previous_ms = frames[frame_index - 1].timestamp_ms if frame_index > 0 else 0
    next_ms = (
        frames[frame_index + 1].timestamp_ms
        if frame_index + 1 < len(frames)
        else (video.duration_ms or frame.timestamp_ms + round(1000 / video.sample_fps))
    )
    start_ms = 0 if frame_index == 0 else round((previous_ms + frame.timestamp_ms) / 2)
    end_ms = round((frame.timestamp_ms + next_ms) / 2)
    return start_ms / 1000, end_ms / 1000


def build_blur_segments(video, annotations: Sequence[Any]) -> List[BlurSegment]:
    frames = list(video.frames)
    positions = {frame.id: index for index, frame in enumerate(frames)}
    segments = []
    for annotation in annotations:
        index = positions[annotation.frame_id]
        start_seconds, end_seconds = _frame_interval(video, index)
        geometry = annotation.geometry
        width = max(2, round(float(geometry["width"]) * video.width))
        height = max(2, round(float(geometry["height"]) * video.height))
        x = min(video.width - width, max(0, round(float(geometry["x"]) * video.width)))
        y = min(video.height - height, max(0, round(float(geometry["y"]) * video.height)))
        segments.append(
            BlurSegment(
                annotation_id=annotation.id,
                label=annotation.label,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                x=x,
                y=y,
                width=width,
                height=height,
            )
        )
    return segments


def _mask_row_spans(pixels: Sequence[int], width: int, height: int):
    for row in range(height):
        offset = row * width
        column = 0
        while column < width:
            while column < width and not pixels[offset + column]:
                column += 1
            start = column
            while column < width and pixels[offset + column]:
                column += 1
            if start < column:
                yield row, start, column


def _scale_mask_rectangles(
    pixels: Sequence[int], grid_width: int, grid_height: int, width: int, height: int
) -> Tuple[MaskRectangle, ...]:
    rectangles = []
    for row, start, end in _mask_row_spans(pixels, grid_width, grid_height):
        x1 = max(0, int(start * width / grid_width))
        x2 = min(width, max(x1 + 1, int((end * width + grid_width - 1) / grid_width)))
        y1 = max(0, int(row * height / grid_height))
        y2 = min(height, max(y1 + 1, int(((row + 1) * height + grid_height - 1) / grid_height)))
        rectangle = MaskRectangle(x1, y1, x2 - x1, y2 - y1)
        if (
            rectangles
            and rectangles[-1].x == rectangle.x
            and rectangles[-1].width == rectangle.width
            and rectangles[-1].y + rectangles[-1].height == rectangle.y
        ):
            previous = rectangles[-1]
            rectangles[-1] = MaskRectangle(
                previous.x, previous.y, previous.width, previous.height + rectangle.height
            )
        else:
            rectangles.append(rectangle)
    return tuple(rectangles)


def build_mask_segments(video, annotations: Sequence[Any]) -> List[MaskSegment]:
    """Convert reviewed boxes or editable RLE masks into time-bounded pixel rectangles."""
    frames = list(video.frames)
    positions = {frame.id: index for index, frame in enumerate(frames)}
    segments = []
    for annotation in annotations:
        start_seconds, end_seconds = _frame_interval(video, positions[annotation.frame_id])
        if annotation.annotation_type == "mask":
            geometry = annotation.geometry
            grid_width = int(geometry["width"])
            grid_height = int(geometry["height"])
            pixels = decode_mask_rle(geometry)
            rectangles = _scale_mask_rectangles(
                pixels, grid_width, grid_height, video.width, video.height
            )
            covered_cells = sum(pixels)
            edit_count = int(geometry.get("edit_count", 0))
            last_edit = str(geometry.get("last_edit", "proposal"))
        else:
            geometry = annotation.geometry
            x1 = max(0, int(float(geometry["x"]) * video.width))
            y1 = max(0, int(float(geometry["y"]) * video.height))
            x2 = min(
                video.width,
                max(x1 + 1, int((float(geometry["x"]) + float(geometry["width"])) * video.width + 0.999)),
            )
            y2 = min(
                video.height,
                max(y1 + 1, int((float(geometry["y"]) + float(geometry["height"])) * video.height + 0.999)),
            )
            rectangles = (MaskRectangle(x1, y1, x2 - x1, y2 - y1),)
            grid_width = video.width
            grid_height = video.height
            covered_cells = rectangles[0].width * rectangles[0].height
            edit_count = 0
            last_edit = "bbox-fallback"
        if not rectangles:
            raise ValueError("Privacy mask cannot be empty")
        segments.append(
            MaskSegment(
                annotation_id=annotation.id,
                label=annotation.label,
                annotation_type=annotation.annotation_type,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                rectangles=rectangles,
                grid_width=grid_width,
                grid_height=grid_height,
                covered_cells=covered_cells,
                edit_count=edit_count,
                last_edit=last_edit,
            )
        )
    return segments


def build_ffmpeg_mask_filter(
    video_width: int,
    video_height: int,
    segments: Sequence[MaskSegment],
    video_duration_seconds: float = None,
) -> Tuple[str, str]:
    """Blur once and merge it through the exact reviewed mask at each sampled interval."""
    mask_duration = video_duration_seconds or max(segment.end_seconds for segment in segments)
    chains = [
        "[0:v]split=2[privacybase][privacyblurinput]",
        "[privacyblurinput]boxblur=10:2[privacyblurred]",
        "color=c=black:s={}x{}:d={:.3f},format=gray[mask0]".format(
            video_width, video_height, mask_duration
        ),
    ]
    mask_index = 0
    for segment in segments:
        for rectangle in segment.rectangles:
            next_index = mask_index + 1
            chains.append(
                "[mask{}]drawbox=x={}:y={}:w={}:h={}:color=white:t=fill:"
                "enable='between(t,{:.3f},{:.3f})'[mask{}]".format(
                    mask_index,
                    rectangle.x,
                    rectangle.y,
                    rectangle.width,
                    rectangle.height,
                    segment.start_seconds,
                    segment.end_seconds,
                    next_index,
                )
            )
            mask_index = next_index
    output = "privacymasked"
    chains.append(
        "[privacybase][privacyblurred][mask{}]maskedmerge[{}]".format(mask_index, output)
    )
    return ";".join(chains), "[{}]".format(output)


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


def mask_segment_manifest(segment: MaskSegment) -> Dict[str, Any]:
    return {
        "annotation_id": segment.annotation_id,
        "label": segment.label,
        "annotation_type": segment.annotation_type,
        "start_ms": round(segment.start_seconds * 1000),
        "end_ms": round(segment.end_seconds * 1000),
        "mask": {
            "encoding": "row-major-rle-v1" if segment.annotation_type == "mask" else "bbox-fallback",
            "grid_width": segment.grid_width,
            "grid_height": segment.grid_height,
            "covered_cells": segment.covered_cells,
            "render_rectangles": len(segment.rectangles),
            "edit_count": segment.edit_count,
            "last_edit": segment.last_edit,
        },
    }
