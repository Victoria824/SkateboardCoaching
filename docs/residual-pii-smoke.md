# Independent residual-PII model smoke test

On 2026-10-08, the real Transformers adapter loaded the pinned
`IDEA-Research/grounding-dino-tiny` revision
`a2bb814dd30d776dcf7e30523b00659f4f141c71` and completed inference on both a real snowboard frame
and the checked-in two-second privacy smoke video.

The end-to-end video command processed two 1 FPS frames in 7,888 ms on Apple Silicon CPU and wrote
a report with exact source SHA-256, model revision, threshold, frame geometry, and predictions. It
produced four conservative screen/plate findings. These unreviewed findings demonstrate that the
adapter and fail-closed reporting path run; they are not accuracy evidence and may include false
positives.

Residual accuracy remains deliberately unclaimed until the reviewer-approved sanitized-video gold
manifest contains both clean frames and positive leakage controls. Run the documented
`residual-pii` evaluator after those labels are available. Model initialization or inference failure
remains a hard export failure.
