"""Automatic perk-10 upgrade: spend spheres on ``$oic name $ name $ … $ 10``.

Order of work (the owner's words): first every sphere game the latest ``$tu``
shows as available is played out by the existing sphere automation; never
start while a game is available or running, or while the account is busy with
rolls, claims or gives. Then the FINAL sphere stock is the running total (the
«(Stock: N)» of the last game result when newer, else the latest ``$tu``) —
no extra ``$tu`` is ever sent; an unknown stock waits for the next one. With a
final stock of at least the minimum (default 2,000), floor(stock / 1,000)
characters are upgraded (10,000 → 10), capped by the user's maximum and by the
names ``$mmz-`` lists (the characters without the upgrade). An optional amount
(``perk10_amount``, 0 = off) upgrades exactly that many once the minimum is
reached, or what the stock affords when that is fewer. «Upgrade perk 10 now»
(``upgrade_now``) runs one pass on request: no switch, minimum or daily cap,
but at least 1,000 spheres known and the same waiting and verification rules.

Flow (game bot replies as transcribed from the owner's recordings):

    account: $mmz-                       (read once; pages turned with its buttons)
    account: $oic Name One $ Name Two $ … $ 10
    bot:     «Do you really want to spend 10,000 <sphere> for 10 characters? (y/n/yes/no)»
             [… «Characters not found: name a, name b»]
    account: Y      (only when M = names sent − not found, N = M × 1,000 and N ≤ stock; else n)
    bot:     ✅ reaction on the account's «Y»

A long name list is split into several commands (each under 1,900
characters, each ending «$ 10»), each finished before the next. Names the bot
reports «not found» are remembered per account (persisted) and skipped next
time. Any other outcome stops cleanly (answers n while the question is open),
logs the bot's text and backs off with growing delays. One upgrade at a time,
at most N per day; an empty ``$mmz-`` is re-checked at most once per 6 hours.
"""

import asyncio
import datetime
import random
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

from .harem_list import LIST_MMZ, HaremListReader
from .kakera_give import BACKOFF_STEPS_SECONDS, BotReply
from .spheres import SPHERE_GAME_KINDS
from .totals import NUMBER, SOURCE_UPGRADE, SPHERES, emoji_kind, parse_amount

PERK10_DEFAULTS = {
    "auto_perk10": False,
    "perk10_min_spheres": 2000,
    "perk10_max_characters": 100,
    "perk10_daily_cap": 3,
    "perk10_amount": 0,  # 0: as many characters as the spheres allow
}
PERK10_COST = 1000  # spheres per character for perk 10
PERK_NUMBER = 10
MIN_SPHERES_MIN = PERK10_COST
MIN_SPHERES_MAX = 1_000_000_000
MAX_CHARACTERS_MAX = 10_000
DAILY_CAP_MAX = 50
AMOUNT_MAX = 10_000
# «Upgrade perk 10 now» (a button, started by hand): same numbers as the give-now buttons.
MANUAL_COOLDOWN_SECONDS = 60.0
MANUAL_BUSY_WAIT_SECONDS = 600.0
MANUAL_POLL_SECONDS = 3.0
MANUAL_STOCK_WAIT_SECONDS = 3600.0
# A Discord message holds 2,000 characters; every command stays under this.
COMMAND_LENGTH_LIMIT = 1900
# At most this many $mmz- pages are read in one upgrade.
MAX_PAGES_PER_UPGRADE = 40
QUESTION_TIMEOUT_SECONDS = 20.0
ACK_TIMEOUT_SECONDS = 20.0
# After a «Characters not found» reply without a question (every name unknown).
FOLLOWUP_TIMEOUT_SECONDS = 5.0
EMPTY_RECHECK_SECONDS = 6 * 3600.0
NOT_FOUND_MEMORY_MAX = 1000

STATE_SECTION_UPGRADES = "perk10_upgrades"
STATE_SECTION_NOT_FOUND = "perk10_not_found"
STATE_SECTION_EMPTY = "perk10_empty"

IDLE = "idle"
READING = "reading $mmz-"
SENDING = "sending"
AWAITING_QUESTION = "awaiting question"
ANSWERING = "answering"
AWAITING_ACK = "awaiting ✅"

_EMOJI = r"(?:<a?:(?P<raw>[A-Za-z0-9_~]+):\d+>|:(?P<rendered>[A-Za-z0-9_~]+):)"
_QUESTION_RE = re.compile(
    r"(?:do you really want to spend)\s+\**\s*(?P<cost>" + NUMBER + r")\s*\**\s*" + _EMOJI
    + r"?\s*for\s+\**\s*(?P<count>" + NUMBER + r")\s*\**\s*characters?",
    re.IGNORECASE,
)
_NOT_FOUND_RE = re.compile(r"characters?\s+not\s+found\s*:\s*(?P<names>[^\n]*)", re.IGNORECASE)
_REFUSAL_WORDS = (
    "not enough", "don't have enough", "do not have enough", "you don't have", "you do not have",
    "can't", "cannot", "not allowed", "procedure has been stopped", "invalid", "insuficiente", "no tienes",
)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def _whole(value, default, minimum, maximum):
    if isinstance(value, bool):
        return None
    try:
        number = int(str(value if value is not None else default).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if minimum <= number <= maximum else None


@dataclass(frozen=True)
class Perk10Settings:
    enabled: bool = False
    min_spheres: int = 2000
    max_characters: int = 100  # 0: no limit
    daily_cap: int = 3
    amount: int = 0  # 0: as many as the spheres allow

    @classmethod
    def from_preset(cls, data):
        data = data or {}

        def number(key, minimum, maximum):
            found = _whole(data.get(key), PERK10_DEFAULTS[key], minimum, maximum)
            return PERK10_DEFAULTS[key] if found is None else found

        return cls(
            enabled=bool(data.get("auto_perk10", False)),
            min_spheres=number("perk10_min_spheres", MIN_SPHERES_MIN, MIN_SPHERES_MAX),
            max_characters=number("perk10_max_characters", 0, MAX_CHARACTERS_MAX),
            daily_cap=number("perk10_daily_cap", 1, DAILY_CAP_MAX),
            amount=number("perk10_amount", 0, AMOUNT_MAX),
        )


def validate_perk10_settings(data):
    data = data or {}
    errors = []
    checks = (
        ("perk10_min_spheres", "Upgrade when spheres reach", MIN_SPHERES_MIN, MIN_SPHERES_MAX),
        ("perk10_max_characters", "Most characters per upgrade (0 = no limit)", 0, MAX_CHARACTERS_MAX),
        ("perk10_daily_cap", "At most N upgrades per day", 1, DAILY_CAP_MAX),
        ("perk10_amount", "Characters to upgrade each time (0 = as many as the spheres allow)", 0, AMOUNT_MAX),
    )
    for key, label, minimum, maximum in checks:
        if _whole(data.get(key, PERK10_DEFAULTS[key]), PERK10_DEFAULTS[key], minimum, maximum) is None:
            errors.append("«{}» must be a whole number from {:,} to {:,}.".format(label, minimum, maximum))
    return errors


# ---------------------------------------------------------------------------
# Decisions (pure)
# ---------------------------------------------------------------------------

def upgrade_count(stock, minimum, maximum=0, names_available=None, amount=0) -> int:
    """How many characters to upgrade once ``stock`` ≥ ``minimum`` (never more than the stock pays for).

    Without ``amount``: floor(stock / 1000), capped by ``maximum`` (0 = no limit)
    and the names available: 1999 → 0, 2000 → 2, 10000 → 10. With ``amount`` above 0:
    exactly that many, but never more than the stock affords (minimum 2000,
    amount 5, stock 2300 → 2): it never waits for more spheres.
    """
    if stock is None or minimum is None or stock < max(minimum, PERK10_COST):
        return 0
    count = int(stock) // PERK10_COST
    if amount and amount > 0:
        count = min(count, int(amount))
    if maximum and maximum > 0:
        count = min(count, int(maximum))
    if names_available is not None:
        count = min(count, max(0, int(names_available)))
    return max(0, count)


def sphere_games_pending(counts, enabled, *, running=False, status_seen=True) -> Optional[str]:
    """Why sphere games come first (None: every available game is played out).

    ``counts`` are the uses left per game as the existing sphere automation
    tracks them (set from ``$tu``, lowered as boards start); ``enabled`` says
    which games that automation plays. A game the user does not automate is
    not waited for (it would never be played).
    """
    if running:
        return "a sphere game is being played"
    automated = [kind for kind in SPHERE_GAME_KINDS if (enabled or {}).get(kind)]
    if automated and not status_seen:
        return "the sphere games left are not known yet (read from the next $tu)"
    left = ["${} {}".format(kind, int((counts or {}).get(kind, 0) or 0))
            for kind in automated if int((counts or {}).get(kind, 0) or 0) > 0]
    if left:
        return "sphere games are still available ({})".format(", ".join(left))
    return None


def normalize_name(name) -> str:
    """Case, accents and spacing folded (how «Characters not found» is compared)."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().casefold()


def usable_name(name) -> bool:
    """A listed name can go into the command whole (no «$», which separates names)."""
    text = str(name or "").strip()
    return bool(text) and "$" not in text and "\n" not in text and len(text) < COMMAND_LENGTH_LIMIT - 20


def build_commands(names: Sequence[str], prefix="$", limit=COMMAND_LENGTH_LIMIT) -> List[Tuple[str, Tuple[str, ...]]]:
    """``[(command, names_in_it), …]``: «$oic a $ b $ … $ 10», each shorter than ``limit``."""
    prefix = prefix or "$"
    head = "{}oic ".format(prefix)
    tail = " $ {}".format(PERK_NUMBER)
    commands = []
    chunk: List[str] = []
    for name in names:
        name = str(name).strip()
        trial = head + " $ ".join(chunk + [name]) + tail
        if chunk and len(trial) >= limit:
            commands.append((head + " $ ".join(chunk) + tail, tuple(chunk)))
            chunk = [name]
        else:
            chunk.append(name)
    if chunk:
        commands.append((head + " $ ".join(chunk) + tail, tuple(chunk)))
    return [item for item in commands if len(item[0]) < limit]


@dataclass(frozen=True)
class OicQuestion:
    cost: int
    count: int


def parse_oic_question(text) -> Optional[OicQuestion]:
    """«Do you really want to spend 10,000 <sphere> for 10 characters? (y/n/yes/no)»."""
    folded = str(text or "")
    if not re.search(r"y\s*/\s*n|yes\s*/\s*no", folded, re.IGNORECASE):
        return None
    match = _QUESTION_RE.search(folded)
    if not match:
        return None
    name = match.group("raw") or match.group("rendered")
    if name and emoji_kind(name) not in (SPHERES, None):
        return None
    cost = parse_amount(match.group("cost"))
    count = parse_amount(match.group("count"))
    if cost is None or count is None:
        return None
    return OicQuestion(cost=cost, count=count)


def parse_not_found(text) -> Tuple[str, ...]:
    """«Characters not found: satanichia mcdowell, kurumizawa» → the names as printed."""
    found = []
    for match in _NOT_FOUND_RE.finditer(str(text or "")):
        for part in match.group("names").split(","):
            part = part.strip().strip("*_` ").strip()
            if part:
                found.append(part)
    return tuple(found)


def looks_like_refusal(text) -> bool:
    folded = str(text or "").casefold()
    return any(word in folded for word in _REFUSAL_WORDS)


# ---------------------------------------------------------------------------
# The upgrader
# ---------------------------------------------------------------------------

@dataclass
class UpgradeOutcome:
    status: str  # "upgraded", "stopped", "skipped", "empty"
    reason: str = ""
    characters: int = 0
    cost: int = 0
    names: Tuple[str, ...] = ()
    bot_text: str = ""


@dataclass
class _Attempt:
    channel_id: object
    own_id: str
    own_names: Tuple[str, ...]
    sent_ids: set = field(default_factory=set)
    question_open: bool = False
    counted: bool = False


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class PerkUpgrader:
    """One per account (main or side).

    ``send(channel, text)`` returns the sent message (or None/False);
    ``click(button)`` turns ``$mmz-`` pages; ``wait(seconds)`` is the bot's
    interruptible delay (False when paused/stopping).
    """

    def __init__(self, *, key, store, send, click, wait, log, clock=_now, monotonic=time.monotonic,
                 question_timeout=QUESTION_TIMEOUT_SECONDS, ack_timeout=ACK_TIMEOUT_SECONDS,
                 followup_timeout=FOLLOWUP_TIMEOUT_SECONDS, backoff_steps=BACKOFF_STEPS_SECONDS,
                 answer_delay=(1.1, 2.6), between_commands=(2.0, 4.0), reader=None):
        self.key = key
        self.store = store
        self._send = send
        self._wait = wait
        self._log = log
        self._clock = clock
        self._monotonic = monotonic
        self.question_timeout = question_timeout
        self.ack_timeout = ack_timeout
        self.followup_timeout = followup_timeout
        self.backoff_steps = tuple(backoff_steps)
        self.answer_delay = answer_delay
        self.between_commands = between_commands
        self.reader = reader or HaremListReader(send=send, click=click, wait=wait, log=log, monotonic=monotonic)
        self.state = IDLE
        self.status = "Perk 10: idle."
        self._failures = 0
        self._retry_at = None  # monotonic seconds
        self._attempt: Optional[_Attempt] = None
        self._queue: Optional[asyncio.Queue] = None
        self._manual_in_flight = False
        self._manual_pressed_at = None

    # -- feeding events --------------------------------------------------
    @property
    def active(self) -> bool:
        return self._attempt is not None or self.state != IDLE

    def on_message(self, message, text):
        """Every game-bot message in the account's channels."""
        self.reader.on_message(message)
        attempt = self._attempt
        if attempt is None or self._queue is None:
            return
        channel = getattr(message, "channel", None)
        channel_id = getattr(channel, "id", None) if channel is not None else getattr(message, "channel_id", None)
        if channel_id != attempt.channel_id:
            return
        reference = getattr(message, "reference", None)
        self._queue.put_nowait(("reply", BotReply(getattr(message, "id", None), channel_id, text,
                                                  getattr(reference, "message_id", None))))

    def on_edit(self, message):
        self.reader.on_edit(message)

    def on_ack(self, message_id):
        """The game bot put ✅ on a message (the account's «Y» means success)."""
        if self._attempt is not None and self._queue is not None:
            self._queue.put_nowait(("ack", message_id))

    def on_refused(self, message_id):
        if self._attempt is not None and self._queue is not None:
            self._queue.put_nowait(("refused", message_id))

    # -- persisted state -------------------------------------------------
    def today(self):
        return self._clock().date()

    def upgrades_today(self) -> int:
        record = self.store.get(self.key, STATE_SECTION_UPGRADES) or {}
        return int(record.get("count", 0)) if record.get("day") == self.today().isoformat() else 0

    def _count_upgrade(self) -> int:
        count = self.upgrades_today() + 1
        self.store.put(self.key, STATE_SECTION_UPGRADES, {"day": self.today().isoformat(), "count": count})
        return count

    def not_found_names(self) -> Tuple[str, ...]:
        record = self.store.get(self.key, STATE_SECTION_NOT_FOUND) or {}
        names = record.get("names") if isinstance(record, dict) else None
        return tuple(str(name) for name in names or () if name)

    def _remember_not_found(self, names):
        known = list(self.not_found_names())
        fresh = [normalize_name(name) for name in names if normalize_name(name) and normalize_name(name) not in known]
        if not fresh:
            return
        known.extend(dict.fromkeys(fresh))
        self.store.put(self.key, STATE_SECTION_NOT_FOUND, {"names": known[-NOT_FOUND_MEMORY_MAX:]})

    def forget_not_found(self):
        self.store.put(self.key, STATE_SECTION_NOT_FOUND, None)

    def empty_since(self) -> Optional[datetime.datetime]:
        record = self.store.get(self.key, STATE_SECTION_EMPTY) or {}
        try:
            return datetime.datetime.fromisoformat(record.get("at"))
        except (TypeError, ValueError):
            return None

    def _record_empty(self, reason):
        self.store.put(self.key, STATE_SECTION_EMPTY, {"at": self._clock().isoformat(), "reason": reason})

    # -- decisions -------------------------------------------------------
    def blocker(self, settings: Perk10Settings, *, stock, games_reason=None, busy_reason=None) -> Optional[str]:
        """Why no upgrade may start now (None: one may start)."""
        if not settings.enabled:
            return "off"
        if self._attempt is not None or self.state != IDLE:
            return "an upgrade is already in progress"
        if busy_reason:
            return "busy: " + busy_reason
        if games_reason:
            return "sphere games first: " + games_reason
        if self._retry_at is not None and self._monotonic() < self._retry_at:
            wait_minutes = max(1, int((self._retry_at - self._monotonic()) // 60))
            return "backing off for about {} min after the last failed upgrade".format(wait_minutes)
        empty_at = self.empty_since()
        if empty_at is not None:
            next_check = empty_at + datetime.timedelta(seconds=EMPTY_RECHECK_SECONDS)
            if self._clock() < next_check:
                return "$mmz- listed nothing to upgrade; next check after {} UTC".format(
                    next_check.astimezone(datetime.timezone.utc).strftime("%H:%M"))
        if stock is None:
            return "the sphere stock is unknown (it is read from the next $tu or sphere game result)"
        if stock < settings.min_spheres:
            return "spheres {:,} are below {:,}".format(stock, settings.min_spheres)
        if self.upgrades_today() >= settings.daily_cap:
            return "the daily limit of {} upgrade(s) is reached".format(settings.daily_cap)
        return None

    async def maybe_upgrade(self, channel, settings: Perk10Settings, *, own_id, own_names, totals, prefix="$",
                            games: Callable[[], Optional[str]] = lambda: None,
                            busy: Callable[[], Optional[str]] = lambda: None) -> UpgradeOutcome:
        stock = totals.spheres if totals is not None else None
        reason = self.blocker(settings, stock=stock, games_reason=games(), busy_reason=busy())
        if reason is not None:
            if reason != "off" and self._attempt is None:
                self.status = "Perk 10 waits: {}.".format(reason)
            elif reason == "off":
                self.status = "Perk 10: off."
            return UpgradeOutcome("skipped", reason)
        return await self._start(channel, settings, own_id, own_names, totals, prefix, games, busy, manual=False)

    async def _start(self, channel, settings, own_id, own_names, totals, prefix, games, busy, *, manual) -> UpgradeOutcome:
        self._attempt = _Attempt(
            channel_id=getattr(channel, "id", None), own_id=str(own_id or ""),
            own_names=tuple(str(name) for name in own_names or () if name),
        )
        self._queue = asyncio.Queue()
        try:
            outcome = await self._run(channel, settings, prefix, totals, games, busy, manual)
        except asyncio.CancelledError:
            await self._answer_no_if_open(channel)
            raise
        except Exception as exc:
            await self._answer_no_if_open(channel)
            outcome = UpgradeOutcome("stopped", "error: {}".format(type(exc).__name__))
        finally:
            self._attempt = None
            self._queue = None
            self.state = IDLE
        self._finish(outcome)
        return outcome

    # -- «Upgrade perk 10 now» ----------------------------------------------
    def _manual_note(self, text, level="INFO"):
        self.status = "Perk 10 (now): " + text
        self._log("Perk 10 «Upgrade perk 10 now»: " + text, level)

    async def upgrade_now(self, channel, settings: Perk10Settings, *, own_id, own_names, totals, prefix="$",
                          allowed_reason: Optional[str] = None,
                          games: Callable[[], Optional[str]] = lambda: None,
                          busy: Callable[[], Optional[str]] = lambda: None,
                          total_wait_seconds=MANUAL_STOCK_WAIT_SECONDS, busy_wait_seconds=MANUAL_BUSY_WAIT_SECONDS,
                          poll_seconds=MANUAL_POLL_SECONDS) -> UpgradeOutcome:
        """One upgrade pass started by hand.

        Ignores the switch, the minimum-spheres trigger and the daily cap; still
        needs at least 1,000 spheres known (never sends ``$tu``: an unknown stock
        waits up to ``total_wait_seconds`` for the next one), waits for sphere
        games and busy work, keeps the failure back-off and the 6-hour
        «$mmz- listed nothing» memory (fewer messages), one at a time, at most
        one press per minute. ``allowed_reason`` (not None) refuses with that text.
        """
        if allowed_reason:
            self._manual_note("not run — {}.".format(allowed_reason))
            return UpgradeOutcome("skipped", allowed_reason)
        now = self._monotonic()
        if self._manual_in_flight:
            return UpgradeOutcome("ignored", "an «Upgrade perk 10 now» request is already running")
        if self._manual_pressed_at is not None and now - self._manual_pressed_at < MANUAL_COOLDOWN_SECONDS:
            return UpgradeOutcome("ignored", "pressed again too soon; wait {} s".format(
                int(MANUAL_COOLDOWN_SECONDS - (now - self._manual_pressed_at)) + 1))
        self._manual_pressed_at = now
        self._manual_in_flight = True
        try:
            if totals is None or totals.spheres is None:
                self._manual_note("the sphere stock is unknown; waiting for the next $tu (up to {} min).".format(
                    max(1, int(total_wait_seconds // 60))))
                deadline = self._monotonic() + total_wait_seconds
                while totals is None or totals.spheres is None:
                    if self._monotonic() >= deadline:
                        return self._manual_stop("the sphere stock is still unknown (no $tu reply read in time)")
                    if not await self._wait(poll_seconds):
                        return self._manual_stop("paused or stopping")
            deadline = self._monotonic() + busy_wait_seconds
            announced = False
            while True:
                reason = (busy() or games()
                          or ("an upgrade is already in progress" if self._attempt is not None or self.state != IDLE else None))
                if reason is None:
                    break
                if not announced:
                    announced = True
                    self._manual_note("deferred while {}; it runs right after.".format(reason))
                if self._monotonic() >= deadline:
                    return self._manual_stop("still busy ({})".format(reason))
                if not await self._wait(poll_seconds):
                    return self._manual_stop("paused or stopping")
            stock = totals.spheres
            if stock is None:
                return self._manual_stop("the sphere stock became unknown")
            if stock < PERK10_COST:
                self._manual_note("not run — only {:,} spheres; perk 10 needs at least {:,}.".format(stock, PERK10_COST))
                return UpgradeOutcome("skipped", "only {:,} spheres".format(stock))
            if self._retry_at is not None and self._monotonic() < self._retry_at:
                minutes = max(1, int((self._retry_at - self._monotonic()) // 60))
                self._manual_note("not run — backing off for about {} min after the last failed upgrade.".format(minutes))
                return UpgradeOutcome("skipped", "backing off")
            empty_at = self.empty_since()
            if empty_at is not None and self._clock() < empty_at + datetime.timedelta(seconds=EMPTY_RECHECK_SECONDS):
                self._manual_note("not run — $mmz- listed nothing to upgrade less than 6 hours ago.")
                return UpgradeOutcome("skipped", "$mmz- listed nothing recently")
            outcome = await self._start(channel, settings, own_id, own_names, totals, prefix, games, busy, manual=True)
            if outcome.status == "skipped":
                self._manual_note("not run — {}.".format(outcome.reason))
            return outcome
        finally:
            self._manual_in_flight = False

    def _manual_stop(self, reason) -> UpgradeOutcome:
        self._manual_note("not run — {}.".format(reason), "WARN")
        return UpgradeOutcome("stopped", reason)

    # -- the flow --------------------------------------------------------
    async def _collect_names(self, channel, count, prefix) -> Tuple[Optional[List[str]], Optional[UpgradeOutcome]]:
        self.state = READING
        read = await self.reader.open(channel, LIST_MMZ, self._attempt.own_names, prefix=prefix)
        if read.status != "ok":
            return None, UpgradeOutcome("stopped", read.reason or "the $mmz- list could not be read")
        skip = set(self.not_found_names())
        names: List[str] = []
        listed = 0
        seen = set()
        page = read.page
        pages_read = 1
        while True:
            for name in page.names:
                listed += 1
                folded = normalize_name(name)
                if folded in seen or folded in skip or not usable_name(name):
                    continue
                seen.add(folded)
                names.append(name)
            if len(names) >= count:
                break
            if page.page >= page.pages or pages_read >= MAX_PAGES_PER_UPGRADE:
                break
            self.reader.last_error = ""
            following = await read.pager.next()
            if following is None:
                if self.reader.last_error:
                    self._log("Perk 10: stopped turning $mmz- pages ({}); using the {} name(s) read.".format(
                        self.reader.last_error, len(names)), "WARN")
                break
            page = following
            pages_read += 1
        if not names:
            reason = ("$mmz- lists no character without the perk-10 upgrade" if listed == 0 else
                      "every name $mmz- listed was reported «not found» before")
            return None, UpgradeOutcome("empty", reason)
        return names[:count], None

    async def _run(self, channel, settings, prefix, totals, games, busy, manual=False):
        stock = totals.spheres
        # A button press ignores the minimum-spheres trigger (one character is 1,000 spheres).
        count = upgrade_count(stock, PERK10_COST if manual else settings.min_spheres, settings.max_characters,
                              amount=settings.amount)
        if count <= 0:
            return UpgradeOutcome("skipped", "spheres {:,} buy no upgrade".format(stock or 0))
        names, failed = await self._collect_names(channel, count, prefix)
        if failed is not None:
            return failed
        commands = build_commands(names, prefix)
        if not commands:
            return UpgradeOutcome("stopped", "no command could be built from the listed names")
        self._log("Perk 10: spheres {:,} → upgrading {} character(s) in {} command(s).".format(
            stock, len(names), len(commands)), "INFO")
        done_names: List[str] = []
        done_cost = 0
        last_text = ""
        for index, (command, chunk) in enumerate(commands):
            if index:
                low, high = self.between_commands
                if not await self._wait(random.uniform(low, high)):
                    return self._partial(done_names, done_cost, "paused or stopping between commands")
                reason = busy() or games()
                if reason:
                    return self._partial(done_names, done_cost, "became busy ({}) between commands".format(reason))
            known = totals.spheres
            if known is None or known < len(chunk) * PERK10_COST:
                return self._partial(done_names, done_cost, "the sphere stock ({}) does not cover {} character(s)".format(
                    "unknown" if known is None else "{:,}".format(known), len(chunk)))
            result = await self._one_command(channel, command, chunk, totals, busy)
            if result.status != "upgraded":
                if done_names:
                    result.reason += " (after {} character(s) already upgraded)".format(len(done_names))
                    result.characters, result.cost = len(done_names), done_cost
                    result.names = tuple(done_names)
                return result
            done_names.extend(result.names)
            done_cost += result.cost
            last_text = result.bot_text
        return UpgradeOutcome("upgraded", "", len(done_names), done_cost, tuple(done_names), last_text)

    def _partial(self, done_names, done_cost, reason):
        if done_names:
            return UpgradeOutcome("upgraded", "stopped early: " + reason, len(done_names), done_cost, tuple(done_names))
        return UpgradeOutcome("stopped", reason)

    async def _send_tracked(self, channel, text):
        receipt = await self._send(channel, text)
        if not receipt:
            return None
        message_id = getattr(receipt, "id", None)
        if message_id is not None and self._attempt is not None:
            self._attempt.sent_ids.add(message_id)
        return receipt

    async def _one_command(self, channel, command, chunk, totals, busy) -> UpgradeOutcome:
        attempt = self._attempt
        attempt.sent_ids.clear()
        self.state = SENDING
        if not await self._send_tracked(channel, command):
            return UpgradeOutcome("stopped", "the $oic command could not be sent")

        self.state = AWAITING_QUESTION
        not_found: List[str] = []
        question = None
        question_text = ""
        timeout = self.question_timeout
        while question is None:
            kind, reply = await self._next(timeout)
            if kind == "timeout":
                if not_found:
                    self._remember_not_found(not_found)
                    return UpgradeOutcome("stopped", "none of the names were found ({}); they are skipped next time".format(
                        ", ".join(not_found)[:300]))
                return UpgradeOutcome("stopped", "the game bot did not ask for confirmation in time")
            if kind == "refused":
                return UpgradeOutcome("stopped", "the game bot refused the command (⛔)")
            if kind == "ack":
                continue
            text = reply.text
            missing = parse_not_found(text)
            not_found.extend(name for name in missing if name not in not_found)
            question = parse_oic_question(text)
            if question is not None:
                question_text = text
                break
            if missing:
                timeout = self.followup_timeout  # the question may still follow
                continue
            if looks_like_refusal(text):
                return UpgradeOutcome("stopped", "the game bot refused the upgrade", bot_text=text)
            return UpgradeOutcome("stopped", "unexpected reply", bot_text=text)
        attempt.question_open = True
        if not_found:
            self._remember_not_found(not_found)

        expected = len(chunk) - len(not_found)
        stock = totals.spheres
        problem = None
        if question.count != expected:
            problem = "the bot asked about {} character(s), expected {}".format(question.count, expected)
        elif question.cost != question.count * PERK10_COST:
            problem = "the bot asked {:,} spheres for {} character(s), not {:,}".format(
                question.cost, question.count, question.count * PERK10_COST)
        elif stock is None or question.cost > stock:
            problem = "the cost {:,} is above the known stock ({})".format(
                question.cost, "unknown" if stock is None else "{:,}".format(stock))
        elif question.count <= 0:
            problem = "nothing to upgrade"
        if problem:
            await self._answer_no_if_open(channel)
            return UpgradeOutcome("stopped", problem + "; answered n", bot_text=question_text)

        self.state = ANSWERING
        low, high = self.answer_delay
        if not await self._wait(random.uniform(low, high)):
            await self._answer_no_if_open(channel)
            return UpgradeOutcome("stopped", "paused or stopping before answering")
        still_busy = busy()
        if still_busy:
            await self._answer_no_if_open(channel)
            return UpgradeOutcome("stopped", "became busy ({}); answered n".format(still_busy))
        answer = await self._send_tracked(channel, "Y")
        if not answer:
            await self._answer_no_if_open(channel)
            return UpgradeOutcome("stopped", "could not answer Y")
        attempt.question_open = False
        answer_id = getattr(answer, "id", None)
        if not attempt.counted:
            attempt.counted = True
            self._count_upgrade()

        self.state = AWAITING_ACK
        missing_folded = {normalize_name(name) for name in not_found}
        upgraded = tuple(name for name in chunk if normalize_name(name) not in missing_folded)
        deadline = self._monotonic() + self.ack_timeout
        while True:
            kind, reply = await self._next(max(0.0, deadline - self._monotonic()))
            if kind == "ack" and (answer_id is None or reply == answer_id):
                totals.add(SPHERES, -question.cost, SOURCE_UPGRADE)
                return UpgradeOutcome("upgraded", "", question.count, question.cost, upgraded, question_text)
            if kind == "ack":
                continue
            # The upgrade may or may not have happened: the stock is unknown
            # until the next $tu or game result.
            totals.set_total(SPHERES, None, SOURCE_UPGRADE)
            if kind == "timeout":
                return UpgradeOutcome("stopped", "no ✅ on the Y in time")
            if kind == "refused":
                return UpgradeOutcome("stopped", "the game bot refused the answer (⛔)")
            if looks_like_refusal(reply.text):
                return UpgradeOutcome("stopped", "the game bot refused the upgrade after Y", bot_text=reply.text)
            return UpgradeOutcome("stopped", "unexpected reply after Y", bot_text=reply.text)

    def _addressed_to_self(self, reply: BotReply) -> bool:
        """Ours: a reply to our message, or led by our mention/name; an unaddressed $oic reply counts too."""
        attempt = self._attempt
        text = str(reply.text or "")
        if reply.reference_id is not None:
            return reply.reference_id in attempt.sent_ids
        lead = re.match(r"^\s*(?:\*\*)?<@!?(\d+)>", text)
        if lead:
            return lead.group(1) == attempt.own_id
        if parse_oic_question(text) is not None or parse_not_found(text):
            return True
        bold = re.match(r"^\s*\*\*([^*]+)\*\*\s*,", text)
        named = bold.group(1) if bold else None
        if named is None:
            plain = re.match(r"^\s*([^,\n]{1,80})\s*,", text)
            named = plain.group(1) if plain else None
        return bool(named) and named.strip(" *_`~").casefold() in {name.casefold() for name in attempt.own_names}

    def _is_after_our_messages(self, reply: BotReply) -> bool:
        sent = [value for value in self._attempt.sent_ids if isinstance(value, int)]
        return not (isinstance(reply.message_id, int) and sent and reply.message_id <= max(sent))

    async def _next(self, timeout):
        """The next relevant event: ("reply", BotReply) / ("ack"|"refused", id) / ("timeout", None)."""
        deadline = self._monotonic() + timeout
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return "timeout", None
            try:
                kind, payload = await asyncio.wait_for(self._queue.get(), timeout=min(remaining, 0.5))
            except asyncio.TimeoutError:
                continue
            if kind in ("ack", "refused"):
                if payload in self._attempt.sent_ids:
                    return kind, payload
                continue
            reply = payload
            if not self._is_after_our_messages(reply) or not self._addressed_to_self(reply):
                continue
            return "reply", reply

    async def _answer_no_if_open(self, channel):
        attempt = self._attempt
        if attempt is None or not attempt.question_open:
            return
        attempt.question_open = False
        try:
            await self._send(channel, "n")
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    def _finish(self, outcome: UpgradeOutcome):
        bot_text = (" Bot said: «{}»".format(outcome.bot_text.strip()[:300])
                    if outcome.bot_text and outcome.status != "upgraded" else "")
        if outcome.status == "upgraded":
            self._failures = 0
            self._retry_at = None
            self.store.put(self.key, STATE_SECTION_EMPTY, None)
            names = ", ".join(outcome.names)
            if len(names) > 600:
                names = names[:600] + "…"
            line = "Perk 10: upgraded {} character(s) for {:,} spheres ({} today): {}".format(
                outcome.characters, outcome.cost, self.upgrades_today(), names)
            if outcome.reason:
                line += " — " + outcome.reason
            self.status = "Perk 10: upgraded {} character(s) for {:,} spheres.".format(outcome.characters, outcome.cost)
            self._log(line + ".", "SUCCESS")
        elif outcome.status == "empty":
            self._failures = 0
            self._retry_at = None
            self._record_empty(outcome.reason)
            self.status = "Perk 10: {}; next check in 6 h.".format(outcome.reason)
            self._log("Perk 10: {}; the list is checked again in 6 hours at the earliest.".format(outcome.reason), "INFO")
        elif outcome.status == "stopped":
            self._failures += 1
            step = self.backoff_steps[min(self._failures, len(self.backoff_steps)) - 1]
            self._retry_at = self._monotonic() + step
            self.status = "Perk 10 stopped: {}. Next try in {} min.".format(outcome.reason, int(step // 60))
            self._log(self.status + bot_text, "WARN")
