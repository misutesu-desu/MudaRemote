"""Parsing and deterministic board choices for Mudae sphere mini-games."""

from dataclasses import dataclass, field
from itertools import combinations
import re
from typing import Dict, Iterable, Optional, Sequence, Tuple


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


def choose_chest_position(
    emojis: Sequence[str],
    disabled: Sequence[bool],
    reward_priority_order: Optional[Sequence[str]] = None,
) -> Optional[int]:
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


_HARVEST_UNKNOWN_VALUE = 65.0


def choose_harvest_position(
    emojis: Sequence[str],
    disabled: Sequence[bool],
    paid_clicks: int = 0,
    priority_order: Optional[Sequence[str]] = None,
    unknown_explore_clicks: int = 3,
    remaining_clicks: Optional[int] = None,
) -> Optional[int]:
    """Explore while rewards can still be collected, then harvest by value."""
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
_QUEST_CLUE_BY_COUNT = {count: name for name, count in _QUEST_CLUES.items()}
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


def choose_quest_position(emojis: Sequence[str], disabled: Sequence[bool]) -> Optional[int]:
    """Pick the $oq cell with the best purple chance, weighted by the clue it reveals otherwise."""
    board = [normalize_sphere_emoji(value) for value in emojis]
    blocked = [bool(value) for value in disabled]
    if len(board) != BOARD_CELLS or len(blocked) != BOARD_CELLS:
        return None
    candidates = _sphere_game_candidates(board, blocked)
    if not candidates:
        return None
    layouts = quest_purple_layouts(board)
    if not layouts:
        return min(candidates, key=lambda index: (_center_distance(index), index))

    def score(position: int):
        bit = 1 << position
        without = [layout for layout in layouts if not layout & bit]
        purple_chance = 1.0 - len(without) / len(layouts)
        clue_value = (
            sum(
                _SPHERE_VALUES[_QUEST_CLUE_BY_COUNT[_bit_count(layout & _NEIGHBOR_MASKS[position])]]
                for layout in without
            ) / len(without)
            if without else 0.0
        )
        expected = purple_chance * _QUEST_PURPLE_VALUE + (1.0 - purple_chance) * clue_value
        return expected, purple_chance, -_center_distance(position), -position

    return max(candidates, key=score)


# $ot: each color sits on one straight run in a row or column; only blue
# costs a click. Lengths come from the board text, these are the defaults.
_TRACE_BASE_COLORS = {"spT": "teal", "spG": "green", "spY": "yellow"}


@dataclass(frozen=True)
class TraceRules:
    lengths: Dict[str, int] = field(default_factory=lambda: {"spT": 4, "spG": 3, "spY": 3})
    rare_length: int = 2
    rare_colors: int = 2


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
    return TraceRules(lengths=lengths, rare_length=rare_length, rare_colors=rare_colors)


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


def choose_trace_position(
    emojis: Sequence[str],
    disabled: Sequence[bool],
    rules: Optional[TraceRules] = None,
) -> Optional[int]:
    """Pick the $ot cell least likely to be blue, the only color that costs a click."""
    board = [normalize_sphere_emoji(value) for value in emojis]
    blocked = [bool(value) for value in disabled]
    if len(board) != BOARD_CELLS or len(blocked) != BOARD_CELLS:
        return None
    candidates = _sphere_game_candidates(board, blocked)
    if not candidates:
        return None
    rules = rules or TraceRules()
    hidden = {index for index, name in enumerate(board) if name == UNKNOWN_SPHERE}
    coverage = [0.0] * BOARD_CELLS

    # ponytail: colors are scored independently (overlaps between runs are
    # ignored); swap in a joint enumeration if measured blue clicks need it.
    def add_runs(found, length, copies=1.0):
        if len(found) >= length or copies <= 0:
            return
        runs = [
            run for run in _straight_runs(length)
            if found.issubset(run) and all(cell in hidden or cell in found for cell in run)
        ]
        for run in runs:
            for cell in run:
                if cell in hidden:
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

    return max(
        candidates,
        key=lambda index: (coverage[index], -_center_distance(index), -index),
    )
