import pytest

from app.gold import evaluate_gold_manifest, evaluate_pii_gold_manifest


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


def test_pii_gold_evaluation_scores_recall_slices_tracks_and_gate():
    checksum = "c" * 64
    manifest = {
        "schema_version": "1.0",
        "dataset": {"name": "pii-gold-v1", "created_at": "2026-10-07T00:00:00Z"},
        "videos": [
            {
                "source": {"sha256": checksum},
                "frames": [
                    {
                        "frame_number": 1,
                        "timestamp_ms": 0,
                        "review_status": "approved",
                        "difficult_case_tags": ["motion_blur"],
                        "objects": [
                            {
                                "id": "face-1",
                                "label": "face",
                                "annotation_type": "bbox",
                                "track_id": "face-track",
                                "geometry": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                            }
                        ],
                    },
                    {
                        "frame_number": 2,
                        "timestamp_ms": 1000,
                        "review_status": "approved",
                        "objects": [
                            {
                                "id": "face-2",
                                "label": "face",
                                "annotation_type": "bbox",
                                "track_id": "face-track",
                                "geometry": {"x": 0.2, "y": 0.1, "width": 0.2, "height": 0.2},
                            },
                            {
                                "id": "plate-1",
                                "label": "license_plate",
                                "annotation_type": "bbox",
                                "geometry": {"x": 0.6, "y": 0.7, "width": 0.2, "height": 0.1},
                            },
                        ],
                    },
                ],
            }
        ],
    }
    report = {
        "source": {"sha256": checksum},
        "media": {"duration_ms": 60_000},
        "runs": [
            {
                "model_kind": "pii",
                "model_name": "pii-model",
                "model_version": "v1",
                "confidence_threshold": 0.25,
                "device": "cpu",
                "predictions": [
                    {
                        "frame_number": 1,
                        "label": "face",
                        "annotation_type": "bbox",
                        "geometry": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                    },
                    {
                        "frame_number": 2,
                        "label": "face",
                        "annotation_type": "bbox",
                        "geometry": {"x": 0.8, "y": 0.1, "width": 0.1, "height": 0.1},
                    },
                ],
            }
        ],
    }

    result = evaluate_pii_gold_manifest(manifest, [report])

    assert result["overall"]["tp"] == 1
    assert result["overall"]["fp"] == 1
    assert result["overall"]["fn"] == 2
    assert result["false_negatives_per_minute"] == 2
    assert result["frames_with_uncovered_pii"] == 1
    assert result["tracks"]["coverage"][f"{checksum}:face:face-track"] == 0.5
    assert result["by_difficult_case"]["motion_blur"]["recall"] == 1
    assert result["quality_gate"]["passed"] is False
