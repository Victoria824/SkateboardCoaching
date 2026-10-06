import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import Annotation, AnnotationTask, SanitizedExport
from ..storage import LocalStorage


router = APIRouter(prefix="/api", tags=["dataset exports"])
storage = LocalStorage()


def _task(task_id: str, session: Session) -> AnnotationTask:
    task = session.get(AnnotationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Annotation task not found")
    if task.status != "COMPLETED":
        raise HTTPException(status_code=409, detail="Only completed tasks can be exported")
    return task


def coco_payload(task: AnnotationTask):
    annotations = [item for item in task.annotations if item.annotation_type == "bbox"]
    labels = sorted({item.label for item in annotations})
    category_ids = {label: index + 1 for index, label in enumerate(labels)}
    images = []
    image_ids = {}
    for index, frame in enumerate(task.video.frames, start=1):
        image_ids[frame.id] = index
        images.append(
            {
                "id": index,
                "file_name": Path(frame.storage_path).name,
                "width": frame.width or task.video.width,
                "height": frame.height or task.video.height,
                "timestamp_ms": frame.timestamp_ms,
            }
        )
    items = []
    for index, annotation in enumerate(annotations, start=1):
        width = annotation.frame.width or task.video.width
        height = annotation.frame.height or task.video.height
        if not width or not height:
            raise HTTPException(status_code=409, detail="Frame dimensions are required for export")
        geometry = annotation.geometry
        box = [
            float(geometry["x"]) * width,
            float(geometry["y"]) * height,
            float(geometry["width"]) * width,
            float(geometry["height"]) * height,
        ]
        items.append(
            {
                "id": index,
                "image_id": image_ids[annotation.frame_id],
                "category_id": category_ids[annotation.label],
                "bbox": box,
                "area": box[2] * box[3],
                "iscrowd": 0,
                "source": annotation.source,
            }
        )
    return {
        "info": {"schema_version": "1.0", "task_id": task.id, "video_id": task.video_id},
        "images": images,
        "annotations": items,
        "categories": [
            {"id": category_ids[label], "name": label} for label in labels
        ],
    }


@router.get("/annotation-tasks/{task_id}/exports/coco")
def export_coco(task_id: str, session: Session = Depends(get_session)):
    return JSONResponse(coco_payload(_task(task_id, session)))


@router.get("/annotation-tasks/{task_id}/exports/yolo")
def export_yolo(task_id: str, session: Session = Depends(get_session)):
    task = _task(task_id, session)
    annotations = [item for item in task.annotations if item.annotation_type == "bbox"]
    labels = sorted({item.label for item in annotations})
    label_ids = {label: index for index, label in enumerate(labels)}
    grouped = {}
    for annotation in annotations:
        geometry = annotation.geometry
        grouped.setdefault(annotation.frame_id, []).append(
            "{} {:.6f} {:.6f} {:.6f} {:.6f}".format(
                label_ids[annotation.label],
                float(geometry["x"]) + float(geometry["width"]) / 2,
                float(geometry["y"]) + float(geometry["height"]) / 2,
                float(geometry["width"]),
                float(geometry["height"]),
            )
        )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("classes.txt", "\n".join(labels) + "\n")
        archive.writestr(
            "dataset.yaml",
            "path: .\ntrain: images\nval: images\nnames:\n"
            + "".join("  {}: {}\n".format(index, label) for label, index in label_ids.items()),
        )
        archive.writestr(
            "manifest.json",
            json.dumps({"schema_version": "1.0", "task_id": task.id, "video_id": task.video_id}),
        )
        for frame in task.video.frames:
            stem = Path(frame.storage_path).stem
            archive.writestr("labels/{}.txt".format(stem), "\n".join(grouped.get(frame.id, [])))
            image_path = storage.absolute_path(frame.storage_path)
            if image_path.exists():
                archive.write(image_path, "images/{}".format(Path(frame.storage_path).name))
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="yolo-{}.zip"'.format(task.id)},
    )


@router.get("/sanitized-exports/{export_id}/bundle")
def export_sanitized_bundle(export_id: str, session: Session = Depends(get_session)):
    item = session.get(SanitizedExport, export_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Sanitized export not found")
    if item.status != "COMPLETED" or not item.storage_path or not item.manifest_path:
        raise HTTPException(status_code=409, detail="Sanitized export is not complete")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        archive.write(storage.absolute_path(item.storage_path), "sanitized.mp4")
        archive.write(storage.absolute_path(item.manifest_path), "manifest.json")
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="sanitized-{}.zip"'.format(item.id)},
    )
