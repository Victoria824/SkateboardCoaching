# Annotation workflow

Milestone 2 introduces a persisted, frame-level annotation loop on top of the media pipeline.

## Flow

1. A processed video reaches `READY_FOR_ANNOTATION`.
2. The client creates or resumes an annotation task.
3. `/annotate/{task_id}` loads the video frames and existing annotations.
4. The annotator draws normalized bounding boxes or places pose keypoints.
5. Saving replaces the current human label set for that task/frame and records time spent.
6. Moving to another frame saves unsaved work first. Navigation stops if that save fails.

## Geometry

Bounding boxes use normalized coordinates:

```json
{
  "x": 0.1,
  "y": 0.2,
  "width": 0.4,
  "height": 0.6
}
```

Keypoints are grouped in a single `rider_pose` annotation:

```json
{
  "points": [
    {"name": "head", "x": 0.45, "y": 0.12, "visible": true}
  ]
}
```

The API rejects non-finite, out-of-bounds, empty, and negative geometry before persistence.

## Controls

- `B`: bounding-box mode
- `K`: keypoint mode
- `Left` / `Right`: previous or next frame
- `Shift+Left` / `Shift+Right`: jump ten frames
- `Delete` / `Backspace`: remove the selected annotation
- `Ctrl+S` / `Cmd+S`: save the current frame

Bounding boxes can be moved and resized from the lower-right handle. Keypoints can be repositioned by dragging them.

## Deliberate next steps

- Model predictions rendered separately from human annotations
- Accept, correct, and reject actions
- Undo/redo command history
- Full multi-handle resizing, zoom, and pan
- Annotation revision history and reviewer workflow

