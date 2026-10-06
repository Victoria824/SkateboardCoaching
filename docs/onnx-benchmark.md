# PyTorch versus ONNX Runtime smoke benchmark

On 2026-10-06, `yolo11n.pt` was evaluated on one real 640×360 extracted snowboard frame on an
Apple M1 Pro CPU. Each runtime received one warmup inference followed by ten measured inferences.

| Runtime | Version | Median latency |
| --- | --- | ---: |
| PyTorch/Ultralytics | torch 2.8.0 / Ultralytics 8.4.173 | 46.20 ms |
| ONNX Runtime | 1.19.2 CPUExecutionProvider | 29.88 ms |

The ONNX smoke run was 1.55× faster. Both runtimes returned zero detections and therefore matched
in detection count and class IDs on this frame. This is infrastructure evidence, not an accuracy or
production-throughput claim; broader gold-video evaluation and confidence/box consistency remain
required. The ignored raw JSON artifact was generated with:

```bash
.venv/bin/python scripts/benchmark_onnx.py <real-frame.jpg> --repeats 10 \
  --output data/evaluation/onnx-benchmark.json
```
