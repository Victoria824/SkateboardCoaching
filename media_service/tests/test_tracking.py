import pytest

from app.inference import PredictionOutput, UltralyticsProvider
from app.tracking import associate_people_and_boards, person_board_score


def test_person_board_score_prefers_board_below_person():
    person = {"x": 0.2, "y": 0.1, "width": 0.3, "height": 0.6}
    board_below = {"x": 0.18, "y": 0.68, "width": 0.4, "height": 0.08}
    board_above = {"x": 0.18, "y": 0.05, "width": 0.4, "height": 0.08}

    assert person_board_score(person, board_below) > 0.7
    assert person_board_score(person, board_above) == 0


def test_association_is_one_to_one_and_reports_ambiguity():
    people = [
        {"x": 0.2, "y": 0.1, "width": 0.3, "height": 0.6},
        {"x": 0.22, "y": 0.1, "width": 0.3, "height": 0.6},
    ]
    boards = [{"x": 0.18, "y": 0.68, "width": 0.4, "height": 0.08}]

    associations = associate_people_and_boards(people, boards)

    assert len(associations) == 1
    assert associations[0].score == pytest.approx(
        max(person_board_score(person, boards[0]) for person in people), abs=0.0001
    )
    assert associations[0].ambiguous is True


def test_geometry_fallback_preserves_short_term_identity():
    sequence = [
        [
            PredictionOutput(
                label="person",
                confidence=0.9,
                annotation_type="bbox",
                geometry={"x": 0.2, "y": 0.2, "width": 0.3, "height": 0.5},
            )
        ],
        [
            PredictionOutput(
                label="person",
                confidence=0.9,
                annotation_type="bbox",
                geometry={"x": 0.22, "y": 0.2, "width": 0.3, "height": 0.5},
            )
        ],
    ]

    tracked = UltralyticsProvider._fill_missing_track_ids(sequence)

    assert tracked[0][0].external_track_id is not None
    assert tracked[0][0].external_track_id == tracked[1][0].external_track_id
