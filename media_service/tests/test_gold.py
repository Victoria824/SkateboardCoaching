import pytest

from app.gold import evaluate_gold_manifest


def test_gold_evaluation_scores_detection_and_association():
    checksum = "a" * 64
    manifest = {
        "schema_version": "1.0",
        "dataset": {"name": "test", "created_at": "2026-10-06T00:00:00Z"},
        "videos": [
            {
                "source": {"sha256": checksum},
                "sampling_profile": "action",
                "sample_fps": 5,
                "frames": [
                    {
                        "frame_number": 1,
                        "timestamp_ms": 0,
                        "review_status": "approved",
                        "objects": [
                            {
                                "id": "gold-rider",
                                "label": "rider",
                                "annotation_type": "bbox",
                                "geometry": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.6},
                                "associated_object_id": "gold-board",
                            },
                            {
                                "id": "gold-board",
                                "label": "snowboard",
                                "annotation_type": "bbox",
                                "geometry": {"x": 0.1, "y": 0.68, "width": 0.4, "height": 0.08},
                            },
                        ],
                    },
                    {
                        "frame_number": 2,
                        "timestamp_ms": 200,
                        "review_status": "approved",
                        "objects": [
                            {
                                "id": "missed-rider",
                                "label": "rider",
                                "annotation_type": "bbox",
                                "geometry": {"x": 0.2, "y": 0.1, "width": 0.3, "height": 0.6},
                            }
                        ],
                    },
                    {
                        "frame_number": 3,
                        "timestamp_ms": 400,
                        "review_status": "pending",
                        "objects": [],
                    },
                ],
            }
        ],
    }
    report = {
        "source": {"sha256": checksum},
        "runs": [
            {
                "model_kind": "detection",
                "predictions": [
                    {
                        "id": "prediction-rider",
                        "frame_number": 1,
                        "label": "rider",
                        "annotation_type": "bbox",
                        "geometry": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.6},
                        "associated_prediction_id": "prediction-board",
                    },
                    {
                        "id": "prediction-board",
                        "frame_number": 1,
                        "label": "snowboard",
                        "annotation_type": "bbox",
                        "geometry": {"x": 0.1, "y": 0.68, "width": 0.4, "height": 0.08},
                    },
                    {
                        "id": "false-person",
                        "frame_number": 1,
                        "label": "person",
                        "annotation_type": "bbox",
                        "geometry": {"x": 0.7, "y": 0.1, "width": 0.2, "height": 0.5},
                    },
                ],
            }
        ],
    }

    result = evaluate_gold_manifest(manifest, [report])

    assert result["evaluated_frames"] == 2
    assert result["overall"]["tp"] == 2
    assert result["overall"]["fp"] == 1
    assert result["overall"]["fn"] == 1
    assert result["overall"]["precision"] == pytest.approx(2 / 3)
    assert result["overall"]["recall"] == pytest.approx(2 / 3)
    assert result["association"]["accuracy"] == 1


def test_gold_evaluation_requires_approved_frames():
    checksum = "b" * 64
    manifest = {
        "schema_version": "1.0",
        "videos": [
            {
                "source": {"sha256": checksum},
                "frames": [
                    {
                        "frame_number": 1,
                        "review_status": "pending",
                        "objects": [],
                    }
                ],
            }
        ],
    }
    report = {
        "source": {"sha256": checksum},
        "runs": [{"model_kind": "detection", "predictions": []}],
    }

    with pytest.raises(ValueError, match="no reviewer-approved frames"):
        evaluate_gold_manifest(manifest, [report])
