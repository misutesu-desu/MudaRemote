"""The account's sphere stock (and kakera stock), read from replies the bot already receives.

Nothing here sends a command. The sphere stock comes from:

* the ``$tu`` reply the bot already requests: of its «Stock: N <emoji>» lines,
  the one followed by a sphere emoji (the other one is the kakera stock; the
  two are told apart by the emoji after the number, never by their order),
* the sphere-game result message (``$oh``/``$oc``/``$oq``/``$ot``): its last
  line carries «(Stock: N)», the sphere stock after the game; without it the
  «<sphere> +N» lines are added once each, even when the message is edited,
* what the perk upgrade itself spends.

The kakera stock is the «Stock: N <kakera emoji>» line of the same ``$tu``.
A stock that cannot be read is ``None`` (unknown), never 0.
"""

import re
import threading
from collections import OrderedDict
from typing import Optional, Tuple

# 159,247 / 159.247 / 159 247 (also no-break and narrow no-break spaces) / 905
NUMBER = r"\d{1,3}(?:[,.   ]\d{3})+(?!\d)|\d+"
_EMOJI_TOKEN = r"<a?:(?P<raw>[A-Za-z0-9_~]+):\d+>|:(?P<rendered>[A-Za-z0-9_~]+):|(?P<bare>[A-Za-z][A-Za-z0-9_]*)"

# «Stock: **905** <:spR:123>» (localized words for "stock" included).
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
    r"^\s*(?:<a?:(?P<raw>[A-Za-z0-9_~]+):\d+>|:(?P<rendered>[A-Za-z0-9_~]+):)\s*"
    r"(?:\(\s*(?:free|gratis|gr[aá]tis)\s*\)\s*)?\+\s*\**\s*(?P<num>" + NUMBER + r")",
    re.IGNORECASE,
)


def parse_amount(raw) -> Optional[int]:
    """«159,247» → 159247; anything that is not a whole number → None."""
    if raw is None:
        return None
    text = re.sub(r"[,.   ]", "", str(raw).strip().strip("*"))
    return int(text) if text.isdigit() else None


def is_sphere_emoji(name) -> bool:
    """``spR``, ``spB2``, ``sp`` … or any emoji name containing «sphere»; kakera emojis are not."""
    folded = str(name or "").strip().strip(":").casefold()
    if not folded or folded.startswith("kakera"):
        return False
    return bool(re.fullmatch(r"sp[a-z]?\d?", folded)) or "sphere" in folded


def is_kakera_emoji(name) -> bool:
    """``kakera``, ``kakeraY``, ``kakeraP`` … (the emoji after the kakera «Stock:» number)."""
    return str(name or "").strip().strip(":").casefold().startswith("kakera")


def _token_name(match) -> Optional[str]:
    return match.group("raw") or match.group("rendered") or match.group("bare")


def _parse_tu_stock(text, is_kind) -> Optional[int]:
    found = set()
    for line in str(text or "").splitlines():
        for match in _TU_STOCK_RE.finditer(line):
            amount = parse_amount(match.group("num"))
            if amount is not None and is_kind(_token_name(match)):
                found.add(amount)
    return next(iter(found)) if len(found) == 1 else None


def parse_tu_sphere_stock(text) -> Optional[int]:
    """The sphere stock of a ``$tu`` reply (raw or rendered emojis), else None.

    Only a «Stock:» line followed by a sphere emoji counts; two such lines
    that disagree make the stock unknown.
    """
    return _parse_tu_stock(text, is_sphere_emoji)


def parse_tu_kakera_stock(text) -> Optional[int]:
    """The kakera stock of a ``$tu`` reply: the «Stock:» line followed by a kakera emoji, else None."""
    return _parse_tu_stock(text, is_kakera_emoji)


def parse_sphere_game_result(text) -> Tuple[Tuple[int, ...], Optional[int]]:
    """``(gains, stock)``: the «<sphere> +N» lines («(Free) +N» counts) and the «(Stock: N)»."""
    gains = []
    stock = None
    for line in str(text or "").splitlines():
        match = _GAME_GAIN_RE.match(line)
        if match and is_sphere_emoji(match.group("raw") or match.group("rendered")):
            amount = parse_amount(match.group("num"))
            if amount is not None:
                gains.append(amount)
        stock_match = _GAME_STOCK_RE.search(line)
        if stock_match:
            value = parse_amount(stock_match.group("num"))
            if value is not None:
                stock = value
    return tuple(gains), stock


def is_sphere_game_result(text) -> bool:
    gains, stock = parse_sphere_game_result(text)
    return bool(gains) or stock is not None


class SphereStock:
    """One account's running sphere stock (thread-safe); ``None`` while unknown."""

    _MAX_TRACKED_GAMES = 50

    def __init__(self):
        self._lock = threading.Lock()
        self._value = None
        # game-result message id → (gain lines already added, «(Stock: N)» seen)
        self._games = OrderedDict()

    @property
    def spheres(self) -> Optional[int]:
        with self._lock:
            return self._value

    def set(self, value):
        with self._lock:
            self._value = None if value is None else max(0, int(value))

    def spend(self, amount) -> Optional[int]:
        """Subtract from a known stock; an unknown stock stays unknown."""
        with self._lock:
            if self._value is not None:
                self._value = max(0, self._value - int(amount))
            return self._value

    def apply_tu(self, text) -> Optional[int]:
        """Take the stock from a ``$tu`` reply (a reply without it makes the stock unknown)."""
        value = parse_tu_sphere_stock(text)
        self.set(value)
        return value

    def apply_game_result(self, message_id, text) -> bool:
        """Update from a (new or edited) game-result message; True when the stock changed.

        «(Stock: N)» sets the stock. Otherwise only the «+N» lines not added
        before for this message id are added (to a known stock).
        """
        gains, stock = parse_sphere_game_result(text)
        if not gains and stock is None:
            return False
        with self._lock:
            counted, final = self._games.get(message_id, (0, False))
            before = self._value
            if stock is not None:
                self._value = stock
                self._remember(message_id, len(gains), True)
                return before != stock
            if final:
                return False
            fresh = gains[counted:]
            self._remember(message_id, max(counted, len(gains)), False)
            if not fresh or before is None:
                return False
            self._value = before + sum(fresh)
            return True

    def _remember(self, message_id, counted, final):
        self._games[message_id] = (counted, final)
        self._games.move_to_end(message_id)
        while len(self._games) > self._MAX_TRACKED_GAMES:
            self._games.popitem(last=False)


class KakeraStock:
    """One account's kakera stock from the latest ``$tu`` (minus what it gave since); ``None`` while unknown."""

    def __init__(self):
        self._lock = threading.Lock()
        self._value = None

    @property
    def kakera(self) -> Optional[int]:
        with self._lock:
            return self._value

    def set(self, value):
        with self._lock:
            self._value = None if value is None else max(0, int(value))

    def spend(self, amount) -> Optional[int]:
        with self._lock:
            if self._value is not None:
                self._value = max(0, self._value - int(amount))
            return self._value

    def apply_tu(self, text) -> Optional[int]:
        value = parse_tu_kakera_stock(text)
        self.set(value)
        return value
