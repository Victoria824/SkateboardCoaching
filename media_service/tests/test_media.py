import pytest

from app.media import MediaProcessingError, parse_frame_rate, parse_probe_payload
from app.storage import LocalStorage


def test_parse_probe_payload(sample_probe_payload):
    metadata = parse_probe_payload(sample_probe_payload)

    assert metadata.duration_ms == 10010
    assert metadata.fps == pytest.approx(29.970, rel=0.001)
    assert metadata.width == 1920
    assert metadata.height == 1080
    assert metadata.codec == "h264"
    assert metadata.frame_count == 300


def test_parse_probe_payload_estimates_missing_frame_count(sample_probe_payload):
    del sample_probe_payload["streams"][0]["nb_frames"]

    metadata = parse_probe_payload(sample_probe_payload)

    assert metadata.frame_count == 300


def test_parse_frame_rate_rejects_zero():
    with pytest.raises(MediaProcessingError) as error:
        parse_frame_rate("0/0")

    assert error.value.code == "INVALID_FRAME_RATE"


def test_local_storage_normalizes_root_before_building_relative_paths(tmp_path):
    storage = LocalStorage(tmp_path / "nested" / ".." / "media")
    frame = storage.root / "frames" / "frame.jpg"

    assert storage.relative_path(frame) == "frames/frame.jpg"
