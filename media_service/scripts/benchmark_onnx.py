#!/usr/bin/env python3
"""Compare PyTorch and ONNX YOLO latency and output consistency on real frames."""
import argparse
import json
import statistics
import time
from pathlib import Path

from ultralytics import YOLO


def predict(model, image: Path, repeats: int):
    latencies = []
    result = model.predict(source=str(image), verbose=False)[0]
    for _ in range(repeats):
        started = time.perf_counter()
        result = model.predict(source=str(image), verbose=False)[0]
        latencies.append((time.perf_counter() - started) * 1000)
    boxes = result.boxes.xyxy.cpu().tolist() if result.boxes is not None else []
    classes = result.boxes.cls.cpu().tolist() if result.boxes is not None else []
    return latencies, boxes, classes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("evaluation/onnx-benchmark.json"))
    args = parser.parse_args()
    pytorch = YOLO(args.model)
    exported = Path(pytorch.export(format="onnx", dynamic=True, simplify=False))
    onnx = YOLO(str(exported))
    pytorch_times, pytorch_boxes, pytorch_classes = predict(pytorch, args.image, args.repeats)
    onnx_times, onnx_boxes, onnx_classes = predict(onnx, args.image, args.repeats)
    report = {
        "schema_version": "1.0",
        "image": str(args.image),
        "model": args.model,
        "onnx_model": str(exported),
        "repeats": args.repeats,
        "pytorch_median_ms": statistics.median(pytorch_times),
        "onnx_median_ms": statistics.median(onnx_times),
        "speedup": statistics.median(pytorch_times) / statistics.median(onnx_times),
        "pytorch_detection_count": len(pytorch_boxes),
        "onnx_detection_count": len(onnx_boxes),
        "class_ids_match": [round(value) for value in pytorch_classes]
        == [round(value) for value in onnx_classes],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
