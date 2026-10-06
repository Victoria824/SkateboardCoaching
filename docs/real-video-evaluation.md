# Real-video evaluation

This evaluation checks the actual FFmpeg ingestion and Ultralytics inference workers against
licensed, real snowboarding footage. It is an engineering smoke benchmark, not an accuracy
claim: the clips do not yet have complete ground-truth annotations.

## Evaluation sources

The source videos and generated frames are intentionally kept under the ignored
`media_service/data/` directory. Only attribution, hashes, methodology, and aggregate results
are committed.

| YouTube source | Creator | Permission evidence | Local SHA-256 |
| --- | --- | --- | --- |
| [People Snowboarding At A Resort](https://www.youtube.com/watch?v=FGkxsSAJSk4) | Freestocks | YouTube metadata reports `Creative Commons Attribution license (reuse allowed)`; the description permits personal and commercial use. | `8c15b3e29e864e6daed515adfddc087ff366b1a08648394642c8770a8990ac0a` |
| [Snowboarding — Free HD Royalty Stock Footage](https://www.youtube.com/watch?v=pWkGclwklFo) | Footage Island / Nissim Farin | The creator's description permits private and commercial use and requests credit. | `a865e2270d8bf3d2e69525bf5994d10fd9dab38c845c3e903a6f36d34418f0a3` |

Metadata and permission evidence were checked on 2026-10-05. Re-check the source page before
redistributing any source media. The repository does not redistribute either video.

## Method

- Hardware: local Apple Silicon (`arm64`), CPU inference
- Frame sampling: the platform default of 1 FPS
- Detection: `yolo11n.pt`, confidence threshold 0.25
- Pose: `yolo11n-pose.pt`, confidence threshold 0.25
- Runtime: Ultralytics 8.4.173
- Each run uses an isolated temporary SQLite database and media directory
- Timings are one observed local run, not a statistically stable performance benchmark

The first clip is a crowded, distant POV resort scene. The second contains a fast, single-rider
jump with long intervals where no rider is visible. Together they exercise different failure
modes.

## Results

| Clip | Ingest | Sampled frames | Detection | Pose |
| --- | ---: | ---: | --- | --- |
| Resort POV, 9.9 s, 720p | 669 ms | 10 | 66 predictions on 10/10 frames; 1,410 ms | 4 poses on 4/10 frames; 519 ms |
| Jump, 32.8 s, 720p | 428 ms | 33 | 12 predictions on 6/33 frames; 2,396 ms | 4 poses on 4/33 frames; 1,573 ms |

Detection label counts were:

- Resort POV: 61 `rider`, 5 `snowboard`
- Jump: 8 `rider`, 4 `snowboard`

The resort clip's median detection confidence was 0.6803. The jump clip's median detection
confidence was 0.4391. These values describe emitted predictions only; they do not measure
precision or recall.

## Findings

1. The full production path works on real VP9 and H.264 input: metadata extraction, frame
   extraction, database persistence, detection, and pose all completed successfully.
2. Mapping every pretrained `person` detection to `rider` is semantically wrong in a mixed ski
   resort scene. Skiers, standing bystanders, and actual snowboarders need either separate labels
   or a person-to-board association step.
3. A visible foreground board carried by the camera wearer can be detected as `snowboard` without
   an associated rider. Independent boxes are therefore insufficient for a useful rider label.
4. In the jump clip, visual review found a rider in roughly eight of the 33 one-second samples;
   detection covered six of those samples and pose covered four. This is a qualitative check,
   not scored ground truth.
5. One-frame-per-second sampling aliases fast motion. It misses takeoff, rotation, landing, and
   short failure events that matter for both coaching and annotation.
6. Frame-independent inference produces no track identity or temporal continuity. Reviewers must
   repeatedly resolve the same subject and cannot propagate a correction through a sequence.

These findings make temporal labeling and measurable review quality a higher-value next step than
adding another standalone model.

## Quality-routing rerun

After the Milestone 4A review workflow was added, the clips were rerun through automatic routing.
The resort clip generated 39 review items: 20 low-confidence predictions, 9 edge-clipped boxes,
6 rider detections without pose, and 4 deterministic random audits. The jump clip generated 14:
9 low-confidence predictions, 3 missing-pose cases, 1 edge-clipped box, and 1 pose without a rider
detection. These are review candidates rather than confirmed errors.

## Milestone 4B temporal rerun

The same licensed clips were rerun after adding sampling profiles, ByteTrack-backed IDs, a
deterministic short-term geometry fallback for unconfirmed tracks, and person-to-board association.
The jump clip used the 5 FPS `action` profile; the resort clip used the 1 FPS `overview` profile.

| Clip | Samples | Detection tracks | Multi-frame detection tracks | Board links | Unlinked boards |
| --- | ---: | ---: | ---: | ---: | ---: |
| Jump, action profile | 164 | 19 | 5 | 10 | 1 |
| Resort POV, overview profile | 10 | 14 | 10 | 2 | 2 |

The jump detector emitted 35 predictions on 22 frames, compared with 12 predictions on 6 frames
in the original 1 FPS run. All 35 predictions received an auditable track ID; 13 person detections
were classified as `rider` through a board association or the same associated person track, while
11 remained `person`. Detection took 9.9 seconds (60.5 ms per sampled frame) in this run.

The crowded resort run no longer maps all people to riders: 26 predictions remained `person`, 3
were association-backed `rider` predictions, and 4 were snowboards. These counts demonstrate the
semantic behavior of the association stage, not association accuracy; gold labels are still
required before publishing precision or recall.

## Motion-aware sampling check

The jump clip was also processed with a 1 FPS baseline plus 5 FPS motion bursts. The calibrated
profile retained 61 of the 164 fixed-action samples (37%) and detection completed in 3.8 seconds,
compared with 9.9 seconds for fixed 5 FPS in the earlier run. It emitted 30 detections on 17 frames,
versus 35 detections on 22 frames at fixed 5 FPS, and preserved 10 of the 10 association-backed
snowboard links from that run. These are workload and emitted-prediction comparisons, not recall;
the approved gold set is required to determine whether any omitted frames contain true objects.

## Reproduce

Install the media and ML dependencies, obtain a locally licensed test video, then run:

```bash
cd media_service
.venv/bin/python scripts/evaluate_pipeline.py /path/to/video.mp4 \
  --sample-fps 5 \
  --source-url "https://source.example/video" \
  --source-creator "Creator name" \
  --source-license "License or permission evidence" \
  --output data/evaluation/report.json
```

Add `--include-predictions` when the report needs every normalized geometry. The evaluator never
writes to the application's development database.
