# Snowboard instance segmentation

Create a `segmentation` model run to use `yolo11n-seg.pt`. The worker retains only snowboard
instances and stores each normalized mask contour as a `polygon` prediction. ByteTrack identities
are preserved when available; the existing geometry fallback uses each polygon's enclosing box when
the tracker has not yet confirmed an identity.

Reviewers can accept or reject a mask in the annotation workspace. Accepted polygons are first-class
annotations and are exported as COCO polygon `segmentation` arrays or Ultralytics YOLO segmentation
rows. Polygon vertex/brush correction is deliberately not presented as complete: the current UI
supports selection and deletion, while mask correction should be added with zoom, undo, and explicit
foreground/background brush semantics rather than an unsafe approximation.

This model is for snowboard data labeling, not privacy redaction. PII sanitization continues to blur
the full reviewer-approved bounding box because under-segmenting a face or plate is a privacy risk.
