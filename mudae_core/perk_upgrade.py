"""Automatic perk-10 upgrade: spend spheres on ``$oic name $ name $ … $ 10``.

Order of work: first every sphere game the latest ``$tu`` shows as available
is played out by the existing sphere automation; an upgrade never starts while
a game is available or running, or while the account is busy rolling or
claiming. The sphere stock is the running one (the «(Stock: N)» of the last
game result when newer, else the latest ``$tu``); no extra ``$tu`` is ever
sent, so an unknown stock waits for the next one. With a stock of at least the
minimum (default 2,000), floor(stock / 1,000) characters are upgraded
(10,000 → 10), capped by the maximum and by the names ``$mmz-`` lists (the
characters without the upgrade). An optional amount (``perk10_amount``, 0 =
off) upgrades exactly that many once the minimum is reached, or what the stock
affords when that is fewer.

Flow (game bot replies as seen on a live account):

    account: $mmz-                       (read once; pages turned with its buttons)
    account: $oic Name One $ Name Two $ … $ 10      (one name: $oi Name $ 10)
    bot:     «Do you really want to spend 10,000 <sphere> for 10 characters? (y/n/yes/no)»
             [… «Characters not found: name a, name b»]
    account: Y      (only when count = names sent − not found, cost = count × 1,000 and cost ≤ stock; else n)
    bot:     ✅ reaction on the account's command (or on its «Y»)

A long name list is split into several commands (each under 1,900
characters, each ending «$ 10»), each finished before the next. Names the bot
reports «not found» are remembered for this account and skipped next time.
Any other outcome stops cleanly (answers n while the question is open), logs
the bot's text and backs off with growing delays. One upgrade at a time, at
most N per day; an empty ``$mmz-`` is re-checked at most once per 6 hours.
The memory, the daily count and the back-off live in this object (one per
account) and start fresh when the bot restarts.
"""

import asyncio
import datetime
import random
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

from .harem_list import HaremListReader, has_visible_text, strip_invisible
from .sphere_stock import NUMBER, is_sphere_emoji, parse_amount
from .spheres import SPHERE_GAME_KINDS

PERK10_DEFAULTS = {
    "auto_perk10": False,
    "perk10_min_spheres": 2000,
    "perk10_max_characters": 100,  # 0: no limit
    "perk10_amount": 0,  # 0: as many characters as the spheres allow
    "perk10_daily_cap": 3,
}
PERK10_COST = 1000  # spheres per character for perk 10
PERK_NUMBER = 10
MIN_SPHERES_MIN = PERK10_COST
MIN_SPHERES_MAX = 1_000_000_000
MAX_CHARACTERS_MAX = 10_000
DAILY_CAP_MAX = 50
AMOUNT_MAX = 10_000
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
BACKOFF_STEPS_SECONDS = (600.0, 1800.0, 3600.0, 10800.0, 21600.0)

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
_YES_NO = re.compile(r"y\s*/\s*n|yes\s*/\s*no", re.IGNORECASE)
_SPEND_RE = re.compile(r"\bspend\s+\**\s*(?P<cost>" + NUMBER + r")", re.IGNORECASE)
_COST_EMOJI_RE = re.compile(r"\**(?P<cost>" + NUMBER + r")\**\s*" + _EMOJI)
_COUNT_RE = re.compile(r"\bfor\s+\**\s*(?P<count>" + NUMBER + r")\s*\**\s*characters?", re.IGNORECASE)
_REFUSAL_WORDS = (
    "not enough", "don't have enough", "do not have enough", "you don't have", "you do not have",
    "can't", "cannot", "not allowed", "procedure has been stopped", "invalid", "insuficiente", "no tienes",
    "no character found", "syntax:",
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


_LIMITS = (
    ("perk10_min_spheres", MIN_SPHERES_MIN, MIN_SPHERES_MAX),
    ("perk10_max_characters", 0, MAX_CHARACTERS_MAX),
    ("perk10_amount", 0, AMOUNT_MAX),
    ("perk10_daily_cap", 1, DAILY_CAP_MAX),
)


@dataclass(frozen=True)
class Perk10Settings:
    enabled: bool = False
    min_spheres: int = 2000
    max_characters: int = 100  # 0: no limit
    amount: int = 0  # 0: as many as the spheres allow
    daily_cap: int = 3

    @classmethod
    def from_preset(cls, data):
        data = data or {}

        def number(key, minimum, maximum):
            found = _whole(data.get(key), PERK10_DEFAULTS[key], minimum, maximum)
            return PERK10_DEFAULTS[key] if found is None else found

        values = {key: number(key, minimum, maximum) for key, minimum, maximum in _LIMITS}
        return cls(
            enabled=bool(data.get("auto_perk10", False)),
            min_spheres=values["perk10_min_spheres"],
            max_characters=values["perk10_max_characters"],
            amount=values["perk10_amount"],
            daily_cap=values["perk10_daily_cap"],
        )


def validate_perk10_settings(data):
    """Preset validation errors for the perk-10 settings (empty when valid)."""
    data = data or {}
    errors = []
    for key, minimum, maximum in _LIMITS:
        if _whole(data.get(key, PERK10_DEFAULTS[key]), PERK10_DEFAULTS[key], minimum, maximum) is None:
            errors.append("{} must be a whole number from {:,} to {:,}.".format(key, minimum, maximum))
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

    ``counts`` are the uses left per game as the sphere automation tracks them
    (set from ``$tu``, lowered as boards start); ``enabled`` says which games
    it plays. A game that is not automated is not waited for (it would never be
    played).
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
    """A listed name can go into the command whole (no «$», which separates names; something visible in it)."""
    text = strip_invisible(name)
    return (bool(text) and has_visible_text(text) and "$" not in text and "\n" not in text
            and len(text) < COMMAND_LENGTH_LIMIT - 20)


def names_problem(names) -> Optional[str]:
    """Why a command with these names must not be sent (None: fine): none, or one that prints as nothing."""
    names = list(names or ())
    if not names:
        return "the command would carry no name"
    for name in names:
        if not isinstance(name, str) or not name.strip() or not usable_name(name):
            return "a name is empty or prints as nothing ({!r})".format(name)
    return None


def command_for(chunk: Sequence[str], prefix="$") -> str:
    """One name: «$oi Name $ 10»; two or more: «$oic A $ B $ 10»."""
    prefix = prefix or "$"
    names = [strip_invisible(name) for name in chunk]
    problem = names_problem(names)
    if problem:
        raise ValueError(problem)
    verb = "oi" if len(names) == 1 else "oic"
    return "{}{} {} $ {}".format(prefix, verb, " $ ".join(names), PERK_NUMBER)


def build_commands(names: Sequence[str], prefix="$", limit=COMMAND_LENGTH_LIMIT) -> List[Tuple[str, Tuple[str, ...]]]:
    """``[(command, names_in_it), …]``, each command shorter than ``limit``.

    Raises ValueError when any name is empty or prints as nothing (never builds «$oic  $ 10»).
    """
    prefix = prefix or "$"
    clean = [strip_invisible(name) for name in names]
    problem = names_problem(clean) if clean else None
    if problem:
        raise ValueError(problem)
    head = "{}oic ".format(prefix)
    tail = " $ {}".format(PERK_NUMBER)
    chunks: List[List[str]] = []
    chunk: List[str] = []
    for name in clean:
        trial = head + " $ ".join(chunk + [name]) + tail
        if chunk and len(trial) >= limit:
            chunks.append(chunk)
            chunk = [name]
        else:
            chunk.append(name)
    if chunk:
        chunks.append(chunk)
    commands = [(command_for(item, prefix), tuple(item)) for item in chunks]
    return [item for item in commands if len(item[0]) < limit]


@dataclass(frozen=True)
class OicQuestion:
    cost: int
    count: int


def parse_oic_question(text) -> Optional[OicQuestion]:
    """«Do you really want to spend 10,000 <sphere> for 10 characters? (y/n/yes/no)»."""
    folded = str(text or "")
    if not _YES_NO.search(folded):
        return None
    match = _QUESTION_RE.search(folded)
    if not match:
        return None
    name = match.group("raw") or match.group("rendered")
    if name and not is_sphere_emoji(name):
        return None
    cost = parse_amount(match.group("cost"))
    count = parse_amount(match.group("count"))
    if cost is None or count is None:
        return None
    return OicQuestion(cost=cost, count=count)


def parse_oi_question(text, name="", own_names=()) -> Optional[OicQuestion]:
    """The y/n question for ONE character (``$oi``). Assumed shape: its wording has not been seen live.

    Accepted when the text is a y/n question that states a cost of exactly 1,000, says «1 character» when
    it states a count, and, when it names a character in bold, names ours (normalised). Else None.
    """
    folded = str(text or "")
    if not _YES_NO.search(folded):
        return None
    found = _SPEND_RE.search(folded) or _COST_EMOJI_RE.search(folded)
    if not found or parse_amount(found.group("cost")) != PERK10_COST:
        return None
    counted = _COUNT_RE.search(folded)
    if counted and parse_amount(counted.group("count")) != 1:
        return None
    ours = normalize_name(name)
    mine = {normalize_name(item) for item in own_names or ()}
    for bold in re.findall(r"\*\*([^*\n]+)\*\*", folded):
        said = normalize_name(bold)
        if not said or re.fullmatch(r"[\d.,\s]+", said) or said in mine or said in ("y", "n", "yes", "no"):
            continue
        if ours and said != ours:
            return None
    return OicQuestion(cost=PERK10_COST, count=1)


def parse_not_found(text) -> Tuple[str, ...]:
    """«Characters not found: satanichia mcdowell, kurumizawa» → the names as printed."""
    found = []
    for match in _NOT_FOUND_RE.finditer(str(text or "")):
        for part in match.group("names").split(","):
            part = part.strip().strip("*_` ").strip()
            if part:
                found.append(part)
    return tuple(found)


def looks_like_oi_syntax_error(text) -> bool:
    """«No character found!  Syntax: $oi <character> $ <perk(s) number to upgrade>»."""
    folded = str(text or "").casefold()
    return "no character found" in folded or "syntax: $oi" in folded


def looks_like_refusal(text) -> bool:
    folded = str(text or "").casefold()
    return any(word in folded for word in _REFUSAL_WORDS)


# ---------------------------------------------------------------------------
# The upgrader
# ---------------------------------------------------------------------------

@dataclass
class BotReply:
    """A game-bot message as the flow needs it."""
    message_id: object
    channel_id: object
    text: str
    reference_id: object = None


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
    listed: str = ""  # what $mmz- returned (shortened), for the ERROR log of a refused command


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class PerkUpgrader:
    """One per account.

    ``send(channel, text)`` returns the sent message (or None/False);
    ``click(button)`` turns ``$mmz-`` pages; ``wait(seconds)`` is the bot's
    interruptible delay (False when paused/stopping).
    """

    def __init__(self, *, send, click, wait, log, clock=_now, monotonic=time.monotonic,
                 question_timeout=QUESTION_TIMEOUT_SECONDS, ack_timeout=ACK_TIMEOUT_SECONDS,
                 followup_timeout=FOLLOWUP_TIMEOUT_SECONDS, backoff_steps=BACKOFF_STEPS_SECONDS,
                 answer_delay=(1.1, 2.6), between_commands=(2.0, 4.0), reader=None):
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
        self._upgrades = (None, 0)  # (day, count)
        self._not_found: List[str] = []
        self._empty_at: Optional[datetime.datetime] = None

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
        """The game bot put ✅ on a message (on the account's command or «Y»: success)."""
        if self._attempt is not None and self._queue is not None:
            self._queue.put_nowait(("ack", message_id))

    def on_refused(self, message_id):
        if self._attempt is not None and self._queue is not None:
            self._queue.put_nowait(("refused", message_id))

    # -- per-account memory ----------------------------------------------
    def today(self):
        return self._clock().date()

    def upgrades_today(self) -> int:
        day, count = self._upgrades
        return count if day == self.today() else 0

    def _count_upgrade(self) -> int:
        count = self.upgrades_today() + 1
        self._upgrades = (self.today(), count)
        return count

    def not_found_names(self) -> Tuple[str, ...]:
        return tuple(self._not_found)

    def _remember_not_found(self, names):
        for name in names:
            folded = normalize_name(name)
            if folded and folded not in self._not_found:
                self._not_found.append(folded)
        del self._not_found[:-NOT_FOUND_MEMORY_MAX]

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
        if self._empty_at is not None:
            next_check = self._empty_at + datetime.timedelta(seconds=EMPTY_RECHECK_SECONDS)
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

    async def maybe_upgrade(self, channel, settings: Perk10Settings, *, own_id, own_names, stock, prefix="$",
                            games: Callable[[], Optional[str]] = lambda: None,
                            busy: Callable[[], Optional[str]] = lambda: None) -> UpgradeOutcome:
        """One upgrade pass when nothing blocks it; ``stock`` is the account's ``SphereStock``."""
        reason = self.blocker(settings, stock=stock.spheres, games_reason=games(), busy_reason=busy())
        if reason is not None:
            self.status = "Perk 10: off." if reason == "off" else "Perk 10 waits: {}.".format(reason)
            return UpgradeOutcome("skipped", reason)
        self._attempt = _Attempt(
            channel_id=getattr(channel, "id", None), own_id=str(own_id or ""),
            own_names=tuple(str(name) for name in own_names or () if name),
        )
        self._queue = asyncio.Queue()
        try:
            outcome = await self._run(channel, settings, prefix, stock, games, busy)
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

    # -- the flow --------------------------------------------------------
    async def _collect_names(self, channel, count, prefix) -> Tuple[Optional[List[str]], Optional[UpgradeOutcome]]:
        self.state = READING
        read = await self.reader.open(channel, self._attempt.own_names, prefix=prefix)
        if read.status != "ok":
            return None, UpgradeOutcome("stopped", read.reason or "the $mmz- list could not be read")
        skip = set(self._not_found)
        names: List[str] = []
        listed = 0
        seen = set()
        page = read.page
        pages_read = 1
        while True:
            if not self._attempt.listed:
                self._attempt.listed = ", ".join(repr(item) for item in page.names[:20])[:600]
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

    async def _run(self, channel, settings, prefix, stock, games, busy):
        spheres = stock.spheres
        count = upgrade_count(spheres, settings.min_spheres, settings.max_characters, amount=settings.amount)
        if count <= 0:
            return UpgradeOutcome("skipped", "spheres {:,} buy no upgrade".format(spheres or 0))
        names, failed = await self._collect_names(channel, count, prefix)
        if failed is not None:
            return failed
        try:
            commands = build_commands(names, prefix)
        except ValueError as exc:
            self._log("Perk 10: refused to build a command: {}. The list returned: {}.".format(
                exc, self._attempt.listed or "nothing"), "ERROR")
            return UpgradeOutcome("stopped", "no command built: {}".format(exc))
        if not commands:
            return UpgradeOutcome("stopped", "no command could be built from the listed names")
        self._log("Perk 10: spheres {:,} → upgrading {} character(s) in {} command(s).".format(
            spheres, len(names), len(commands)), "INFO")
        done_names: List[str] = []
        done_cost = 0
        for index, (command, chunk) in enumerate(commands):
            if index:
                low, high = self.between_commands
                if not await self._wait(random.uniform(low, high)):
                    return self._partial(done_names, done_cost, "paused or stopping between commands")
                reason = busy() or games()
                if reason:
                    return self._partial(done_names, done_cost, "became busy ({}) between commands".format(reason))
            known = stock.spheres
            if known is None or known < len(chunk) * PERK10_COST:
                return self._partial(done_names, done_cost, "the sphere stock ({}) does not cover {} character(s)".format(
                    "unknown" if known is None else "{:,}".format(known), len(chunk)))
            result = await self._one_command(channel, command, chunk, stock, busy)
            if result.status != "upgraded":
                if done_names:
                    result.reason += " (after {} character(s) already upgraded)".format(len(done_names))
                    result.characters, result.cost = len(done_names), done_cost
                    result.names = tuple(done_names)
                return result
            done_names.extend(result.names)
            done_cost += result.cost
        return UpgradeOutcome("upgraded", "", len(done_names), done_cost, tuple(done_names))

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

    async def _one_command(self, channel, command, chunk, stock, busy) -> UpgradeOutcome:
        attempt = self._attempt
        attempt.sent_ids.clear()
        # Last check before anything is sent: every name prints as something and the command matches them.
        problem = names_problem(chunk)
        if problem is None and command != command_for(chunk, command.split("oi", 1)[0] or "$"):
            problem = "the command does not match its names"
        if problem is not None:
            self._log("Perk 10: refused to send {!r}: {}. The list returned: {}.".format(
                command, problem, attempt.listed or "nothing"), "ERROR")
            return UpgradeOutcome("stopped", "not sent: " + problem)
        single = len(chunk) == 1
        verb = "$oi" if single else "$oic"
        self.state = SENDING
        sent_command = await self._send_tracked(channel, command)
        if not sent_command:
            return UpgradeOutcome("stopped", "the {} command could not be sent".format(verb))
        command_id = getattr(sent_command, "id", None)

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
            question = parse_oic_question(text)  # the same question for one or many characters
            if question is None and single:
                question = parse_oi_question(text, chunk[0], attempt.own_names)  # tolerant fallback
            if question is not None:
                question_text = text
                break
            if single and not missing and _YES_NO.search(str(text or "")):
                # A question for one character that does not state exactly 1,000 for ours: never answered Y.
                attempt.question_open = True
                await self._answer_no_if_open(channel)
                self._log("Perk 10: the $oi question was not recognised ({}); answered n. Bot said: «{}»".format(
                    chunk[0], str(text).strip()[:300]), "ERROR")
                return UpgradeOutcome("stopped", "the question for one character was not recognised; answered n",
                                      bot_text=text)
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
        spheres = stock.spheres
        problem = None
        if question.count != expected:
            problem = "the bot asked about {} character(s), expected {}".format(question.count, expected)
        elif question.cost != question.count * PERK10_COST:
            problem = "the bot asked {:,} spheres for {} character(s), not {:,}".format(
                question.cost, question.count, question.count * PERK10_COST)
        elif spheres is None or question.cost > spheres:
            problem = "the cost {:,} is above the known stock ({})".format(
                question.cost, "unknown" if spheres is None else "{:,}".format(spheres))
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
        self._drop_queued_acks()
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
            # The live run put the ✅ on the $oic COMMAND message; a ✅ on our Y counts too. This loop starts
            # only after Y was answered, so an earlier ✅ (dropped above) never counts.
            if kind == "ack" and (answer_id is None or reply in (answer_id, command_id)):
                stock.spend(question.cost)
                return UpgradeOutcome("upgraded", "", question.count, question.cost, upgraded, question_text)
            if kind == "ack":
                continue
            # The upgrade may or may not have happened: the stock is unknown
            # until the next $tu or game result.
            stock.set(None)
            if kind == "timeout":
                return UpgradeOutcome("stopped", "no ✅ on the command or the Y in time")
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
        if parse_oic_question(text) is not None or parse_not_found(text) or looks_like_oi_syntax_error(text) \
                or re.search(r"do you really want to spend", text, re.IGNORECASE):
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

    def _drop_queued_acks(self):
        """Forget ✅ events that arrived before we answered (they cannot be the result of the answer)."""
        queue = self._queue
        if queue is None:
            return
        kept = []
        while True:
            try:
                item = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item[0] != "ack":
                kept.append(item)
        for item in kept:
            queue.put_nowait(item)

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
            self._empty_at = None
            names = ", ".join(outcome.names)
            if len(names) > 600:
                names = names[:600] + "…"
            line = "Perk 10: upgraded {} character(s) for {:,} spheres ({} today): {}".format(
                outcome.characters, outcome.cost, self.upgrades_today(), names)
            if outcome.reason:
                line += " — " + outcome.reason
            self.status = "Perk 10: upgraded {} character(s) for {:,} spheres.".format(outcome.characters, outcome.cost)
            self._log(line + ".", "INFO")
        elif outcome.status == "empty":
            self._failures = 0
            self._retry_at = None
            self._empty_at = self._clock()
            self.status = "Perk 10: {}; next check in 6 h.".format(outcome.reason)
            self._log("Perk 10: {}; the list is checked again in 6 hours at the earliest.".format(outcome.reason), "INFO")
        elif outcome.status == "stopped":
            self._failures += 1
            step = self.backoff_steps[min(self._failures, len(self.backoff_steps)) - 1]
            self._retry_at = self._monotonic() + step
            self.status = "Perk 10 stopped: {}. Next try in {} min.".format(outcome.reason, int(step // 60))
            self._log(self.status + bot_text, "WARN")
