"""Parsing and deterministic board choices for Mudae sphere mini-games."""

from dataclasses import dataclass
import re
from typing import Iterable, Optional, Sequence, Tuple


BOARD_SIZE = 5
BOARD_CELLS = BOARD_SIZE * BOARD_SIZE
UNKNOWN_SPHERE = "spU"
RED_SPHERE = "sp"


@dataclass(frozen=True)
class SphereGameStatus:
    oh: int
    oc: int
    oq: int
    ot: int
    refill_minutes: Optional[int] = None
    oh_stored: int = 0
    oc_stored: int = 0
    oq_stored: int = 0
    ot_stored: int = 0

    def count_for(self, game: str) -> int:
        return int(getattr(self, str(game).lower(), 0))

    def stored_for(self, game: str) -> int:
        return int(getattr(self, f"{str(game).lower()}_stored", 0))

    def available_for(self, game: str) -> int:
        return self.count_for(game) + self.stored_for(game)


def parse_sphere_game_status(text: str) -> Optional[SphereGameStatus]:
    """Parse the $oh/$oc/$oq/$ot stock line and its shared refill timer."""
    normalized = str(text or "").replace("**", "")
    counts = {}
    stored_counts = {}
    for game in ("oh", "oc", "oq", "ot"):
        match = re.search(
            r"([\d,]+)\s+\$" + game + r"\b"
            # Mudae localizes the label after the bonus count (for example,
            # "stored" and "armazenados"), while the (+N ...) shape is stable.
            r"(?:[^,$\r\n]*?\(\s*\+\s*([\d,]+)(?:\s+[^)]*)?\))?",
            normalized,
            re.IGNORECASE,
        )
        if match:
            counts[game] = int(match.group(1).replace(",", ""))
            stored_counts[game] = int((match.group(2) or "0").replace(",", ""))

    if not counts:
        return None

    refill_minutes = None
    refill_match = re.search(
        r"(?:(\d+)\s*h\s*)?(\d+)\s*min(?:ute)?s?\s+before\s+the\s+refill",
        normalized,
        re.IGNORECASE,
    )
    if refill_match:
        refill_minutes = int(refill_match.group(1) or 0) * 60 + int(refill_match.group(2))

    return SphereGameStatus(
        oh=counts.get("oh", 0),
        oc=counts.get("oc", 0),
        oq=counts.get("oq", 0),
        ot=counts.get("ot", 0),
        refill_minutes=refill_minutes,
        oh_stored=stored_counts.get("oh", 0),
        oc_stored=stored_counts.get("oc", 0),
        oq_stored=stored_counts.get("oq", 0),
        ot_stored=stored_counts.get("ot", 0),
    )


def normalize_sphere_emoji(value) -> str:
    name = getattr(value, "name", value)
    normalized = str(name or "")
    if normalized.startswith("sp") and normalized.endswith("2"):
        return normalized[:-1]
    return normalized


def harvest_reveal_is_free(value) -> bool:
    """Return whether an $oh result grants another click instead of spending one."""
    return normalize_sphere_emoji(value) == "spP"


def count_harvest_bonus_clicks(text: str) -> int:
    """Count separate $oh result lines where a dark sphere becomes a free purple."""
    return len(re.findall(
        r"\bspD\b.{0,80}?\bturns\s+into\b.{0,80}?\bspP\b",
        str(text or ""),
        re.IGNORECASE | re.DOTALL,
    ))


def _coordinates(index: int) -> Tuple[int, int]:
    return divmod(index, BOARD_SIZE)


def _matches_red_relation(clue: str, clue_position: int, red_position: int) -> bool:
    clue_row, clue_column = _coordinates(clue_position)
    red_row, red_column = _coordinates(red_position)
    row_delta = abs(clue_row - red_row)
    column_delta = abs(clue_column - red_column)
    same_row_or_column = row_delta == 0 or column_delta == 0
    same_diagonal = row_delta == column_delta and row_delta > 0

    if clue == "spO":
        return max(row_delta, column_delta) == 1
    if clue == "spY":
        return same_diagonal
    if clue == "spG":
        return same_row_or_column
    if clue == "spT":
        return same_row_or_column or same_diagonal
    if clue == "spB":
        return not same_row_or_column and not same_diagonal
    return True


def chest_red_candidates(emojis: Sequence[str]) -> Tuple[int, ...]:
    """Return every red location compatible with the currently revealed clues."""
    board = [normalize_sphere_emoji(value) for value in emojis]
    if len(board) != BOARD_CELLS:
        return ()

    known_red = [index for index, name in enumerate(board) if name == RED_SPHERE]
    if known_red:
        return tuple(known_red)

    center = BOARD_CELLS // 2
    candidates = []
    for red_position in range(BOARD_CELLS):
        if red_position == center or board[red_position] != UNKNOWN_SPHERE:
            continue
        compatible = True
        for clue_position, clue in enumerate(board):
            if clue not in {"spO", "spY", "spG", "spT", "spB"}:
                continue
            if not _matches_red_relation(clue, clue_position, red_position):
                compatible = False
                break
        if compatible:
            candidates.append(red_position)
    return tuple(candidates)


def _chest_information_score(position: int, candidates: Iterable[int]) -> Tuple[int, int, int, int]:
    candidates = tuple(candidates)
    result_sizes = [1 if position in candidates else 0]
    remaining_candidates = tuple(red for red in candidates if red != position)
    for clue in ("spO", "spY", "spG", "spT", "spB"):
        result_sizes.append(sum(_matches_red_relation(clue, position, red) for red in remaining_candidates))
    nonempty_sizes = [size for size in result_sizes if size]
    row, column = _coordinates(position)
    center_distance = abs(row - 2) + abs(column - 2)
    return (
        max(nonempty_sizes or [0]),
        sum(size * size for size in nonempty_sizes),
        center_distance,
        position,
    )


_SPHERE_VALUES = {
    "spP": 5.0,
    "spB": 10.0,
    "spT": 20.0,
    "spG": 35.0,
    "spY": 55.0,
    "spO": 90.0,
    "spR": 150.0,
    RED_SPHERE: 150.0,
    "spD": 110.0,
    "spM": 180.0,
    "spL": 240.0,
    "spW": 500.0,
}


def _chest_unknown_value(board: Sequence[str], red_position: int, position: int) -> float:
    """Estimate a hidden chest cell from its geometry and remaining color quotas."""
    red_row, red_column = _coordinates(red_position)
    row, column = _coordinates(position)
    row_delta = abs(row - red_row)
    column_delta = abs(column - red_column)
    adjacent = max(row_delta, column_delta) == 1
    diagonal = row_delta == column_delta and row_delta > 0
    row_or_column = row_delta == 0 or column_delta == 0

    if not diagonal and not row_or_column:
        return _SPHERE_VALUES["spB"]

    base_value = _SPHERE_VALUES["spT"]
    unknown_positions = [
        index for index, name in enumerate(board)
        if name == UNKNOWN_SPHERE and index != red_position
    ]

    if diagonal:
        diagonal_unknown = [
            index for index in unknown_positions
            if (lambda delta: delta[0] == delta[1] and delta[0] > 0)(
                (abs(_coordinates(index)[0] - red_row), abs(_coordinates(index)[1] - red_column))
            )
        ]
        remaining_yellow = max(0, 3 - sum(name == "spY" for name in board))
        yellow_probability = min(1.0, remaining_yellow / max(1, len(diagonal_unknown)))
        base_value += yellow_probability * (_SPHERE_VALUES["spY"] - base_value)
    elif row_or_column:
        aligned_unknown = [
            index for index in unknown_positions
            if (_coordinates(index)[0] == red_row or _coordinates(index)[1] == red_column)
        ]
        remaining_green = max(0, 4 - sum(name == "spG" for name in board))
        green_probability = min(1.0, remaining_green / max(1, len(aligned_unknown)))
        base_value += green_probability * (_SPHERE_VALUES["spG"] - base_value)

    if adjacent:
        adjacent_unknown = [
            index for index in unknown_positions
            if max(
                abs(_coordinates(index)[0] - red_row),
                abs(_coordinates(index)[1] - red_column),
            ) == 1
        ]
        remaining_orange = max(0, 2 - sum(name == "spO" for name in board))
        orange_probability = min(1.0, remaining_orange / max(1, len(adjacent_unknown)))
        base_value += orange_probability * (_SPHERE_VALUES["spO"] - base_value)

    return base_value


def choose_chest_reward_position(
    emojis: Sequence[str],
    disabled: Sequence[bool],
    red_position: int,
) -> Optional[int]:
    """Spend post-red $oc clicks on the enabled cell with the best expected value."""
    board = [normalize_sphere_emoji(value) for value in emojis]
    blocked = [bool(value) for value in disabled]
    if len(board) != BOARD_CELLS or len(blocked) != BOARD_CELLS:
        return None

    enabled = [index for index in range(BOARD_CELLS) if not blocked[index]]
    if not enabled:
        return None

    def expected_value(position: int) -> Tuple[float, int]:
        name = board[position]
        value = (
            _chest_unknown_value(board, red_position, position)
            if name == UNKNOWN_SPHERE
            else _SPHERE_VALUES.get(name, 0.0)
        )
        return value, -position

    return max(enabled, key=expected_value)


def choose_chest_position(emojis: Sequence[str], disabled: Sequence[bool]) -> Optional[int]:
    """Choose the next enabled $oc cell using all revealed geometry clues."""
    board = [normalize_sphere_emoji(value) for value in emojis]
    blocked = [bool(value) for value in disabled]
    if len(board) != BOARD_CELLS or len(blocked) != BOARD_CELLS:
        return None

    red_positions = [index for index, name in enumerate(board) if name == RED_SPHERE]
    for red_position in red_positions:
        if not blocked[red_position]:
            return red_position
    if red_positions:
        return choose_chest_reward_position(board, blocked, red_positions[0])

    enabled_unknown = [
        index for index, name in enumerate(board)
        if name == UNKNOWN_SPHERE and not blocked[index]
    ]
    if not enabled_unknown:
        return None

    revealed_clues = any(name != UNKNOWN_SPHERE for name in board)
    center = BOARD_CELLS // 2
    if not revealed_clues and center in enabled_unknown:
        return center

    candidates = chest_red_candidates(board)
    if candidates:
        candidate_clicks = [position for position in candidates if position in enabled_unknown]
        if len(candidate_clicks) == 1:
            return candidate_clicks[0]
        return min(enabled_unknown, key=lambda position: _chest_information_score(position, candidates))

    # Unexpected/localized clues should never stall the game completely.
    fallback = [position for position in enabled_unknown if position != center]
    return min(fallback or enabled_unknown)


_HARVEST_UNKNOWN_VALUE = 65.0


def choose_harvest_position(
    emojis: Sequence[str],
    disabled: Sequence[bool],
    paid_clicks: int = 0,
) -> Optional[int]:
    """Choose an $oh cell with an EV-oriented reveal and endgame heuristic."""
    board = [normalize_sphere_emoji(value) for value in emojis]
    blocked = [bool(value) for value in disabled]
    if len(board) != BOARD_CELLS or len(blocked) != BOARD_CELLS:
        return None
    enabled = [index for index in range(BOARD_CELLS) if not blocked[index]]
    if not enabled:
        return None

    def closest_to_center(positions):
        return min(
            positions,
            key=lambda index: (
                abs(_coordinates(index)[0] - 2) + abs(_coordinates(index)[1] - 2),
                index,
            ),
        )

    purple = [index for index in enabled if board[index] == "spP"]
    if purple:
        return closest_to_center(purple)

    guaranteed_high_value = [
        index for index in enabled
        if board[index] in {"spW", "spL", "spM", "spR", "spO", "spY", "spG"}
    ]
    unknown = [index for index in enabled if board[index] == UNKNOWN_SPHERE]
    used_clicks = max(0, int(paid_clicks or 0))

    # Secure visible green-or-better rewards before exploring more blue/teal
    # reveal chains, matching the guaranteed-value preference users expect.
    if guaranteed_high_value:
        return max(guaranteed_high_value, key=lambda index: (_SPHERE_VALUES[board[index]], -index))

    # Early unknown clicks can expose blue/teal chains, purple free clicks, or the
    # hidden $oc reward while the guaranteed prizes remain available for later.
    if used_clicks < 3 and unknown:
        return closest_to_center(unknown)

    dark = [index for index in enabled if board[index] == "spD"]
    if used_clicks == 3 and dark:
        return closest_to_center(dark)

    if used_clicks < 4 and unknown:
        return closest_to_center(unknown)

    def expected_value(position: int) -> Tuple[float, int]:
        value = (
            _HARVEST_UNKNOWN_VALUE
            if board[position] == UNKNOWN_SPHERE
            else _SPHERE_VALUES.get(board[position], 0.0)
        )
        return value, -position

    return max(enabled, key=expected_value)
