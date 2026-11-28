"""Running kakera and sphere totals per account, read from replies the bot already gets.

Nothing here sends a command. The totals come from:

* the ``$tu`` reply the program already requests on its own schedule (the two
  «Stock: N <emoji>» lines; told apart by the emoji after the number, never by
  their position),
* the sphere-game result message (``$oh``/``$oc``/``$oq``/``$ot``): its last line
  carries «(Stock: N)», the sphere total after the game; without it the «+N»
  lines are added once each, even when the message is edited many times,
* the outcomes of gives/upgrades the program itself performs.

A total that cannot be read is ``None`` ("unknown"), never 0.
"""

import datetime
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

KAKERA = "kakera"
SPHERES = "spheres"

SOURCE_TU = "$tu"
SOURCE_GAME = "game result"
SOURCE_GAME_GAINS = "game result (+N lines)"
SOURCE_GIVE = "give"
SOURCE_GIFT_RECEIVED = "gift received"
SOURCE_UPGRADE = "upgrade"

# 159,247 / 159.247 / 159 247 (also no-break and narrow no-break spaces) / 905
NUMBER = r"\d{1,3}(?:[,.   ]\d{3})+(?!\d)|\d+"
_EMOJI_TOKEN = r"<a?:(?P<raw>[A-Za-z0-9_~]+):\d+>|:(?P<rendered>[A-Za-z0-9_~]+):|(?P<bare>[A-Za-z][A-Za-z0-9_]*)"

# «Stock: **159,247** <:kakera:123>» (localized words for "stock" included).
_TU_STOCK_RE = re.compile(
    r"(?:stock|estoque|existencias|reserva)\s*:\s*\**\s*(?P<num>" + NUMBER + r")\s*\**\s*(?:" + _EMOJI_TOKEN + r")?",
    re.IGNORECASE,
)
# «(Stock: **8,635**)» on the last line of a sphere-game result.
_GAME_STOCK_RE = re.compile(
    r"\(\s*(?:stock|estoque|existencias|reserva)\s*:\s*\**\s*(?P<num>" + NUMBER + r")\s*\**\s*\)",
    re.IGNORECASE,
)
# «<:spB:1> +28», «<:spP:1> (Free) +92», «:spO: +108 (Stock: 8,635)».
_GAME_GAIN_RE = re.compile(
    r"^\s*(?:" + r"<a?:(?P<raw>[A-Za-z0-9_~]+):\d+>|:(?P<rendered>[A-Za-z0-9_~]+):" + r")\s*"
    r"(?:\(\s*(?:free|gratis|gr[aá]tis)\s*\)\s*)?\+\s*\**\s*(?P<num>" + NUMBER + r")",
    re.IGNORECASE,
)


def parse_amount(raw) -> Optional[int]:
    """«159,247» → 159247; anything that is not a whole number → None."""
    if raw is None:
        return None
    text = re.sub(r"[,.   ]", "", str(raw).strip().strip("*"))
    return int(text) if text.isdigit() else None


def emoji_kind(name) -> Optional[str]:
    """``"kakera"`` for kakera emojis, ``"spheres"`` for sphere emojis, else None."""
    value = str(name or "").strip().strip(":")
    folded = value.casefold()
    if folded.startswith("kakera"):
        return KAKERA
    if re.fullmatch(r"sp[a-z]?\d?", folded) or "sphere" in folded:
        return SPHERES
    return None


def _token_name(match) -> Optional[str]:
    return match.group("raw") or match.group("rendered") or match.group("bare")


@dataclass(frozen=True)
class TuTotals:
    kakera: Optional[int] = None
    spheres: Optional[int] = None


def parse_tu_totals(text) -> TuTotals:
    """Kakera and sphere totals from a ``$tu`` reply (raw or rendered emojis).

    Each «Stock:» line is classified by the emoji right after its number. A
    line without a recognisable emoji is ignored, and two lines of the same
    kind that disagree make that total unknown.
    """
    found: Dict[str, set] = {KAKERA: set(), SPHERES: set()}
    for line in str(text or "").splitlines():
        for match in _TU_STOCK_RE.finditer(line):
            kind = emoji_kind(_token_name(match))
            amount = parse_amount(match.group("num"))
            if kind is not None and amount is not None:
                found[kind].add(amount)

    def single(values):
        return next(iter(values)) if len(values) == 1 else None

    return TuTotals(kakera=single(found[KAKERA]), spheres=single(found[SPHERES]))


@dataclass(frozen=True)
class SphereGameResult:
    gains: Tuple[int, ...] = ()
    stock: Optional[int] = None

    @property
    def is_result(self) -> bool:
        return bool(self.gains) or self.stock is not None


def parse_sphere_game_result(text) -> SphereGameResult:
    """The «+N» lines (sphere emoji first; «(Free) +N» counts) and the «(Stock: N)»."""
    gains: List[int] = []
    stock = None
    for line in str(text or "").splitlines():
        match = _GAME_GAIN_RE.match(line)
        if match and emoji_kind(match.group("raw") or match.group("rendered")) == SPHERES:
            amount = parse_amount(match.group("num"))
            if amount is not None:
                gains.append(amount)
        stock_match = _GAME_STOCK_RE.search(line)
        if stock_match:
            value = parse_amount(stock_match.group("num"))
            if value is not None:
                stock = value
    return SphereGameResult(gains=tuple(gains), stock=stock)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class AccountTotals:
    """One account's running ``{kakera, spheres, as_of, source}`` (thread-safe)."""

    _MAX_TRACKED_GAMES = 50

    def __init__(self, name="", clock=_now):
        self.name = name
        self._clock = clock
        self._lock = threading.Lock()
        self._values = {KAKERA: None, SPHERES: None}
        self._as_of = {KAKERA: None, SPHERES: None}
        self._source = {KAKERA: None, SPHERES: None}
        # message id → (lines already added, authoritative stock seen)
        self._games: "OrderedDict[object, Tuple[int, bool]]" = OrderedDict()

    # -- reading ---------------------------------------------------------
    @property
    def kakera(self) -> Optional[int]:
        with self._lock:
            return self._values[KAKERA]

    @property
    def spheres(self) -> Optional[int]:
        with self._lock:
            return self._values[SPHERES]

    def at_least(self, kind, amount) -> bool:
        """True only when the total is known and ``>= amount`` (e.g. spheres ≥ X)."""
        with self._lock:
            value = self._values[kind]
        return value is not None and value >= amount

    def spheres_at_least(self, amount) -> bool:
        return self.at_least(SPHERES, amount)

    def kakera_at_least(self, amount) -> bool:
        return self.at_least(KAKERA, amount)

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            stamps = [stamp for stamp in self._as_of.values() if stamp is not None]
            latest = max(stamps) if stamps else None
            latest_kind = next((kind for kind, stamp in self._as_of.items() if stamp == latest), None) if latest else None
            return {
                "kakera": self._values[KAKERA],
                "spheres": self._values[SPHERES],
                "as_of": latest.isoformat() if latest else None,
                "source": self._source[latest_kind] if latest_kind else None,
                "kakera_as_of": self._as_of[KAKERA].isoformat() if self._as_of[KAKERA] else None,
                "kakera_source": self._source[KAKERA],
                "spheres_as_of": self._as_of[SPHERES].isoformat() if self._as_of[SPHERES] else None,
                "spheres_source": self._source[SPHERES],
            }

    def describe(self) -> str:
        snap = self.snapshot()

        def show(value):
            return "unknown" if value is None else "{:,}".format(value)

        return "kakera {} · spheres {}".format(show(snap["kakera"]), show(snap["spheres"]))

    # -- writing ---------------------------------------------------------
    def _set(self, kind, value, source, when=None):
        self._values[kind] = value
        self._as_of[kind] = when or self._clock()
        self._source[kind] = source

    def set_total(self, kind, value, source, when=None):
        with self._lock:
            self._set(kind, value, source, when)

    def add(self, kind, delta, source, when=None) -> Optional[int]:
        """Add (or subtract) to a known total; an unknown total stays unknown."""
        with self._lock:
            current = self._values[kind]
            if current is None:
                return None
            self._set(kind, max(0, current + int(delta)), source, when)
            return self._values[kind]

    def apply_tu(self, text, when=None) -> TuTotals:
        """Replace both totals with what this ``$tu`` reply says (missing → unknown)."""
        parsed = parse_tu_totals(text)
        with self._lock:
            self._set(KAKERA, parsed.kakera, SOURCE_TU, when)
            self._set(SPHERES, parsed.spheres, SOURCE_TU, when)
        return parsed

    def apply_sphere_game_result(self, message_id, text, when=None) -> Optional[int]:
        """Update spheres from a (new or edited) game-result message; returns the change or None.

        «(Stock: N)» sets the total (authoritative). Otherwise only the «+N»
        lines not counted before for this message id are added.
        """
        parsed = parse_sphere_game_result(text)
        if not parsed.is_result:
            return None
        with self._lock:
            counted, final = self._games.get(message_id, (0, False))
            before = self._values[SPHERES]
            if parsed.stock is not None:
                self._set(SPHERES, parsed.stock, SOURCE_GAME, when)
                self._remember_game(message_id, len(parsed.gains), True)
                return None if before is None else parsed.stock - before
            if final:
                return 0
            fresh = parsed.gains[counted:]
            self._remember_game(message_id, max(counted, len(parsed.gains)), False)
            if not fresh or before is None:
                return 0 if not fresh else None
            self._set(SPHERES, before + sum(fresh), SOURCE_GAME_GAINS, when)
            return sum(fresh)

    def _remember_game(self, message_id, counted, final):
        self._games[message_id] = (counted, final)
        self._games.move_to_end(message_id)
        while len(self._games) > self._MAX_TRACKED_GAMES:
            self._games.popitem(last=False)


def account_key(profile_id, account_index=1) -> str:
    """Stable key of one account: the profile's stable id plus its token number."""
    return "{}#{}".format(str(profile_id or "").strip() or "unknown", int(account_index or 1))


class TotalsBook:
    """Every running account's totals, shared by the accounts of this process."""

    def __init__(self, clock=_now):
        self._clock = clock
        self._lock = threading.Lock()
        self._accounts: Dict[str, AccountTotals] = {}
        self._user_ids: Dict[str, str] = {}

    def account(self, key, name="") -> AccountTotals:
        with self._lock:
            totals = self._accounts.get(key)
            if totals is None:
                totals = self._accounts[key] = AccountTotals(name, clock=self._clock)
            elif name:
                totals.name = name
            return totals

    def note_user_id(self, key, user_id):
        if user_id:
            with self._lock:
                self._user_ids[key] = str(user_id)

    def by_user_id(self, user_id) -> Optional[AccountTotals]:
        wanted = str(user_id or "")
        if not wanted:
            return None
        with self._lock:
            for key, value in self._user_ids.items():
                if value == wanted:
                    return self._accounts.get(key)
        return None

    def forget(self, key):
        with self._lock:
            self._accounts.pop(key, None)
            self._user_ids.pop(key, None)

    def snapshot_all(self) -> Dict[str, Dict[str, object]]:
        with self._lock:
            items = list(self._accounts.items())
        return {key: dict(totals.snapshot(), name=totals.name) for key, totals in items}
