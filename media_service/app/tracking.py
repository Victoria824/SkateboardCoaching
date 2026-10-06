from dataclasses import dataclass
from typing import Any, Dict, List, Sequence


@dataclass(frozen=True)
class Association:
    person_index: int
    board_index: int
    score: float
    ambiguous: bool


def person_board_score(person: Dict[str, Any], board: Dict[str, Any]) -> float:
    """Score whether a board is plausibly underneath a detected person."""
    person_left = float(person["x"])
    person_right = person_left + float(person["width"])
    person_top = float(person["y"])
    person_bottom = person_top + float(person["height"])
    board_left = float(board["x"])
    board_right = board_left + float(board["width"])
    board_center_x = (board_left + board_right) / 2
    board_center_y = float(board["y"]) + float(board["height"]) / 2

    if board_center_y < person_top + float(person["height"]) * 0.45:
        return 0.0

    overlap = max(0.0, min(person_right, board_right) - max(person_left, board_left))
    overlap_ratio = overlap / max(0.001, min(float(person["width"]), float(board["width"])))
    vertical_distance = abs(board_center_y - person_bottom)
    vertical_proximity = max(
        0.0,
        1.0 - vertical_distance / max(0.08, float(person["height"]) * 0.5),
    )
    person_center_x = (person_left + person_right) / 2
    horizontal_proximity = max(
        0.0,
        1.0
        - abs(board_center_x - person_center_x)
        / max(0.1, float(person["width"]) * 1.25),
    )
    return min(1.0, 0.55 * overlap_ratio + 0.3 * vertical_proximity + 0.15 * horizontal_proximity)


def associate_people_and_boards(
    people: Sequence[Dict[str, Any]],
    boards: Sequence[Dict[str, Any]],
    minimum_score: float = 0.3,
    ambiguity_margin: float = 0.1,
) -> List[Association]:
    """Greedily produce one-to-one person/board matches with an ambiguity signal."""
    candidates = []
    scores_by_board: Dict[int, List[float]] = {}
    for board_index, board in enumerate(boards):
        scores = [person_board_score(person, board) for person in people]
        scores_by_board[board_index] = sorted(scores, reverse=True)
        for person_index, score in enumerate(scores):
            if score >= minimum_score:
                candidates.append((score, person_index, board_index))

    associations: List[Association] = []
    used_people = set()
    used_boards = set()
    for score, person_index, board_index in sorted(candidates, reverse=True):
        if person_index in used_people or board_index in used_boards:
            continue
        ranked = scores_by_board[board_index]
        ambiguous = len(ranked) > 1 and ranked[0] - ranked[1] < ambiguity_margin
        associations.append(
            Association(
                person_index=person_index,
                board_index=board_index,
                score=round(score, 4),
                ambiguous=ambiguous,
            )
        )
        used_people.add(person_index)
        used_boards.add(board_index)
    return associations
