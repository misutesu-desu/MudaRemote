"""Parsing and deterministic board choices for Mudae sphere mini-games."""

from dataclasses import dataclass, field
from itertools import combinations
import re
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


BOARD_SIZE = 5
BOARD_CELLS = BOARD_SIZE * BOARD_SIZE
UNKNOWN_SPHERE = "spU"
RED_SPHERE = "sp"
SPHERE_GAME_KINDS = ("oh", "oc", "oq", "ot")


def any_sphere_game_enabled(client) -> bool:
    return any(getattr(client, f"auto_{kind}_enabled", False) for kind in SPHERE_GAME_KINDS)


def parse_sphere_button_count(text):
    """Read the sphere quota without confusing it with Perk 8/9 counters."""
    match = re.search(
        r"(\d+)\s*/\s*(\d+)\s+buttons\s+clicked\b",
        str(text or "").replace("**", ""), re.IGNORECASE,
    )
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


class SphereButtonBudget:
    """Keep authoritative usage separate from clicks awaiting a status snapshot."""

    def __init__(self):
        self.clicked = None
        self.limit = None
        self.pending = {}

    def observe(self, text, requested_at):
        count = parse_sphere_button_count(text)
        if count is None:
            return False
        self.clicked, self.limit = count
        # Clicks sent during the query may not appear in its snapshot yet.
        self.pending = {key: sent_at for key, sent_at in self.pending.items()
                        if sent_at >= requested_at}
        return True

    @property
    def available(self):
        return self.limit is None or self.clicked + len(self.pending) < self.limit

    def reserve(self, key, sent_at):
        self.pending[key] = sent_at

    def cancel(self, key):
        self.pending.pop(key, None)


def sphere_click_recovery_decision(previous_snapshot, latest_snapshot, attempts_used, max_attempts=2):
    """Classify an acknowledged or ambiguous logical board click."""
    if latest_snapshot is not None and latest_snapshot != previous_snapshot:
        return "delivered"
    if max(0, int(attempts_used or 0)) < max(1, int(max_attempts or 1)):
        return "retry"
    return "stop"


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

    def parse_count(value: Optional[str]) -> int:
        token = str(value or "0").strip()
        if token in {"-", "–", "—"}:
            return 0
        try:
            return max(0, int(token.replace(",", "")))
        except ValueError:
            return 0

    for game in ("oh", "oc", "oq", "ot"):
        match = re.search(
            r"([-–—]|-?[\d,]+)\s+\$" + game + r"\b"
            # Mudae localizes the label after the bonus count (for example,
            # "stored" and "armazenados"), while the (+N ...) shape is stable.
            r"(?:[^,$\r\n]*?\(\s*\+\s*([-–—]|-?[\d,]+)(?:\s+[^)]*)?\))?",
            normalized,
            re.IGNORECASE,
        )
        if match:
            counts[game] = parse_count(match.group(1))
            stored_counts[game] = parse_count(match.group(2))

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
        return (row_delta + column_delta) == 1
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
    "spL": 240.0,
    "spW": 500.0,
}


def _chest_unknown_value(board: Sequence[str], red_position: int, position: int) -> float:
    """Estimate a hidden chest cell from its geometry and remaining color quotas."""
    red_row, red_column = _coordinates(red_position)
    row, column = _coordinates(position)
    row_delta = abs(row - red_row)
    column_delta = abs(column - red_column)
    adjacent = (row_delta + column_delta) == 1
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


def _chest_unknown_priority_probability(
    board: Sequence[str],
    red_position: int,
    position: int,
    target: str,
) -> float:
    """Estimate whether a hidden cell matches one configured $oc reward."""
    if board[position] != UNKNOWN_SPHERE:
        return 1.0 if board[position] == target else 0.0

    red_row, red_column = _coordinates(red_position)

    def relation(index: int):
        row, column = _coordinates(index)
        row_delta = abs(row - red_row)
        column_delta = abs(column - red_column)
        adjacent = (row_delta + column_delta) == 1
        diagonal = row_delta == column_delta and row_delta > 0
        aligned = row_delta == 0 or column_delta == 0
        return adjacent, diagonal, aligned

    adjacent, diagonal, aligned = relation(position)
    eligibility = {
        "spO": adjacent,
        "spY": diagonal,
        "spG": aligned,
        "spT": aligned or diagonal,
        "spB": not aligned and not diagonal,
    }
    if not eligibility.get(target, False):
        return 0.0

    fixed_quotas = {"spO": 2, "spY": 3, "spG": 4}
    if target in fixed_quotas:
        remaining = max(0, fixed_quotas[target] - sum(name == target for name in board))
        eligible_unknown = sum(
            name == UNKNOWN_SPHERE
            and {
                "spO": relation(index)[0],
                "spY": relation(index)[1],
                "spG": relation(index)[2],
            }[target]
            for index, name in enumerate(board)
            if index != red_position
        )
        return min(1.0, remaining / max(1, eligible_unknown))

    # Blue is the only possible colour outside the red's row, column and
    # diagonals. Teal is restricted to those relations, but has no fixed quota.
    if target == "spB":
        return 1.0
    if target == "spT":
        return 0.5
    return 0.0


def choose_chest_reward_position(
    emojis: Sequence[str],
    disabled: Sequence[bool],
    red_position: int,
    priority_order: Optional[Sequence[str]] = None,
) -> Optional[int]:
    """Spend post-red $oc clicks on the enabled cell with the best expected value."""
    board = [normalize_sphere_emoji(value) for value in emojis]
    blocked = [bool(value) for value in disabled]
    if len(board) != BOARD_CELLS or len(blocked) != BOARD_CELLS:
        return None

    enabled = [index for index in range(BOARD_CELLS) if not blocked[index]]
    if not enabled:
        return None

    configured_order = tuple(
        normalize_sphere_emoji(name)
        for name in priority_order or ()
        if str(name or "").strip()
    )

    def expected_value(position: int):
        name = board[position]
        if configured_order:
            # Revealed configured rewards are deterministic. For still-hidden
            # cells, use the chest's published geometry so an orange-first
            # preset searches next to red instead of falling back to top-left.
            probabilities = tuple(
                _chest_unknown_priority_probability(
                    board,
                    red_position,
                    position,
                    target,
                )
                for target in configured_order
            )
            fallback_value = (
                _chest_unknown_value(board, red_position, position)
                if name == UNKNOWN_SPHERE
                else _SPHERE_VALUES.get(name, 0.0)
            )
            return probabilities + (name != UNKNOWN_SPHERE, fallback_value, -position)
        value = (
            _chest_unknown_value(board, red_position, position)
            if name == UNKNOWN_SPHERE
            else _SPHERE_VALUES.get(name, 0.0)
        )
        return value, -position

    return max(enabled, key=expected_value)


# Optimal $oc play: an exact Bellman DP over every board Mudae can deal (red on
# one of the 24 non-centre cells, 2 orange next to it, 3 yellow on its
# diagonals, 4 green on its row/column, teal/blue for the rest), maximising the
# expected sphere total of all 5 clicks. With red equally likely on each cell
# it averages 344.7 SP per board; the clue heuristic below averaged ~301.
# Entry format "<clicked cells>:<next cell>": a cell is its index as a letter
# (a = top-left ... y = bottom-right), a clicked cell is followed by
# R/O/Y/G/T/B. Only states reached under optimal play are stored; anything
# else (an unexpected emoji or layout) falls back to the heuristic.
_CHEST_POLICY = (
    ":i iB:k iG:x iO:h iR:n iT:e iY:o eBiT:f eGiT:c eOiT:d eRiT:d eTiT:c eYiT:p hGiO:j hRiO:c hTiO:j "
    "hYiO:d iBkB:t iBkG:f iBkO:p iBkR:l iBkT:f iBkY:r iGxB:g iGxG:n iGxO:s iGxR:s iGxT:n iGxY:a "
    "iRnG:d iRnO:d iRnT:d iYoB:p iYoG:d iYoR:j iYoT:d iYoY:b aGiGxY:g aOiGxY:f aTiGxY:f bGiYoY:d "
    "bOiYoY:c bTiYoY:c cBeTiT:l cGhRiO:g cOhRiO:l cReGiT:b cReTiT:b cThRiO:m cYeGiT:j cYeTiT:j "
    "dGhYiO:n dGiRnG:h dGiRnO:h dGiRnT:h dGiYoT:c dOeRiT:j dOiRnG:h dOiRnO:m dOiRnT:j dOiYoG:e "
    "dOiYoT:e dReOiT:h dRhYiO:c dTeOiT:j dThYiO:n dTiRnG:h dTiRnO:j dTiRnT:h dTiYoT:b dYeOiT:j "
    "eBfBiT:s eBfGiT:g eBfOiT:l eBfRiT:a eBfTiT:s eBfYiT:x eYiTpG:q eYiTpO:u eYiTpT:l fBiBkT:v "
    "fGiBkG:p fGiBkT:p fOiBkG:a fOiBkT:a fTiBkG:l fTiBkT:l fYiBkG:l fYiBkT:l gGiGxB:j gOiGxB:c "
    "gRiGxB:l gTiGxB:j hGiOjR:e hTiOjR:e hTiOjT:n hTiOjY:d iBkBtB:v iBkBtG:s iBkBtO:x iBkBtR:s "
    "iBkBtT:h iBkBtY:a iBkOpR:q iBkOpT:q iBkOpY:q iBkRlG:f iBkRlO:f iBkRlT:f iBkYrG:w iBkYrO:w "
    "iBkYrT:v iGnBxT:a iGnGxG:d iGnGxT:d iGnOxG:t iGnOxT:s iGnRxG:s iGnRxT:s iGnTxG:d iGnTxT:d "
    "iGsGxR:w iGsOxR:w iGsRxO:t iGsTxR:w iYjGoR:n iYjOoR:n iYjToR:n iYoBpG:q iYoBpO:u iYoBpT:q "
    "aGeBfRiT:g aGgOiGxY:f aGiBkBtY:b aGiGnBxT:f aOeBfRiT:g aOfRiGxY:k aOiBkBtY:b aOiGnBxT:f "
    "aRfOiBkG:b aRfOiBkT:b aTeBfRiT:g aTfRiGxY:g aTiBkBtY:b aTiGnBxT:f bGcReGiT:d bGcReTiT:d "
    "bGdOiYoY:c bOcReGiT:h bOcReTiT:d bOcRiYoY:h bOdTiYoT:c bTcReGiT:d bTcReTiT:d bTcRiYoY:d "
    "cBeTiTlG:q cBeTiTlO:q cBeTiTlT:q cGdRhYiO:e cGgGhRiO:m cGgOhRiO:t cGgOiGxB:h cGgThRiO:m "
    "cOdRhYiO:j cOgOiGxB:h cOhRiOlT:d cOhRiOlY:b cRdGiYoT:b cTdRhYiO:e cTgOiGxB:h cThRiOmG:g "
    "cThRiOmO:b cThRiOmT:g cYeGiTjG:o cYeGiTjO:o cYeGiTjT:o cYeTiTjG:o cYeTiTjO:o cYeTiTjT:o "
    "dGhGiRnO:j dGhOiRnG:j dGhOiRnO:u dGhOiRnT:j dGhTiOjY:n dGhTiRnO:j dGhYiOnR:m dGiGnGxG:s "
    "dGiGnGxT:s dGiGnTxG:s dGiGnTxT:s dOeGiYoT:c dOeRiTjO:m dOeRiYoG:j dOeRiYoT:j dOeTiYoT:c "
    "dOhGiRnG:j dOhOiRnG:u dOhTiRnG:j dOiRjGnT:h dOiRjOnT:c dOiRjTnT:h dOiRmTnO:e dOiRmYnO:c "
    "dReOhTiT:c dReOhYiT:c dRhTiOjY:c dRiGnGxG:c dRiGnGxT:c dRiGnTxG:c dRiGnTxT:c dTeOiTjR:o "
    "dThOiRnG:j dThOiRnT:j dThTiOjY:n dThYiOnR:o dTiGnGxG:s dTiGnGxT:s dTiGnTxG:s dTiRjGnO:h "
    "dTiRjOnO:c dTiRjTnO:h dYeOiTjR:o eBfBiTsG:n eBfBiTsO:n eBfBiTsR:n eBfBiTsT:n eBfGgGiT:h "
    "eBfGgOiT:h eBfGgRiT:h eBfGgTiT:h eBfOiTlG:g eBfOiTlO:g eBfOiTlT:g eBfTiTsB:h eBfTiTsG:x "
    "eBfTiTsO:x eBfTiTsT:g eBfTiTsY:g eBfYiTxR:w eGhGiOjR:o eGhTiOjR:o eOhGiOjR:n eOhTiOjR:n "
    "eThGiOjR:o eThTiOjR:o eYiTlGpT:q eYiTlOpT:q eYiTlTpT:q eYiTpGqR:l eYiTpOuR:v eYiTpOuT:q "
    "eYiTpOuY:q fBiBkTvG:w fBiBkTvO:w fBiBkTvT:w fGiBkGpR:q fGiBkRlO:p fGiBkTpR:q fOiBkRlG:p "
    "fOiBkRlO:g fOiBkRlT:p fTiBkGlR:m fTiBkGlT:p fTiBkGlY:p fTiBkRlO:p fTiBkTlR:g fTiBkTlT:p "
    "fTiBkTlY:p fYiBkGlR:m fYiBkTlR:g gGiGjGxB:h gGiGjRxB:e gGiGjTxB:h gRiGlGxB:f gRiGlOxB:h "
    "gRiGlTxB:f gTiGjGxB:h gTiGjRxB:e gTiGjTxB:h hGiBkBtT:r hTiBkBtT:r hTiOjTnR:m hYiBkBtT:b "
    "iBkBsGtG:r iBkBsGtR:o iBkBsOtG:r iBkBsOtR:o iBkBsTtG:r iBkBsTtR:o iBkBtBvR:q iBkBtOxO:y "
    "iBkOpRqG:u iBkOpRqO:h iBkOpRqT:u iBkOpTqG:l iBkOpTqO:l iBkOpTqT:l iBkOpYqG:l iBkOpYqO:l "
    "iBkOpYqT:l iBkYrGwR:v iBkYrOwR:x iBkYrTvO:w iGnOsRxT:r iGnOtGxG:s iGnOtOxG:s iGnOtTxG:s "
    "iGnRsGxG:m iGnRsGxT:m iGnRsOxG:m iGnRsOxT:m iGnRsTxG:m iGnRsTxT:m iGsGwOxR:y iGsOwGxR:y "
    "iGsOwOxR:l iGsOwTxR:y iGsRtGxO:n iGsRtOxO:y iGsRtTxO:n iGsTwOxR:y iYjGnOoR:t iYjOnGoR:t "
    "iYjOnOoR:c iYjOnToR:t iYjTnOoR:t iYoBpGqR:r iYoBpOuR:v iYoBpOuT:q iYoBpOuY:q iYoBpTqR:l "
)
_CHEST_POLICY_CODES = {
    RED_SPHERE: "R", "spR": "R", "spO": "O", "spY": "Y", "spG": "G", "spT": "T", "spB": "B",
}
_chest_policy_table: Optional[Dict[str, str]] = None


def _chest_policy_position(board: Sequence[str], blocked: Sequence[bool]) -> Optional[int]:
    """Look up the optimal next $oc click; None when the board is off the table."""
    global _chest_policy_table
    table = _chest_policy_table
    if table is None:
        table = {}
        for entry in _CHEST_POLICY.split():
            state, move = entry.split(":")
            table[state] = move
        _chest_policy_table = table
    key = []
    for index in range(BOARD_CELLS):
        if not blocked[index]:
            continue
        code = _CHEST_POLICY_CODES.get(board[index])
        if code is None:
            return None
        key.append(chr(97 + index) + code)
    move = table.get("".join(key))
    if move is None:
        return None
    position = ord(move) - 97
    return None if blocked[position] else position


def choose_chest_position(
    emojis: Sequence[str],
    disabled: Sequence[bool],
    reward_priority_order: Optional[Sequence[str]] = None,
) -> Optional[int]:
    """Choose the next enabled $oc cell: optimal table first, clue heuristic as fallback."""
    board = [normalize_sphere_emoji(value) for value in emojis]
    blocked = [bool(value) for value in disabled]
    if len(board) != BOARD_CELLS or len(blocked) != BOARD_CELLS:
        return None

    red_positions = [index for index, name in enumerate(board) if name == RED_SPHERE]
    for red_position in red_positions:
        if not blocked[red_position]:
            return red_position
    # A configured after-red priority is the user's choice of rewards; the
    # table only maximises the default sphere values.
    if not (red_positions and any(str(name or "").strip() for name in reward_priority_order or ())):
        position = _chest_policy_position(board, blocked)
        if position is not None:
            return position
    if red_positions:
        return choose_chest_reward_position(
            board,
            blocked,
            red_positions[0],
            priority_order=reward_priority_order,
        )

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


# $oh model measured on 12,670 real boards (community data set): every hidden
# button is drawn independently with these rates, so positions carry no
# information. A covered spU can also be the Hidden Ourosphere: it is on half
# of the boards, never shows before it is clicked (an unveil that lands on it
# leaves it covered) and grants one $oc use instead of spheres.
_HARVEST_RATES = (
    ("spB", 0.54519653), ("spT", 0.23461405), ("spG", 0.07858879), ("spP", 0.03920758),
    ("spL", 0.02964167), ("spY", 0.02584373), ("spD", 0.01459511), ("spO", 0.00976796),
    ("spR", 0.00227624), ("spW", 0.00039148),
)
_HARVEST_RATE_TOTAL = sum(rate for _, rate in _HARVEST_RATES)
_HARVEST_RATES = tuple((name, rate / _HARVEST_RATE_TOTAL) for name, rate in _HARVEST_RATES)
# What a dark sphere turns into; purple refunds the click.
_HARVEST_DARK_RATES = (
    ("spG", 0.11820403), ("spO", 0.1154551), ("spY", 0.11392792), ("spL", 0.11301161),
    ("spR", 0.11240073), ("spB", 0.10904093), ("spW", 0.10843005), ("spT", 0.10751374),
    ("spP", 0.10201588),
)
_HARVEST_VALUES = {
    "spB": 10.0, "spT": 20.0, "spG": 35.0, "spY": 55.0, "spL": 76.2208, "spO": 90.0,
    "spR": 150.0, RED_SPHERE: 150.0, "spW": 500.0, "spP": 5.0,
}
_HARVEST_FLATS = ("spG", "spY", "spL", "spO", "spR", RED_SPHERE, "spW")
_HARVEST_DARK_PURPLE = dict(_HARVEST_DARK_RATES)["spP"]
_HARVEST_DARK_SPHERES = sum(
    rate * _HARVEST_VALUES[name] for name, rate in _HARVEST_DARK_RATES if name != "spP"
)
# One $oc use played with _CHEST_POLICY.
_HARVEST_HIDDEN_VALUE = 344.7
# With more clicks left the exact search always opens a covered button (the
# Hidden Ourosphere chance outweighs everything); the hard choices come last.
_HARVEST_EXACT_CLICKS = 3


def _add_harvest_flat(flats: Tuple[float, ...], value: float, keep: int) -> Tuple[float, ...]:
    if len(flats) >= keep and (keep <= 0 or value <= flats[-1]):
        return flats[:keep]
    return tuple(sorted(flats + (value,), reverse=True)[:keep])


class _HarvestSolver:
    """Exact expected-sphere search over position-free $oh counts.

    A state is: clicks left, covered buttons, visible blue/teal/dark counts,
    the best visible flat rewards, and the Hidden Ourosphere: 0 = gone,
    1 = possible (each covered button is it with chance 1/(covered + s),
    s = covered buttons when the board opened), 2 = confirmed (1/covered).
    Unveils are walked one button at a time, which is exact because draws are
    independent; free purples are always clicked at once.
    """

    def __init__(self, initial_covered: int):
        self.s = max(0, int(initial_covered))
        self._values: Dict[tuple, float] = {}
        self._reveals: Dict[tuple, float] = {}

    def _hidden_chance(self, covered: int, hidden: int) -> float:
        if hidden == 0 or covered <= 0:
            return 0.0
        return 1.0 / covered if hidden == 2 else 1.0 / (covered + self.s)

    @property
    def size(self) -> int:
        return len(self._values) + len(self._reveals)

    def value(self, k, nc, nb, nt, nd, flats, hidden) -> float:
        if k <= 0:
            return 0.0
        # More buttons of a kind than clicks left change nothing.
        if nb > k:
            nb = k
        if nt > k:
            nt = k
        if nd > k + 1:
            nd = k + 1
        if len(flats) > k:
            flats = flats[:k]
        key = (k, nc, nb, nt, nd, flats, hidden)
        cached = self._values.get(key)
        if cached is None:
            cached = self._values[key] = self.best(*key)[0]
        return cached

    def _reveal(self, k, nc, nb, nt, nd, flats, hidden, pending, excluded) -> float:
        """Value once `pending` random covered buttons are unveiled."""
        if pending <= 0 or nc - excluded <= 0 or k <= 0:
            return self.value(k, nc, nb, nt, nd, flats, hidden)
        if nb > k:
            nb = k
        if nt > k:
            nt = k
        if nd > k + 1:
            nd = k + 1
        if len(flats) > k:
            flats = flats[:k]
        key = (k, nc, nb, nt, nd, flats, hidden, pending, excluded)
        cached = self._reveals.get(key)
        if cached is not None:
            return cached
        # An unveil that lands on the Hidden Ourosphere leaves it covered and
        # proves it is there; it cannot be drawn again in the same unveil.
        chance = 0.0 if excluded else self._hidden_chance(nc, hidden)
        total = chance * self._reveal(k, nc, nb, nt, nd, flats, 2, pending - 1, 1) if chance else 0.0
        nc, pending = nc - 1, pending - 1
        rest = 0.0
        for name, rate in _HARVEST_RATES:
            if name == "spB":
                rest += rate * self._reveal(k, nc, nb + 1, nt, nd, flats, hidden, pending, excluded)
            elif name == "spT":
                rest += rate * self._reveal(k, nc, nb, nt + 1, nd, flats, hidden, pending, excluded)
            elif name == "spD":
                rest += rate * self._reveal(k, nc, nb, nt, nd + 1, flats, hidden, pending, excluded)
            elif name == "spP":
                rest += rate * (5.0 + self._reveal(k, nc, nb, nt, nd, flats, hidden, pending, excluded))
            else:
                rest += rate * self._reveal(
                    k, nc, nb, nt, nd, _add_harvest_flat(flats, _HARVEST_VALUES[name], k),
                    hidden, pending, excluded,
                )
        total += (1.0 - chance) * rest
        self._reveals[key] = total
        return total

    def _dark(self, k, nc, nb, nt, nd, flats, hidden) -> float:
        return (
            _HARVEST_DARK_SPHERES
            + (1.0 - _HARVEST_DARK_PURPLE) * self.value(k - 1, nc, nb, nt, nd, flats, hidden)
            + _HARVEST_DARK_PURPLE * (5.0 + self.value(k, nc, nb, nt, nd, flats, hidden))
        )

    def _covered(self, k, nc, nb, nt, nd, flats, hidden) -> float:
        chance = self._hidden_chance(nc, hidden)
        nc -= 1
        total = (
            chance * (_HARVEST_HIDDEN_VALUE + self.value(k - 1, nc, nb, nt, nd, flats, 0))
            if chance else 0.0
        )
        rest = 0.0
        for name, rate in _HARVEST_RATES:
            if name == "spB":
                outcome = 10.0 + self._reveal(k - 1, nc, nb, nt, nd, flats, hidden, 3, 0)
            elif name == "spT":
                outcome = 20.0 + self._reveal(k - 1, nc, nb, nt, nd, flats, hidden, 1, 0)
            elif name == "spP":
                outcome = 5.0 + self.value(k, nc, nb, nt, nd, flats, hidden)
            elif name == "spD":
                outcome = self._dark(k, nc, nb, nt, nd, flats, hidden)
            else:
                outcome = _HARVEST_VALUES[name] + self.value(k - 1, nc, nb, nt, nd, flats, hidden)
            rest += rate * outcome
        return total + (1.0 - chance) * rest

    def best(self, k, nc, nb, nt, nd, flats, hidden) -> Tuple[float, Optional[str]]:
        options = []
        if flats:
            options.append((flats[0] + self.value(k - 1, nc, nb, nt, nd, flats[1:], hidden), "flat"))
        if nd:
            options.append((self._dark(k, nc, nb, nt, nd - 1, flats, hidden), "dark"))
        if nb:
            options.append((10.0 + self._reveal(k - 1, nc, nb - 1, nt, nd, flats, hidden, 3, 0), "blue"))
        if nt:
            options.append((20.0 + self._reveal(k - 1, nc, nb, nt - 1, nd, flats, hidden, 1, 0), "teal"))
        if nc:
            options.append((self._covered(k, nc, nb, nt, nd, flats, hidden), "covered"))
        return max(options) if options else (0.0, None)


# Values only depend on the opening covered count, so later clicks on the same
# board reuse the first search. Bounded: a cold search stores ~30k states.
_HARVEST_SOLVER_STATE_LIMIT = 150000
_harvest_solvers: Dict[int, _HarvestSolver] = {}


def _harvest_solver(initial_covered: int) -> _HarvestSolver:
    solver = _harvest_solvers.get(initial_covered)
    if solver is None or solver.size > _HARVEST_SOLVER_STATE_LIMIT:
        if sum(cached.size for cached in _harvest_solvers.values()) > _HARVEST_SOLVER_STATE_LIMIT:
            _harvest_solvers.clear()
        solver = _harvest_solvers[initial_covered] = _HarvestSolver(initial_covered)
    return solver


_HARVEST_UNVEILS = {"spB": 3, "spT": 1}


def harvest_unveil_fell_short(before_emojis, before_disabled, after_emojis, after_disabled, position) -> bool:
    """Whether a blue/teal click unveiled one button fewer than it should have.

    The missing unveil landed on the Hidden Ourosphere, which stays covered.
    A dark that turned blue/teal unveils nothing, and a gap larger than one
    is more likely a partial board edit, so neither counts.
    """
    if not 0 <= position < min(len(before_emojis), len(after_emojis)):
        return False
    clicked = normalize_sphere_emoji(before_emojis[position])
    unveils = _HARVEST_UNVEILS.get(normalize_sphere_emoji(after_emojis[position]))
    if unveils is None or clicked not in {UNKNOWN_SPHERE, "spB", "spT"}:
        return False

    def covered(emojis, disabled):
        return {
            index for index, (name, off) in enumerate(zip(emojis, disabled))
            if normalize_sphere_emoji(name) == UNKNOWN_SPHERE and not off
        }

    pool = covered(before_emojis, before_disabled) - {position}
    unveiled = len(pool - covered(after_emojis, after_disabled))
    return unveiled == min(unveils, len(pool)) - 1


def _closest_to_center(positions: Sequence[int]) -> int:
    return min(positions, key=lambda index: (_center_distance(index), index))


def choose_harvest_position(
    emojis: Sequence[str],
    disabled: Sequence[bool],
    paid_clicks: int = 0,
    priority_order: Optional[Sequence[str]] = None,
    unknown_explore_clicks: int = 3,
    remaining_clicks: Optional[int] = None,
    initial_covered: Optional[int] = None,
    hidden_confirmed: bool = False,
) -> Optional[int]:
    """Pick the next $oh button: free purple, then the best expected sphere total.

    `initial_covered` is the covered count when the board opened and
    `hidden_confirmed` says an unveil fell short (it landed on the Hidden
    Ourosphere); both sharpen where the hidden $oc use can still be.
    """
    if any(str(name or "").strip() for name in priority_order or ()):
        return _choose_harvest_by_priority(
            emojis, disabled, paid_clicks, priority_order, unknown_explore_clicks, remaining_clicks,
        )
    board = [normalize_sphere_emoji(value) for value in emojis]
    blocked = [bool(value) for value in disabled]
    if len(board) != BOARD_CELLS or len(blocked) != BOARD_CELLS:
        return None
    enabled = [index for index in range(BOARD_CELLS) if not blocked[index]]
    if not enabled:
        return None
    clicks_left = max(0, 5 - max(0, int(paid_clicks or 0)) if remaining_clicks is None else int(remaining_clicks))
    if not clicks_left:
        return None

    groups: Dict[str, list] = {}
    for index in enabled:
        groups.setdefault(board[index], []).append(index)
    if groups.get("spP"):
        return _closest_to_center(groups["spP"])
    covered = groups.get(UNKNOWN_SPHERE, [])
    if covered and clicks_left > _HARVEST_EXACT_CLICKS:
        return _closest_to_center(covered)

    flats = sorted(
        (index for name in _HARVEST_FLATS for index in groups.get(name, ())),
        key=lambda index: (-_HARVEST_VALUES[board[index]], _center_distance(index), index),
    )
    if any(blocked[index] and board[index] == UNKNOWN_SPHERE for index in range(BOARD_CELLS)):
        hidden = 0  # the Hidden Ourosphere was already clicked
    else:
        hidden = 2 if hidden_confirmed else 1
    solver = _harvest_solver(max(0, int(len(covered) if initial_covered is None else initial_covered)))
    _, action = solver.best(
        clicks_left,
        len(covered),
        min(len(groups.get("spB", ())), clicks_left),
        min(len(groups.get("spT", ())), clicks_left),
        min(len(groups.get("spD", ())), clicks_left + 1),
        tuple(_HARVEST_VALUES[board[index]] for index in flats[:clicks_left]),
        hidden,
    )
    choices = {
        "flat": flats,
        "dark": groups.get("spD", []),
        "blue": groups.get("spB", []),
        "teal": groups.get("spT", []),
        "covered": covered,
    }.get(action or "")
    if choices:
        return choices[0] if action == "flat" else _closest_to_center(choices)
    # Only unrecognised emojis are left: still finish the board.
    return _closest_to_center(enabled)


_HARVEST_UNKNOWN_VALUE = 65.0


def _choose_harvest_by_priority(
    emojis: Sequence[str],
    disabled: Sequence[bool],
    paid_clicks: int = 0,
    priority_order: Optional[Sequence[str]] = None,
    unknown_explore_clicks: int = 3,
    remaining_clicks: Optional[int] = None,
) -> Optional[int]:
    """The configured-priority $oh path: explore, then harvest by the user's order."""
    board = [normalize_sphere_emoji(value) for value in emojis]
    blocked = [bool(value) for value in disabled]
    if len(board) != BOARD_CELLS or len(blocked) != BOARD_CELLS:
        return None
    enabled = [index for index in range(BOARD_CELLS) if not blocked[index]]
    if not enabled:
        return None
    used_clicks = max(0, int(paid_clicks or 0))
    clicks_left = max(0, 5 - used_clicks if remaining_clicks is None else int(remaining_clicks))
    if not clicks_left:
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

    configured_priority = {
        normalize_sphere_emoji(name): len(priority_order or ()) - index
        for index, name in enumerate(priority_order or ())
    }
    if configured_priority:
        configured_visible = [
            index for index in enabled
            if board[index] != UNKNOWN_SPHERE and board[index] in configured_priority
        ]
        if configured_visible:
            return max(
                configured_visible,
                key=lambda index: (configured_priority[board[index]], -index),
            )
        unknown = [index for index in enabled if board[index] == UNKNOWN_SPHERE]
        if unknown and max(0, int(paid_clicks or 0)) < max(0, int(unknown_explore_clicks or 0)):
            return closest_to_center(unknown)

    unknown = [index for index in enabled if board[index] == UNKNOWN_SPHERE]
    valuable = [
        index for index in enabled
        if _SPHERE_VALUES.get(board[index], 0.0) > _HARVEST_UNKNOWN_VALUE
    ]
    spare_clicks = clicks_left - len(valuable)

    # Reserve enough paid clicks for every reward worth more than exploring.
    # Green/yellow must not consume the early clicks needed for reveal chains.
    if spare_clicks > 0 and unknown and used_clicks < max(0, int(unknown_explore_clicks or 0)):
        return closest_to_center(unknown)

    dark = [index for index in enabled if board[index] == "spD"]
    # Resolve dark before flat rewards when all still fit: a blue/teal result
    # needs a follow-up click, and purple can refund this paid click.
    if clicks_left > 1 and spare_clicks >= 0 and dark:
        return closest_to_center(dark)

    if clicks_left > 1 and spare_clicks > 0 and unknown:
        return closest_to_center(unknown)

    # ponytail: fixed reward estimates, not an exact stochastic solver;
    # replace with a calibrated probability model if measured yield needs it.
    def expected_value(position: int) -> Tuple[float, int]:
        value = (
            _HARVEST_UNKNOWN_VALUE
            if board[position] == UNKNOWN_SPHERE
            else _SPHERE_VALUES.get(board[position], 0.0)
        )
        return value, -position

    return max(enabled, key=expected_value)


def _center_distance(index: int) -> int:
    row, column = _coordinates(index)
    return abs(row - 2) + abs(column - 2)


def _sphere_game_candidates(board: Sequence[str], blocked: Sequence[bool]):
    """Enabled hidden cells; any enabled cell when the board hides nothing."""
    enabled = [index for index in range(BOARD_CELLS) if not blocked[index]]
    hidden = [index for index in enabled if board[index] == UNKNOWN_SPHERE]
    return hidden or enabled


# $oq: four hidden purples; every other revealed color counts its purple
# neighbors (8 tiles around). The 4th purple turns red when 3 are found.
_QUEST_PURPLE_COUNT = 4
_QUEST_CLUES = {"spB": 0, "spT": 1, "spG": 2, "spY": 3, "spO": 4}
# A purple costs no click and moves toward the red, so it outranks any clue.
_QUEST_PURPLE_VALUE = 100.0


def _neighbor_mask(index: int) -> int:
    row, column = _coordinates(index)
    mask = 0
    for other_row in range(max(0, row - 1), min(BOARD_SIZE, row + 2)):
        for other_column in range(max(0, column - 1), min(BOARD_SIZE, column + 2)):
            if (other_row, other_column) != (row, column):
                mask |= 1 << (other_row * BOARD_SIZE + other_column)
    return mask


_NEIGHBOR_MASKS = tuple(_neighbor_mask(index) for index in range(BOARD_CELLS))
_QUEST_ALL_LAYOUTS = tuple(
    sum(1 << index for index in layout)
    for layout in combinations(range(BOARD_CELLS), _QUEST_PURPLE_COUNT)
)


def _bit_count(value: int) -> int:
    return bin(value).count("1")


def quest_purple_layouts(emojis: Sequence[str]) -> Tuple[int, ...]:
    """Return every purple placement (as a bitmask) matching the revealed $oq board."""
    board = [normalize_sphere_emoji(value) for value in emojis]
    if len(board) != BOARD_CELLS:
        return ()
    required = sum(1 << index for index, name in enumerate(board) if name in {"spP", RED_SPHERE})
    excluded = sum(
        1 << index for index, name in enumerate(board)
        if name not in {"spP", RED_SPHERE, UNKNOWN_SPHERE}
    )
    clues = [
        (_NEIGHBOR_MASKS[index], _QUEST_CLUES[name])
        for index, name in enumerate(board) if name in _QUEST_CLUES
    ]
    return tuple(
        layout for layout in _QUEST_ALL_LAYOUTS
        if layout & required == required
        and not layout & excluded
        and all(_bit_count(layout & mask) == count for mask, count in clues)
    )


_QUEST_CLICKS = 7
_QUEST_CLUE_VALUES = (10.0, 20.0, 35.0, 55.0, 90.0)
_QUEST_RED_VALUE = 150.0
_QUEST_PURPLE_SPHERES = 5.0
_QUEST_CODES = {"spB": "B", "spT": "T", "spG": "G", "spY": "Y", "spO": "O", "spP": "P"}
# Up to this many purple layouts the next click is solved exactly on the spot.
_QUEST_EXACT_LAYOUTS = 12
# Decisions of the offline $oq policy (7 clicks) for every board state with
# more than _QUEST_EXACT_LAYOUTS layouts left that it meets on any of the
# 12,650 layouts: open at row 2, column 2, then the exact search on small
# layout sets and purple chance + clue value on large ones. Averages
# 351.8 spheres per board (with red on 95.0% of them) under the
# rules the community measured: the red costs a click, purples are free.
# Entry format as in _CHEST_POLICY, with B/T/G/Y/O for clues and P for purple.
_QUEST_POLICY = (
    ":g gB:s gG:h gO:h gP:m gT:s gY:h gBsB:i gBsG:n gBsO:t gBsP:n gBsT:i gBsY:t gGhB:f gGhG:m gGhO:i "
    "gGhP:i gGhT:f gGhY:i gOhG:k gOhP:l gPmG:h gPmO:h gPmP:h gPmT:b gPmY:h gTsB:i gTsG:n gTsP:n "
    "gTsT:i gTsY:n gYhG:l gYhP:l gYhT:f gYhY:m bGgPmT:f bPgPmT:f bTgPmT:k bYgPmT:a fGgGhT:k fPgGhB:k "
    "fPgGhT:l fPgYhT:k fTgGhT:m gBiBsT:p gBiGsB:d gBiGsT:j gBiPsB:d gBiPsT:j gBiTsT:q gBiYsT:d "
    "gBnBsG:v gBnGsG:o gBnGsP:w gBnPsG:i gBnPsP:r gBnTsG:x gBnTsP:w gBnYsG:i gBnYsP:o gBsOtP:x "
    "gBsYtG:r gBsYtP:x gBsYtY:i gGhGmB:c gGhGmG:l gGhGmP:l gGhGmT:c gGhPiG:l gGhPiO:n gGhPiP:m "
    "gGhPiT:l gGhPiY:n gGhYiG:l gGhYiP:m gGhYiY:m gOhPlP:m gPhGmG:l gPhGmP:l gPhGmY:r gPhOmP:l "
    "gPhPmG:b gPhPmO:c gPhPmY:l gPhTmG:r gPhTmY:l gPhYmG:c gPhYmP:l gPhYmY:l gTiBsB:p gTiBsT:q "
    "gTiGsB:d gTiGsT:d gTiOsT:d gTiPsB:d gTiPsT:h gTiTsB:q gTiTsT:q gTiYsB:d gTiYsT:d gTmPsO:n "
    "gTnBsG:x gTnGsG:r gTnGsP:r gTnGsY:r gTnOsP:o gTnPsG:i gTnPsP:m gTnPsY:r gTnTsG:x gTnTsP:w "
    "gTnTsY:x gTnYsG:i gTnYsP:m gTnYsY:m gYhGlG:m gYhGlP:f gYhGlT:a gYhPlG:b gYhPlP:m gYhPlT:c "
    "gYhPlY:m gYhYmP:l gYhYmT:b aPbYgPmT:c aPgYhGlT:b bGfGgPmT:a bGfPgPmT:k bGgPhPmG:l bGgYhPlG:i "
    "bPfGgPmT:c bPfYgPmT:a bPgYhPlG:c bPgYhYmT:c bTgPkPmT:q bTgPkTmT:j bYgPhPmG:l bYgYhPlG:c "
    "cGgGhGmT:a cGgPhYmG:f cPgGhGmB:b cPgGhGmT:i cPgPhYmG:b cPgYhPlT:d cTgGhGmT:l cYgPhYmG:a "
    "dGgTiGsB:h dGgTiGsT:j dGgTiPsB:h dGgTiYsT:j dPgBiPsB:e dPgBiYsT:e dPgTiGsB:h dPgTiGsT:j "
    "dPgTiPsB:c dPgTiYsB:h dPgTiYsT:j dTgTiGsT:n dTgTiPsB:q dYgTiPsB:e fGgGhTkP:l fGgYhGlP:q "
    "fPgGhBkP:l fPgGhTlG:m fPgGhTlP:r fPgGhTlT:b fPgGhTlY:q fPgYhGlP:k fPgYhTkP:l fTgGhTmP:k "
    "fYgYhGlP:b gBiBpPsT:q gBiGjGsT:n gBiGjPsT:n gBiGnPsG:j gBiGsYtY:j gBiPjGsT:n gBiPjPsT:d "
    "gBiPjTsT:q gBiPjYsT:d gBiPnPsG:j gBiPnYsG:o gBiTnPsG:q gBiTqGsT:p gBiTqPsT:w gBiTqYsT:p "
    "gBiYnPsG:j gBnBsGvG:w gBnBsGvP:w gBnGoGsG:i gBnGoPsG:i gBnGsPwG:x gBnGsPwP:r gBnGsPwT:i "
    "gBnGsPwY:r gBnPrGsP:m gBnPrYsP:m gBnTsGxG:w gBnTsGxP:q gBnTsPwG:p gBnTsPwP:q gBnTsPwY:q "
    "gBnYoPsP:t gBnYoYsP:t gBrPsYtG:x gBsYtPxG:n gBsYtPxP:y gBsYtPxY:n gGhGlGmG:b gGhGlGmP:i "
    "gGhGlPmG:r gGhGlPmP:r gGhGlPmY:r gGhGlTmG:b gGhGlTmP:b gGhGlYmP:q gGhPiGlG:n gGhPiGlP:m "
    "gGhPiGlT:b gGhPiGlY:m gGhPiPmG:d gGhPiPmY:d gGhPiTlG:b gGhPiTlP:m gGhPiTlT:s gGhPiTlY:k "
    "gGhPiYnG:d gGhPiYnP:m gGhPiYnT:b gGhPiYnY:d gGhYiGlP:r gGhYiPmG:c gGhYiPmP:n gGhYiPmT:b "
    "gGhYiYmP:n gPhGlGmG:c gPhGlGmP:n gPhGlPmG:k gPhGlTmG:n gPhGlYmG:c gPhGlYmP:q gPhGmYrG:k "
    "gPhGmYrP:l gPhPlGmY:b gPhPlYmY:b gPhTlYmY:r gPhTmGrG:l gPhTmGrP:l gPhTmGrT:q gPhYlGmP:i "
    "gPhYlGmY:c gPhYlPmY:f gPhYlTmY:c gPhYlYmP:c gThGiPsT:c gThPiPsT:d gThTiPsT:f gThYiPsT:n "
    "gTiBpPsB:k gTiBqGsT:k gTiBqPsT:p gTiBqYsT:p gTiGnPsG:r gTiGnYsG:o gTiPnPsG:h gTiPnYsG:m "
    "gTiTnPsG:r gTiTqGsB:k gTiTqGsT:p gTiTqPsB:l gTiTqPsT:l gTiTqTsT:b gTiTqYsB:p gTiTqYsT:l "
    "gTiYnPsG:j gTiYnYsG:d gTmGnPsP:r gTmGnYsP:x gTmPnPsO:i gTmPnYsP:r gTmPnYsY:r gTmTnYsP:o "
    "gTmYnPsP:o gTmYnYsP:r gTnBsGxP:w gTnGrBsG:o gTnGrGsG:m gTnGrGsP:o gTnGrGsY:m gTnGrPsG:q "
    "gTnGrPsP:x gTnGrPsY:q gTnGrTsG:o gTnGrTsP:o gTnGrTsY:t gTnGrYsP:w gTnPrGsY:i gTnPrPsY:m "
    "gTnPrTsY:o gTnPrYsY:m gTnTsGxG:w gTnTsGxP:r gTnTsGxT:o gTnTsPwG:q gTnTsPwP:r gTnTsPwT:p "
    "gTnTsPwY:r gTnTsYxP:r gYhGlGmP:b gYhGlYmP:q gYhPlPmG:b gYhPlPmY:b gYhPlYmG:b gYhPlYmP:n "
    "gYhPlYmT:b gYhYlGmP:i gYhYlPmG:f gYhYlPmP:r gYhYlTmP:b aGcYgPhYmG:b aPbGfGgPmT:j aPbPgYhGlT:f "
    "aPcGgGhGmT:b aPfGgGhBkP:q aPfGgGhTkG:l aPfGgGhTkT:l aPfGgYhTkP:l aPfPgGhBkG:l aPfPgGhBkT:s "
    "aPfPgYhTkG:b aPfPgYhTkT:b aPfYgYhTkP:l bGcPfTgPmT:i bGcPgPhYmG:l bGfPgGhTlT:c bGfPgPkGmT:x "
    "bGgGhPiGlT:n bGgGhPiTlG:f bGgGhPiYnT:c bGgPhPlGmG:i bGgPhPlGmY:c bGgPhPlYmG:c bGgPhPlYmY:c "
    "bGgYhGlGmP:c bGgYhPiGlG:m bGgYhPiYlG:d bGgYhPlPmG:f bGgYhPlPmY:f bPcGfGgPmT:t bPcGgYhPlG:m "
    "bPcPgGhGmB:i bPcPgYhYmT:f bPfPgGhTlT:s bPfYgYhGlP:k bPgGhGlTmP:s bPgGhPiGlT:n bPgGhPiTlG:m "
    "bPgGhYiGlB:c bPgGhYiGlT:m bPgGhYiPmT:c bPgGhYiTlP:r bPgTiTqTsT:n bPgYhGlGmP:f bPgYhYlTmP:c "
    "bTgGhGlTmP:c bTgPjBkTmT:x bTgPjGkTmT:c bTgPjPkTmT:i bTgPjTkTmT:x bTgPkGmTpP:q bTgPkPmTqG:l "
    "bTgPkPmTqT:d bTgTiTqTsT:a bYcPgYhPlG:d bYgPhPlGmG:c bYgPhPlYmG:d cGdPgTiPsB:e cGfGgPhYmG:a "
    "cGfYgPhYmG:k cGgGhYiPmG:b cGgPhGlGmG:i cGgPhGlYmG:f cGgPhYlYmP:i cGgThGiPsT:b cPdGgYhPlT:b "
    "cPfTgGhTmB:k cPfTgGhTmT:q cPgGhGiGmT:l cPgGhGiPmT:d cPgGhGiTmT:l cPgGhYiPmG:d cPgPhGlGmG:b "
    "cPgThGiPsT:n cTgGhGlPmT:b cTgThGiPsT:l dGgBiPjPsT:n dGgGhPiPmG:n dGgGhPiPmY:n dGgGhPiYnG:m "
    "dGgGhPiYnY:m dGgThGiPsB:c dGgThPiPsT:m dGgThTiGsB:c dGgThTiPsB:e dGgTiGjPsT:e dGgTiYjPsT:n "
    "dPePgBiYsT:j dPgBiPjYsT:e dPgGhPiYnG:c dPgThGiGsB:c dPgThTiGsB:e dPgTiGjGsT:e dPgTiGjPsT:h "
    "dPgTiGjTsT:l dPgTiYjGsT:h dPgTiYjPsT:h dTgTiGnGsT:j dTgTiGnPsT:j dTgTiGnTsT:e dTgTiPqPsB:m "
    "dYePgTiPsB:j dYgGhPiPmG:c dYgGhPiYnG:b dYgThPiPsT:n fGgGhTkPlG:b fGgGhTkPlP:q fGgGhTkPlT:b "
    "fGgPhYlPmY:k fGgYhGlPqG:m fGgYhGlPqY:p fPgGhBkPlG:q fPgGhBkPlY:q fPgGhTlGmB:p fPgGhTlGmP:s "
    "fPgGhTlGmT:k fPgGhTlPrG:q fPgGhTlPrT:k fPgGhTlYqG:m fPgGhTlYqP:k fPgThTiPsT:n fPgYhGkGlP:m "
    "fPgYhTkPlG:b fPgYhTkPlY:m fTgGhTkPmP:q fTgThTiPsT:k gBiGjGnPsG:d gBiGjGnTsT:o gBiGjPnGsT:o "
    "gBiGjPnPsG:r gBiGjPnTsT:d gBiGnGoPsG:t gBiGnGsPwT:o gBiPjGnGsT:o gBiPjGnPsG:m gBiPjGnTsT:d "
    "gBiPjTqPsT:m gBiPjYnPsG:h gBiPnGoGsG:t gBiPnGoPsG:j gBiPnYoPsG:j gBiTnPqPsG:r gBiTpPqGsT:r "
    "gBiTpPqYsT:u gBiTqPsTwG:p gBiTqPsTwT:p gBiYjPnPsG:o gBiYjYnPsG:d gBmGnPrGsP:t gBmGnPrYsP:o "
    "gBnGoTrPsG:i gBnGrGsPwP:o gBnGrPsPwY:m gBnGsPwGxG:q gBnGsPwGxP:o gBnGsPwGxT:q gBnGsYtPxY:q "
    "gBnPsYtPxG:o gBnToPsGxT:q gBnTqGsGxP:p gBnTqPsGxP:r gBnTqTsGxP:i gBnTsGwPxG:q gBnYoGrPsP:w "
    "gBnYoPsPtG:r gBnYoYsPtP:x gBrGsYtGwP:x gBrPsYtGxP:w gBrPsYtTwP:q gBrYsYtGwP:q gBsYtPxPyG:n "
    "gGhGiGlGmP:q gGhGiPlGmP:n gGhGiYlGmP:j gGhGlPmGrG:q gGhGlPmGrP:q gGhGlPmGrY:w gGhGlPmPrG:q "
    "gGhGlPmPrY:q gGhPiGlGnG:f gGhPiGlGnP:b gGhPiGlGnT:c gGhPiGlGnY:s gGhPiGlPmG:d gGhPiGlPmY:n "
    "gGhPiGlYmG:q gGhPiGlYmP:n gGhPiTkGlY:b gGhPiTkPlY:q gGhPiTlPmG:q gGhPiTlPmY:q gGhPiTlTsT:b "
    "gGhPiYmGnP:d gGhYiGlPrG:d gGhYiGlPrY:m gGhYiPmPnG:l gGhYiPmPnY:c gGhYiYmPnP:s gPhGiPmYrT:k "
    "gPhGkGlPmG:q gPhGkGmYrG:s gPhGkYlPmG:f gPhGlGmPnG:s gPhGlGmPnT:q gPhGlGmYrP:n gPhGlTmGnG:i "
    "gPhGlTmGnP:s gPhGlTmGnT:s gPhGlYmPqG:r gPhTlGmGrG:q gPhTlGmGrP:s gPhTlGmYsP:r gPhTlYmGrP:k "
    "gPhTlYmYrP:v gPhTmGqPrT:k gPhYiGlGmP:n gThGiPnPsG:o gThYiPnPsG:m gThYiPnPsT:j gTiBkTqGsT:p "
    "gTiBpGqPsT:r gTiBpPqPsT:v gTiBpPqYsT:v gTiBpYqPsT:v gTiGnPrGsG:x gTiGnPrGsY:t gTiGnPrPsG:m "
    "gTiGnPrTsG:o gTiGnPrYsG:l gTiGnYoPsG:l gTiPmGnYsG:h gTiPmPnYsG:j gTiTkTqGsB:p gTiTlGqPsB:p "
    "gTiTlGqPsT:k gTiTlGqYsT:p gTiTlPqPsT:p gTiTlPqYsT:p gTiTlTqPsB:u gTiTlTqPsT:c gTiTlYqPsT:v "
    "gTiTnPrGsG:t gTiTnPrGsY:t gTiTnPrPsG:q gTiTnPrTsG:t gTiTnPrYsG:q gTiTpGqGsT:v gTiTpPqGsT:r "
    "gTiTpPqYsB:k gTiTpTqGsT:r gTiYjGnPsG:h gTiYjPnPsG:h gTmGnPrGsP:t gTmGnPrPsY:t gTmGnPrYsP:w "
    "gTmGnYsPxG:t gTmGnYsPxT:i gTmPnGrGsG:i gTmPnGrGsY:t gTmPnPrYsY:i gTmPnYrGsP:i gTmPnYrPsY:q "
    "gTmPnYrYsP:o gTmYnPoGsP:r gTmYnYrPsP:l gTnBsGwPxP:r gTnGoGrGsP:t gTnGoGrTsP:t gTnGoPrBsG:t "
    "gTnGoPrGsP:t gTnGoPrTsG:i gTnGoPrTsP:i gTnGoTrGsP:m gTnGoTrTsG:h gTnGqGrPsG:t gTnGqGrPsY:x "
    "gTnGqPrPsG:l gTnGqTrPsG:x gTnGqTrPsY:t gTnGqYrPsG:m gTnGrPsPxG:q gTnGrTsYtP:x gTnGrYsPwG:m "
    "gTnToPsGxT:w gTnTpPsPwT:k gTnTpTsPwT:d gTnTqGsPwG:r gTnTqPsPwG:l gTnTqTsPwG:x gTnTrGsGxP:w "
    "gTnTrGsPwP:q gTnTrGsYxP:t gTnTrPsGxP:q gTnTrTsGxP:e gTnTrYsGxP:w gTnTrYsPwP:x gTnTrYsPwY:q "
    "gTnTsGwPxG:r gYhPlYmPnG:i gYhPlYmPnY:s gYhYlPmPrG:q gYhYlPmPrY:s aGbPcYgPhYmG:f aPbGcPgYhGlT:i "
    "aPbGfGgPjBmT:p aPbGfGgPjTmT:d aPbGfPgYhTkG:l aPbPcGgGhGmT:i aPbPfGgGhTkB:s aPbPfGgYhGlT:m "
    "aPbTgTiTqTsT:j aPfGgGhBkPqG:p aPfGgGhBkPqT:s aPfGgGhTkGlP:q aPfGgGhTkTlP:r aPfGgYhTkPlG:q "
    "aPfPgGhBkGlG:q aPfPgGhBkTsG:x aPfPgGhBkTsT:j aPfTgGhTkBmP:s aPfTgGhTkTmP:l aTcGgGhGkPmT:i "
    "bGcGgPhPlGmY:n bGcGgPhPlYmG:k bGcGgPhPlYmY:k bGcPdPgGhGmB:i bGcPfPgGhTlT:i bGcPfTgPiGmT:d "
    "bGcPfTgPiTmT:p bGcPgGhPiYnT:d bGcPgPhGlGmG:k bGcPgPhYlTmG:i bGcPgYhGlGmP:f bGfPgGhPiTlG:s "
    "bGfPgPkGmTxB:j bGfPgPkGmTxT:t bGfPgYhTkPlG:c bGgGhPiGlTnG:c bGgGhPiGlTnT:c bGgGhPiTkGlY:f "
    "bGgPhPiGlGmG:d bGgPhPiTlGmG:x bPcGdPgGhGmB:a bPcGfGgPmTtB:v bPcGfGgPmTtT:x bPcGgGhYiPmG:f "
    "bPcGgThGiPsT:t bPcGgYhPlGmT:f bPcPfGgYhYmT:l bPcPgGhGiGmB:d bPcPgGhGiTmB:v bPcPgGhYiGlB:s "
    "bPcTgGhGlPmT:v bPfGgGhTkPlG:q bPfGgGhTkPlT:q bPfGgYhGlGmP:k bPfPgGhTlTsT:j bPgGhGiTlGmP:q "
    "bPgGhGlTmPsG:i bPgGhPiGlTnG:d bPgGhPiTlGmG:r bPgGhYiGlTmP:n bTcPgGhGlTmP:i bTgGhPiTkPlG:s "
    "bTgPiGjPkTmT:d bTgPiTjPkTmT:x bTgPjTkTmTxP:t bTgPjTkTmTxT:v bTgPkGmTpPqG:u bTgPkGmTpPqT:d "
    "bTgPkPlGmTqG:p bTgYhGkPlGmP:i cGdPeGgTiPsB:q cGdPgGhPiYnG:m cGgGhPiGlGnT:d cGgPhGiPlGmG:f "
    "cGgPhGiTlGmG:d cPdGgGhGiPmT:b cPdGgGhYiPmG:l cPfTgGhTkPmB:v cPfTgGhTmTqG:k cPfTgGhTmTqP:k "
    "cPfTgGhTmTqT:s cPgGhGiGlPmT:d cPgGhGiGlTmT:b cPgGhGiTlPmT:p cPgThGiPnGsT:d cPgThGiPnTsT:w "
    "cTgGhGlTmTnP:a cTgPhGlGmGnP:f cTgThGiPlPsT:r cTgThGiPlTsT:n cTgTiTlTqPsT:b dGePgTiGjPsT:n "
    "dGePgTiGjTsT:h dGePgTiYjGsT:h dGeTgTiGjPsT:h dGgGhPiGlPmG:n dGgGhPiPmGnG:b dGgGhPiYmGnP:c "
    "dGgThPiPmGsT:n dGgTiYjPnGsT:e dGgTiYjPnPsT:h dPePgTiGjGsT:h dPeTgTiGjGsT:n dPgBiGjGnPsG:t "
    "dPgThGiYjGsT:e dPgThGiYjPsT:o dPgThPiYjGsT:n dPgThTiGjPsT:k dPgThYiPnGsT:c dPgTiGjTlGsT:q "
    "dPgTiGjTlTsT:c dTePgTiGnTsT:q dTgTiGjPnGsT:q dTgTiGjPnPsT:r eBgTnTrTsGxP:p eTgTnTrTsGxP:y "
    "fBgGhPiGlGnG:m fGgGhTkPlPqG:s fGgGhTkPlPqY:p fGgPhYkGlPmY:c fPgGhBkPlGqG:p fPgGhBkPlGqT:s "
    "fPgGhBkPlYqG:s fPgGhPiGlGnG:d fPgGhTkGlGmT:a fPgGhTkGlPrT:o fPgGhTkPlGmT:n fPgGhTlGmBpP:b "
    "fPgGhTlGmPsG:i fPgGhTlPqGrG:p fPgGhTlYmPqG:r fPgThTiPnGsT:o fPgThTiPnTsT:w fPgYhGkGlPmT:b "
    "fTgGhPiGlGnG:k fTgGhTkPmPqG:s fTgGhTkPmPqY:l fTgThTiPkPsT:p gBiPnGoGsGtP:x gBiPnGoTrPsG:w "
    "gBiTnGoTrPsG:t gBmGnPoGrYsP:t gBnGoGrGsPwP:x gBnGoGsPwGxP:t gBnGsYtPxPyG:r gBnPoGsYtPxG:r "
    "gBnTqGsGwPxG:t gBnTsGwTxGyP:t gBnYoGrPsPwG:x gBqGrPsYtTwP:x gBrPsYtGwGxP:n gBrPsYtGxGyP:n "
    "gGhGiGlGmPqG:n gGhGiPlGmPnG:k gGhGiPlPmGrT:k gGhGlPmGqGrG:i gGhGlPmGqGrP:f gGhGlPmGqPrG:f "
    "gGhGlPmGqTrG:s gGhGlPmPqYrY:p gGhYiPlTmPnG:c gPhGiPlTmGnG:j gPhGkGlPmGqG:p gPhGkGlPmGqT:t "
    "gPhGlTmGnPsG:t gPhGlTmGnTsP:b gPhGlYmPqGrT:k gPhTkGlYmGrP:v gPhTkGmGqPrT:j gPhTkYmGqPrT:a "
    "gPhTlGmGqPrG:v gPhTlGmGrPsG:x gPhTlTmGrGsP:w gPhTmGqBrTsP:o gPhTmGqTrTsP:k gPhYiGlGmPnT:c "
    "gThGiYjGnPsG:e gThPiYjGnPsG:m gThPnGoTrTsG:t gTiBpPqPsTvG:k gTiGmGnPrPsG:j gTiGmPnGrGsG:q "
    "gTiGnGoPrTsG:j gTiGnPoGrTsG:t gTiGnPrGsGxP:j gTiGnPrGsGxT:h gTiTkGlGqPsT:f gTiTkPlGqPsT:w "
    "gTiTkTlGqPsT:r gTiTlPpGqPsT:r gTiTlYqPsTvG:p gTiTnPrGsGtG:y gTiTpGqGsTvP:x gTiTpPqGrBsT:y "
    "gTiTpPqGrTsT:v gTiTpTqGrPsT:v gTmGnPrGsPtG:j gTmGnPrPsYtG:x gTmPnGrYsPwG:q gTmPnToBsGxT:q "
    "gTmYnPoGrYsP:h gTnBrGsGwPxP:q gTnBrYsGwPxP:v gTnBsGwPxGyP:b gTnBsGwTxPyP:d gTnGoGrGsPtP:m "
    "gTnGoGrGsPtT:i gTnGoGrTsGtP:i gTnGoGrTsPtP:b gTnGoGrTsPtT:i gTnGoPrBsGtP:i gTnGoPrGsPtG:w "
    "gTnGqGrPsGtP:v gTnGqGrPsGtT:l gTnGqGrPsPxG:v gTnGqTrPsGxG:y gTnToPsGwPxT:b gTnTqGrGsPwG:v "
    "gTnTqGrPsGxP:v gTnTqTsPwGxP:r gTnTrGsGwGxP:q gTnTrGsGwPxG:t gTnTrGsGwPxP:h gTnTrGsGwTxP:l "
    "gTnTrPsGwPxG:q gTnTrTsGwPxG:t gTnTrYsPwPxG:v gTnTsGwTxGyP:r gYhPiGlYmPnG:b gYhYlPmPqGrG:f "
    "aGbPcGfPgGhGmT:i aGbPcYfGgPhYmG:i aPbGcTfPgGhTlT:i aPbGfTgGhPiTlG:p aPbPfGgGhTkBsG:x "
    "aPbPfGgGhTkBsT:e aPbPfGgGhTkTlT:q aPbTcTgGhGlTmP:i aPbTfGgGhTkPlT:d aPbTgTiTjTqTsT:d "
    "aPcPfTgGhTkBmB:e aPfGgGhBkPpGqG:v aPfGgGhBkPpTqG:r aPfGgGhTkTlPrG:v aPfGgGhTkTlPrT:e "
    "aPfTgGhTkBmPsG:u aPfTgGhTkBmPsY:x aPfTgGhTkTlGmP:q aPfTgThTiPkBsT:e aTbTfPgTiTqTsT:d "
    "bGcPdGfTgPiGmT:e bGcPdGgGhGiPmT:f bGcPdPgGhGiGmB:f bGcPfPgGhTiGlT:e bGcPfPgGhTiTlT:s "
    "bGfPgGhPiTkGlY:q bPcGgPhGiBlGmG:k bPcGgThGiPsTtT:x bPcPdGgGhGiGmB:j bPcPgGhGiTlTmT:r "
    "bPcTgGhGlPmTvB:e bPcTgGhGlPmTvT:p bPfGgGhTkPlGqG:r bPfGgGhTkPlTqG:u bPfGgGhTkPlTqT:s "
    "bTcPgGhGiGlTmP:s bTcPgGhGiYlTmP:e bTcTdPgGhGlPmT:f bTgPkPlGmTpGqG:u bTgTnBsGwPxGyP:a "
    "bTgTnGoGrTsPtP:a bTgTnToPsGwPxT:a cGdPgPhGiTlGmG:k cPdGgGhGiGlPmT:j cPfTgGhTkPmBvB:e "
    "cPfTgGhTkPmBvT:p cTgThGiPlPrGsT:q dGePgThPiGjTsT:q dGePgTiGjPnTsT:w dGeTgThPiGjPsT:t "
    "dPePgThTiGjGsT:k dPeTgTiGjGnPsT:b dTePgBiGjGnPsG:t dTePgTiGjGnPsT:q fGgGhTkPlPpGqY:r "
    "fGgGhTkPlPpYqY:v fPgGhBkPlGpGqG:v fPgGhTkTlGmTrP:a fPgTiTkGlGqPsT:d fTgGhPiGkPlGnG:d "
    "fTgGhTkPlGmPqY:u fTgGhTkPlYmPqY:r fTgThTiPkPpGsT:q gPhGkGlPmGpGqG:v gPhGlTmGnPsGtG:x "
    "gPhTlGmGrPsGxG:t gPhTlTmGrGsPwG:x gThGiGnPrGsGxT:d gThPmGnGoTrGsP:x gTiPnGoGrGsPtT:w "
    "gTiPnGoGrTsPtT:e gTiTpGqGsTuPvT:k gTiTpGqGsTvPxT:t gTiTpPqGrTsTvG:u gTlGnGqGrPsGtT:p "
    "gTmTnGoGrGsPtP:x gTnGoPrBsGtGyP:j gTnToPsGwBxTyP:e gTnTqYrPsGwPxG:v gTnTrGsGtPwPxG:v "
    "gTnTrPsGwTxGyP:u gTnTrTsGtPwPxG:u gTnTsGtPwBxGyP:e aPcPeBfTgGhTkBmB:t cPdGePgThTiGjTsT:q "
    "cPdGeTgThTiGjPsT:q dPeTgTiGjGnToPsT:p gTiTjPnGoGrGsPtT:w gTnTrTsGtTwPxGyP:i "
)
_quest_policy_table: Optional[Dict[str, str]] = None
# _QUEST_OUTCOMES[cell][outcome] = bitset over _QUEST_ALL_LAYOUTS (5 = purple).
_quest_outcomes: Optional[Tuple[Tuple[int, ...], ...]] = None


def _quest_outcome_bits() -> Tuple[Tuple[int, ...], ...]:
    global _quest_outcomes
    if _quest_outcomes is None:
        bits = [[0] * 6 for _ in range(BOARD_CELLS)]
        for index, layout in enumerate(_QUEST_ALL_LAYOUTS):
            bit = 1 << index
            for cell in range(BOARD_CELLS):
                outcome = 5 if layout >> cell & 1 else min(4, _bit_count(layout & _NEIGHBOR_MASKS[cell]))
                bits[cell][outcome] |= bit
        _quest_outcomes = tuple(tuple(row) for row in bits)
    return _quest_outcomes


class _QuestSolver:
    """Exact best expected spheres for a small set of purple layouts.

    Clicks whose outcome is already certain only add their spheres, so they
    are saved for the end ("cash"); the search branches on informative clicks.
    """

    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.memo: Dict[tuple, Tuple[float, Optional[int]]] = {}

    def cash(self, layouts: int, hidden, clicks: int, red: bool) -> float:
        flats = [_QUEST_RED_VALUE] if red else []
        for cell in hidden:
            for outcome in range(5):
                if layouts & self.outcomes[cell][outcome] == layouts:
                    flats.append(_QUEST_CLUE_VALUES[outcome])
                    break
        flats.sort(reverse=True)
        return sum(flats[:clicks])

    def settle(self, layouts: int, hidden, found: int, clicks: int) -> float:
        """Click certain purples (free); after the 3rd the last one shows as red."""
        if clicks <= 0 or not layouts:
            return 0.0
        gain = 0.0
        hidden = list(hidden)
        while found < 3:
            certain = next((c for c in hidden if layouts & self.outcomes[c][5] == layouts), None)
            if certain is None:
                break
            hidden.remove(certain)
            gain += _QUEST_PURPLE_SPHERES
            found += 1
        if found >= 3:
            total = 0.0
            for red in hidden:
                part = layouts & self.outcomes[red][5]
                if part:
                    rest = [cell for cell in hidden if cell != red]
                    total += _bit_count(part) * self.cash(part, rest, clicks, True)
            return gain + total / _bit_count(layouts)
        return gain + self.best(layouts, tuple(hidden), found, clicks)[0]

    def best(self, layouts: int, hidden, found: int, clicks: int) -> Tuple[float, Optional[int]]:
        if clicks <= 0 or not layouts:
            return 0.0, None
        key = (layouts, clicks)
        cached = self.memo.get(key)
        if cached is not None:
            return cached
        n = _bit_count(layouts)
        best, best_cell = self.cash(layouts, hidden, clicks, False), None
        for cell in hidden:
            parts = [(o, layouts & self.outcomes[cell][o]) for o in range(6)]
            parts = [(o, part) for o, part in parts if part]
            if len(parts) < 2:
                continue
            rest = tuple(other for other in hidden if other != cell)
            value = 0.0
            for outcome, part in parts:
                if outcome == 5:
                    value += _bit_count(part) * (_QUEST_PURPLE_SPHERES + self.settle(part, rest, found + 1, clicks))
                else:
                    value += _bit_count(part) * (
                        _QUEST_CLUE_VALUES[outcome] + self.settle(part, rest, found, clicks - 1)
                    )
            value /= n
            if value > best + 1e-9:
                best, best_cell = value, cell
        self.memo[key] = (best, best_cell)
        return best, best_cell


def parse_sphere_click_limit(text, default: int) -> int:
    """Read "You can click **N** times" from a sphere board message."""
    match = re.search(r"click\s+(\d+)\s+times?", str(text or "").replace("**", ""), re.IGNORECASE)
    return max(1, int(match.group(1))) if match else default


def choose_quest_position(
    emojis: Sequence[str],
    disabled: Sequence[bool],
    clicks: int = _QUEST_CLICKS,
) -> Optional[int]:
    """Pick the next $oq button: red, certain purples, then the offline policy or exact search."""
    board = [normalize_sphere_emoji(value) for value in emojis]
    blocked = [bool(value) for value in disabled]
    if len(board) != BOARD_CELLS or len(blocked) != BOARD_CELLS:
        return None
    # The red (4th purple) shows up after 3 purples; it costs a click and is
    # worth the most, so take it as soon as it appears.
    for index, name in enumerate(board):
        if name in {RED_SPHERE, "spR"} and not blocked[index]:
            return index
    candidates = _sphere_game_candidates(board, blocked)
    if not candidates:
        return None
    hidden = [index for index in candidates if board[index] == UNKNOWN_SPHERE]
    outcomes = _quest_outcome_bits()
    layouts = (1 << len(_QUEST_ALL_LAYOUTS)) - 1
    for index, name in enumerate(board):
        if name in _QUEST_CLUES and blocked[index]:
            layouts &= outcomes[index][_QUEST_CLUES[name]]
        elif name in {"spP", RED_SPHERE, "spR"}:
            layouts &= outcomes[index][5]
    if not hidden or not layouts:
        return min(candidates, key=lambda index: (_center_distance(index), index))
    for index in hidden:
        if layouts & outcomes[index][5] == layouts:
            return index  # certainly purple: free

    global _quest_policy_table
    if clicks == _QUEST_CLICKS:
        table = _quest_policy_table
        if table is None:
            table = {}
            for entry in _QUEST_POLICY.split():
                state, move = entry.split(":")
                table[state] = move
            _quest_policy_table = table
        key = "".join(
            chr(97 + index) + _QUEST_CODES[name]
            for index, name in enumerate(board) if blocked[index] and name in _QUEST_CODES
        )
        move = table.get(key)
        if move is not None and ord(move) - 97 in hidden:
            return ord(move) - 97

    count = _bit_count(layouts)
    if count <= _QUEST_EXACT_LAYOUTS:
        found = sum(1 for name in board if name == "spP")
        used = sum(
            1 for index in range(BOARD_CELLS)
            if blocked[index] and (board[index] in _QUEST_CLUES or board[index] in {RED_SPHERE, "spR"})
        )
        _, cell = _QuestSolver(outcomes).best(layouts, tuple(hidden), found, max(0, clicks - used))
        if cell is not None:
            return cell
        # Nothing left to learn: take the best certain clue.
        return max(hidden, key=lambda index: (
            max((_QUEST_CLUE_VALUES[o] for o in range(5) if layouts & outcomes[index][o] == layouts), default=0.0),
            -index,
        ))

    def score(position: int):
        purple = _bit_count(layouts & outcomes[position][5]) / count
        clue = sum(
            _bit_count(layouts & outcomes[position][o]) * _QUEST_CLUE_VALUES[o] for o in range(5)
        ) / count
        return purple * _QUEST_PURPLE_VALUE + clue, -_center_distance(position), -position

    return max(hidden, key=score)


# $ot: each color sits on one straight run in a row or column; only blue
# costs a click. Lengths come from the board text, these are the defaults.
_TRACE_BASE_COLORS = {"spT": "teal", "spG": "green", "spY": "yellow"}


@dataclass(frozen=True)
class TraceRules:
    lengths: Dict[str, int] = field(default_factory=lambda: {"spT": 4, "spG": 3, "spY": 3})
    rare_length: int = 2
    rare_colors: int = 2
    blue_clicks: int = 4


def parse_trace_rules(text: str) -> TraceRules:
    """Read run lengths and the rare color count from an $ot board message."""
    normalized = str(text or "").replace("**", "")
    defaults = TraceRules()
    lengths = dict(defaults.lengths)
    for emoji, color in _TRACE_BASE_COLORS.items():
        match = re.search(r"\b" + color + r"\s*=\s*(\d+)", normalized, re.IGNORECASE)
        if match:
            lengths[emoji] = max(1, min(BOARD_SIZE, int(match.group(1))))
    rare_length = defaults.rare_length
    match = re.search(r"rarer\s+spheres?\s*=\s*(\d+)", normalized, re.IGNORECASE)
    if match:
        rare_length = max(1, min(BOARD_SIZE, int(match.group(1))))
    rare_colors = defaults.rare_colors
    match = re.search(r"different\s+colou?rs?\s*:\s*(\d+)", normalized, re.IGNORECASE)
    if match:
        # Blue and the three named colors are always present.
        rare_colors = max(0, int(match.group(1)) - 1 - len(lengths))
    return TraceRules(
        lengths=lengths, rare_length=rare_length, rare_colors=rare_colors,
        blue_clicks=parse_sphere_click_limit(normalized, defaults.blue_clicks),
    )


def _straight_runs(length: int) -> Tuple[Tuple[int, ...], ...]:
    runs = []
    for row in range(BOARD_SIZE):
        for start in range(BOARD_SIZE - length + 1):
            runs.append(tuple(row * BOARD_SIZE + start + offset for offset in range(length)))
    if length > 1:
        for column in range(BOARD_SIZE):
            for start in range(BOARD_SIZE - length + 1):
                runs.append(tuple((start + offset) * BOARD_SIZE + column for offset in range(length)))
    return tuple(runs)


_TRACE_VALUES = {
    "spB": 10.0, "spT": 20.0, "spG": 35.0, "spY": 55.0, "spO": 90.0,
    "spL": 76.0, "spD": 104.0, "spR": 150.0, "spW": 500.0,
}
_TRACE_RARES = ("spL", "spD", "spR", "spW")
# How often each rare colour fills the extra ships, by number of extra ships
# (community data from 1,177 real boards); values unknown rare cells.
_TRACE_RARE_WEIGHTS = {
    1: {"spL": 0.6697, "spD": 0.3303},
    2: {"spL": 0.8182, "spD": 0.6071, "spR": 0.4156, "spW": 0.1591},
    3: {"spL": 0.9063, "spD": 0.8750, "spR": 0.7500, "spW": 0.4688},
}
# Extra Chance: until this many ship cells are hit, a blue never ends the board.
_TRACE_EXTRA_CHANCE_SHIPS = 5
_TRACE_ENDGAME_BOARDS = 400        # exact endgame search up to this many boards
# Boards counted live; every state the policy meets with more is in the table.
_TRACE_COUNT_LIMIT = 300000
_TRACE_COUNT_SECONDS = 2.0
# Offline decisions for the default rules ("extra ships:<revealed cells>:<cell>")
# in every state the policy meets with more than ~300k consistent boards.
_TRACE_POLICY = (
    "1::a 1:aB:b 1:aBbB:c 2::a 2:aB:b 2:aD:y 2:aG:e 2:aL:y 2:aO:y 2:aR:y 2:aT:e 2:aW:y 2:aY:e "
    "2:aBbB:c 2:aBbD:d 2:aBbL:d 2:aBbR:d 2:aBbT:f 2:aBbW:d 2:aDyB:t 2:aLyB:t 2:aRyB:t 2:aTeB:u "
    "2:aWyB:t 2:aBbBcB:d 2:aTeBuB:j 3::a 3:aB:b 3:aD:y 3:aG:y 3:aL:y 3:aO:y 3:aR:y 3:aT:e 3:aW:y "
    "3:aY:y 3:aBbB:c 3:aBbD:d 3:aBbG:e 3:aBbL:d 3:aBbO:d 3:aBbR:d 3:aBbT:f 3:aBbW:d 3:aBbY:e 3:aDyB:t "
    "3:aDyL:c 3:aDyR:c 3:aDyT:e 3:aDyW:c 3:aGyB:t 3:aLyB:t 3:aLyD:c 3:aLyR:c 3:aLyT:e 3:aLyW:c "
    "3:aOyB:t 3:aRyB:t 3:aRyD:c 3:aRyL:c 3:aRyT:e 3:aRyW:c 3:aTeB:u 3:aTeD:u 3:aTeL:u 3:aTeR:u "
    "3:aTeW:u 3:aWyB:t 3:aWyD:c 3:aWyL:c 3:aWyR:c 3:aWyT:e 3:aYyB:t 3:aBbBcB:d 3:aBbBcD:e 3:aBbBcL:e "
    "3:aBbBcR:e 3:aBbBcW:e 3:aBbDdB:e 3:aBbLdB:e 3:aBbRdB:e 3:aBbTfB:k 3:aBbWdB:e 3:aDtByB:o "
    "3:aLtByB:o 3:aRtByB:o 3:aTeBuB:j 3:aWtByB:o 4::a 4:aB:b 4:aD:y 4:aG:y 4:aL:y 4:aO:y 4:aR:y "
    "4:aT:e 4:aW:y 4:aY:y 4:aBbB:c 4:aBbD:f 4:aBbG:e 4:aBbL:f 4:aBbR:f 4:aBbT:f 4:aBbW:f 4:aBbY:e "
    "4:aDyB:t 4:aDyG:j 4:aDyL:c 4:aDyR:c 4:aDyT:e 4:aDyW:c 4:aDyY:j 4:aGyB:t 4:aGyD:d 4:aGyL:d "
    "4:aGyR:d 4:aGyW:d 4:aLyB:t 4:aLyD:c 4:aLyG:j 4:aLyR:c 4:aLyT:e 4:aLyW:c 4:aLyY:j 4:aRyB:t "
    "4:aRyD:c 4:aRyG:j 4:aRyL:c 4:aRyT:e 4:aRyW:c 4:aRyY:j 4:aTeB:u 4:aTeD:u 4:aTeL:u 4:aTeR:u "
    "4:aTeW:u 4:aWyB:t 4:aWyD:c 4:aWyG:j 4:aWyL:c 4:aWyR:c 4:aWyT:e 4:aWyY:j 4:aYyB:t 4:aYyD:d "
    "4:aYyL:d 4:aYyR:d 4:aYyW:d 4:aBbBcD:e 4:aBbBcL:e 4:aBbBcR:e 4:aBbBcW:e 4:aBbDfB:y 4:aBbLfB:y "
    "4:aBbRfB:y 4:aBbWfB:y "
)
_trace_policy_table: Optional[Dict[str, int]] = None


class _TraceBudget(Exception):
    pass


def _straight_masks(length: int) -> Tuple[int, ...]:
    return tuple(sum(1 << cell for cell in run) for run in _straight_runs(length))


def _trace_rare_value(extra_ships: int) -> float:
    weights = _TRACE_RARE_WEIGHTS.get(extra_ships) or {name: 1.0 for name in _TRACE_RARES}
    return sum(_TRACE_VALUES[name] * w for name, w in weights.items()) / sum(weights.values())


class _TraceShips:
    """Every ship placement still consistent with the revealed $ot cells.

    Ships never overlap; orange and the extra rare ships have the rare length.
    Rare ships whose colour is not revealed yet are interchangeable ("rare").
    """

    def __init__(self, board: Sequence[str], rules: TraceRules):
        extra_ships = max(0, rules.rare_colors - 1)
        blue = 0
        cells: Dict[str, int] = {}
        for index, name in enumerate(board):
            if name == "spB":
                blue |= 1 << index
            elif name != UNKNOWN_SPHERE:
                cells[name] = cells.get(name, 0) | (1 << index)
        revealed = 0
        for mask in cells.values():
            revealed |= mask
        known_rares = [name for name in _TRACE_RARES if name in cells]
        named = list(rules.lengths.items()) + [("spO", rules.rare_length)]
        named += [(name, rules.rare_length) for name in known_rares]
        self.generic = extra_ships - len(known_rares)
        self.valid = self.generic >= 0 and not set(cells) - {name for name, _ in named}
        self.ships = []
        for name, length in named:
            need = cells.get(name, 0)
            forbid = blue | (revealed & ~need)
            self.ships.append((name, [m for m in _straight_masks(length) if not m & forbid and m & need == need]))
        self.ships.sort(key=lambda ship: len(ship[1]))
        self.generic_masks = [m for m in _straight_masks(rules.rare_length) if not m & (blue | revealed)]

    def _generic(self, occupied: int, left: int, start: int):
        if left == 0:
            yield 0
            return
        masks = self.generic_masks
        for index in range(start, len(masks)):
            if not masks[index] & occupied:
                for rest in self._generic(occupied | masks[index], left - 1, index + 1):
                    yield masks[index] | rest

    def _walk(self, visit, deadline: float):
        chosen = [0] * len(self.ships)
        steps = [0]

        def walk(index, occupied):
            if index == len(self.ships):
                visit(chosen, occupied)
                return
            steps[0] += 1
            if not steps[0] & 4095 and time.monotonic() > deadline:
                raise _TraceBudget
            for mask in self.ships[index][1]:
                if not mask & occupied:
                    chosen[index] = mask
                    walk(index + 1, occupied | mask)

        if self.valid:
            walk(0, 0)

    def count(self, limit: int, deadline: float) -> Tuple[int, Dict[str, List[int]]]:
        """(boards, per-colour ship counts per cell); raises _TraceBudget when too big."""
        per_mask: Dict[str, Dict[int, int]] = {name: {} for name, _ in self.ships}
        per_mask["rare"] = {}
        total = [0]

        def visit(chosen, occupied):
            ways = 0
            rare = per_mask["rare"]
            for union in self._generic(occupied, self.generic, 0):
                ways += 1
                if union:
                    rare[union] = rare.get(union, 0) + 1
            if not ways:
                return
            total[0] += ways
            if total[0] > limit:
                raise _TraceBudget
            for slot, (name, _) in enumerate(self.ships):
                bucket = per_mask[name]
                bucket[chosen[slot]] = bucket.get(chosen[slot], 0) + ways

        self._walk(visit, deadline)
        colours: Dict[str, List[int]] = {}
        for name, bucket in per_mask.items():
            counts = [0] * BOARD_CELLS
            for mask, ways in bucket.items():
                while mask:
                    low = mask & -mask
                    counts[low.bit_length() - 1] += ways
                    mask ^= low
            if any(counts):
                colours[name] = counts
        return total[0], colours

    def boards(self, limit: int) -> List[Tuple[str, ...]]:
        out: List[Tuple[str, ...]] = []

        def visit(chosen, occupied):
            for union in self._generic(occupied, self.generic, 0):
                board = ["spB"] * BOARD_CELLS
                for slot, (name, _) in enumerate(self.ships):
                    for cell in range(BOARD_CELLS):
                        if chosen[slot] >> cell & 1:
                            board[cell] = name
                for cell in range(BOARD_CELLS):
                    if union >> cell & 1:
                        board[cell] = "rare"
                out.append(tuple(board))
                if len(out) > limit:
                    raise _TraceBudget

        self._walk(visit, time.monotonic() + _TRACE_COUNT_SECONDS)
        return out


def _trace_endgame(boards, hidden, lives: int, value_of) -> Optional[int]:
    """Exact best click once Extra Chance is off: each blue costs one of `lives`."""
    memo: Dict[tuple, Tuple[float, Optional[int]]] = {}

    def solve(members, cells, lives):
        if not cells or not members:
            return 0.0, None
        key = (members, cells, lives)
        cached = memo.get(key)
        if cached is not None:
            return cached
        best, best_cell = -1.0, None
        for cell in cells:
            groups: Dict[str, list] = {}
            for member in members:
                groups.setdefault(boards[member][cell], []).append(member)
            rest = tuple(other for other in cells if other != cell)
            value = 0.0
            for label, group in groups.items():
                if label == "spB":
                    after = solve(tuple(group), rest, lives - 1)[0] if lives > 1 else 0.0
                    value += len(group) * (_TRACE_VALUES["spB"] + after)
                else:
                    value += len(group) * (value_of(label) + solve(tuple(group), rest, lives)[0])
            value /= len(members)
            if value > best:
                best, best_cell = value, cell
        memo[key] = (best, best_cell)
        return best, best_cell

    return solve(tuple(range(len(boards))), tuple(hidden), lives)[1]


def choose_trace_position(
    emojis: Sequence[str],
    disabled: Sequence[bool],
    rules: Optional[TraceRules] = None,
) -> Optional[int]:
    """Pick the next $ot button from every ship layout still possible.

    While fewer than 5 ship cells are hit, Extra Chance keeps blues from ending
    the board, so the safest cells are uncovered first and ships (always free)
    wait. After that every blue costs a click: certain ships go first, then the
    exact endgame search, or the most likely ship.
    """
    board = [normalize_sphere_emoji(value) for value in emojis]
    blocked = [bool(value) for value in disabled]
    if len(board) != BOARD_CELLS or len(blocked) != BOARD_CELLS:
        return None
    candidates = _sphere_game_candidates(board, blocked)
    if not candidates:
        return None
    rules = rules or TraceRules()
    hidden = [index for index in candidates if board[index] == UNKNOWN_SPHERE]
    if not hidden:
        return min(candidates, key=lambda index: (_center_distance(index), index))
    hits = sum(1 for i in range(BOARD_CELLS) if blocked[i] and board[i] not in {"spB", UNKNOWN_SPHERE})
    blues = sum(1 for i in range(BOARD_CELLS) if blocked[i] and board[i] == "spB")
    extra_ships = max(0, rules.rare_colors - 1)

    global _trace_policy_table
    if rules == TraceRules(rare_colors=rules.rare_colors):
        table = _trace_policy_table
        if table is None:
            table = {}
            for entry in _TRACE_POLICY.split():
                ships, state, move = entry.split(":")
                table[ships + ":" + state] = ord(move) - 97
            _trace_policy_table = table
        key = f"{extra_ships}:" + "".join(
            chr(97 + i) + board[i][2:] for i in range(BOARD_CELLS) if board[i] != UNKNOWN_SPHERE
        )
        move = table.get(key)
        if move is not None and move in hidden:
            return move

    ships = _TraceShips(board, rules)
    try:
        total, colours = ships.count(_TRACE_COUNT_LIMIT, time.monotonic() + _TRACE_COUNT_SECONDS)
    except _TraceBudget:
        total, colours = 0, {}
    if not total:
        return _choose_trace_by_coverage(board, hidden, rules, hits)
    ship_cells = [sum(counts[i] for counts in colours.values()) for i in range(BOARD_CELLS)]
    rare_value = _trace_rare_value(extra_ships)

    def value_of(label):
        return rare_value if label == "rare" else _TRACE_VALUES.get(label, rare_value)

    def ship_value(index):
        if not ship_cells[index]:
            return 0.0
        return sum(counts[index] * value_of(name) for name, counts in colours.items()) / ship_cells[index]

    if hits < _TRACE_EXTRA_CHANCE_SHIPS:
        return max(hidden, key=lambda i: (total - ship_cells[i], -_center_distance(i), -i))
    certain = [i for i in hidden if ship_cells[i] == total]
    if certain:
        return max(certain, key=lambda i: (ship_value(i), -i))
    if total <= _TRACE_ENDGAME_BOARDS:
        try:
            boards = ships.boards(_TRACE_ENDGAME_BOARDS)
        except _TraceBudget:
            boards = []
        if boards:
            lives = rules.blue_clicks - min(blues, rules.blue_clicks - 1)
            cell = _trace_endgame(boards, hidden, max(1, lives), value_of)
            if cell is not None:
                return cell
    return max(hidden, key=lambda i: (ship_cells[i], ship_value(i), -i))


def _choose_trace_by_coverage(board, hidden, rules: TraceRules, hits: int) -> int:
    """Rough fallback when the layouts are too many to count: per-colour run coverage."""
    hidden_set = set(hidden)
    coverage = [0.0] * BOARD_CELLS

    def add_runs(found, length, copies=1.0):
        if len(found) >= length or copies <= 0:
            return
        runs = [
            run for run in _straight_runs(length)
            if found.issubset(run) and all(cell in hidden_set or cell in found for cell in run)
        ]
        for run in runs:
            for cell in run:
                if cell in hidden_set:
                    coverage[cell] += copies / len(runs)

    for emoji, length in rules.lengths.items():
        add_runs({index for index, name in enumerate(board) if name == emoji}, length)
    rare_names = {
        name for name in board
        if name not in rules.lengths and name not in {UNKNOWN_SPHERE, "spB"}
    }
    for name in rare_names:
        add_runs({index for index, value in enumerate(board) if value == name}, rules.rare_length)
    add_runs(set(), rules.rare_length, copies=float(max(0, rules.rare_colors - len(rare_names))))

    if hits < _TRACE_EXTRA_CHANCE_SHIPS:
        return min(hidden, key=lambda index: (coverage[index], _center_distance(index), index))
    return max(hidden, key=lambda index: (coverage[index], -_center_distance(index), -index))
