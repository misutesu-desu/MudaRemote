"""Auto-give harem pages from a SIDE account to its Main (``$give <@MAIN_ID>``).

Two accounts act (the game bot's replies as transcribed from the owner's samples):

    side:  $give <@MAIN_ID>
    bot:   «<@side>, Who do you want to give to <@main> ?»
    side:  Page 1 2 3
    bot:   «<@main>, <side name> wants to give you Harem page(s) n°1… Do you confirm? (y/n/yes/no)»
           [+ «(Enhanced multitrade: this gift is free)»]
    MAIN:  y          (only when the giver, the pages and the free/known shape check out, else n)
    bot:   «Harem page(s) n°… given to <@main>»

The side drives the flow and reads every bot reply; the Main only answers,
through a small partner handle the bot glue builds from the running Main
account (both must run in this process). Every stop leaves nothing open: the
Main answers ``n`` to an open confirmation, and the side sends ``$exit`` for a
procedure of its own that is still open («The procedure has been stopped.»).

When to give (one trigger, read on its own modest schedule, never ``$tu``):
pages (``$mm`` footer N), characters (``$mmi`` footer TOTAL) or harem value
(``$mmrk`` «Total value»). What to give: «Pages to give» (default: every page
up to X), minus «Keep the first N pages». A long page list is given in several
rounds and ``$mm`` is re-read between rounds (given pages shift the rest).
"""

import asyncio
import datetime
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

from .harem_list import LIST_MM, LIST_MMI, LIST_MMRK, HaremListReader, clean_line
from .kakera_give import BACKOFF_STEPS_SECONDS, BotReply, GiveOutcome

TRIGGER_PAGES = "pages"
TRIGGER_CHARACTERS = "characters"
TRIGGER_VALUE = "value"
TRIGGERS = (TRIGGER_PAGES, TRIGGER_CHARACTERS, TRIGGER_VALUE)
TRIGGER_COMMANDS = {TRIGGER_PAGES: LIST_MM, TRIGGER_CHARACTERS: LIST_MMI, TRIGGER_VALUE: LIST_MMRK}

HAREM_GIVE_DEFAULTS = {
    "auto_give_harem": False,
    "harem_give_trigger": TRIGGER_PAGES,
    "harem_give_pages": 10,
    "harem_give_characters": 150,
    "harem_give_value": 100000,
    "harem_check_hours": 6,
    "harem_give_pages_text": "",
    "harem_keep_first_pages": 0,
    "harem_give_daily_cap": 1,
}
PAGES_MAX = 100_000
CHARACTERS_MAX = 10_000_000
VALUE_MAX = 10_000_000_000
CHECK_HOURS_MAX = 168
DAILY_CAP_MAX = 20
# A Discord message holds 2,000 characters; «Page 1 2 3 …» stays well below.
MAX_ROUND_MESSAGE_LENGTH = 1900
STEP_TIMEOUT_SECONDS = 20.0

IDLE = "idle"
CHECKING = "checking the harem"
GIVING = "asking to give"
CHOOSING = "naming the pages"
CONFIRMING = "main confirming"
AWAITING_DONE = "awaiting the result"

STATE_SECTION_CHECK = "harem_check"
STATE_SECTION_GIVES = "harem_gives"

_MENTION = r"<@!?(?P<{}>\d+)>"
_WHO_RE = re.compile(_MENTION.format("giver") + r"\s*,?\s*who do you want to give to\s*" + _MENTION.format("receiver"),
                     re.IGNORECASE)
_PAGES_WORD = r"harem\s+pages?(?:\s*\(s\))?\s*"
_CONFIRM_RE = re.compile(
    r"^\s*" + _MENTION.format("receiver") + r"\s*,\s*(?P<giver>.+?)\s+wants to give you\s+" + _PAGES_WORD
    + r"(?P<pages>(?:n\s*[°º]\s*|#)?\d+(?:\s*(?:,|&|and|et|\s)\s*(?:n\s*[°º]\s*|#)?\d+)*)\s*[.!]?\s*"
    r"do you confirm\s*\?\s*\(\s*y\s*/\s*n\s*/\s*yes\s*/\s*no\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_FREE_RE = re.compile(r"\(\s*enhanced multitrade\s*:\s*this gift is free\s*\)", re.IGNORECASE)
_DONE_RE = re.compile(
    _PAGES_WORD + r"(?P<pages>(?:n\s*[°º]\s*|#)?\d+(?:\s*(?:,|&|and|et|\s)\s*(?:n\s*[°º]\s*|#)?\d+)*)\s*[.!]?\s*given to\s*"
    + _MENTION.format("receiver"),
    re.IGNORECASE,
)
_STOPPED_RE = re.compile(r"procedure has been stopped", re.IGNORECASE)


def _plain(text) -> str:
    return str(text or "").replace("**", "").replace("__", "")


# ---------------------------------------------------------------------------
# Parsing the bot's replies
# ---------------------------------------------------------------------------

def parse_who_question(text) -> Optional[Tuple[str, str]]:
    """«<@giver>, Who do you want to give to <@receiver> ?» → (giver id, receiver id)."""
    match = _WHO_RE.search(_plain(text))
    return (match.group("giver"), match.group("receiver")) if match else None


@dataclass(frozen=True)
class GiftQuestion:
    receiver_id: str
    giver_name: str
    pages: Tuple[int, ...]
    free: bool
    extra: str  # anything else in the message (a cost, a warning, …)


def parse_gift_question(text) -> Optional[GiftQuestion]:
    plain = _plain(text)
    match = _CONFIRM_RE.search(plain)
    if not match:
        return None
    rest = plain[:match.start()] + plain[match.end():]
    free = bool(_FREE_RE.search(rest))
    rest = _FREE_RE.sub("", rest)
    rest = re.sub(r"\s+", " ", rest).strip(" *_~`.")
    pages = tuple(int(value) for value in re.findall(r"\d+", match.group("pages")))
    return GiftQuestion(match.group("receiver"), clean_line(match.group("giver")).strip(" *_`~"), pages, free, rest)


def parse_gift_done(text) -> Optional[Tuple[Tuple[int, ...], str]]:
    """«Harem page(s) n°1 given to <@main>» → ((1,), main id)."""
    match = _DONE_RE.search(_plain(text))
    if not match:
        return None
    return tuple(int(value) for value in re.findall(r"\d+", match.group("pages"))), match.group("receiver")


def check_gift_question(question: GiftQuestion, *, main_id, giver_names, pages) -> Optional[str]:
    """Why the Main must answer n (None: the question is the intended one)."""
    if str(question.receiver_id) != str(main_id):
        return "the question is addressed to another account"
    names = {clean_line(name).casefold() for name in giver_names or () if name}
    if question.giver_name.casefold() not in names:
        return "the giver named in the question ({}) is not this side account".format(question.giver_name)
    if sorted(set(question.pages)) != sorted(set(pages)):
        return "the question names page(s) {} instead of {}".format(
            " ".join(map(str, question.pages)) or "?", " ".join(map(str, pages)))
    if question.extra:
        return "the bot's question does not have the expected free shape (it says: {})".format(question.extra[:200])
    return None


# ---------------------------------------------------------------------------
# Settings, triggers, page selection
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
class PageSelection:
    kind: str  # "default", "first", "list"
    count: int = 0
    pages: Tuple[int, ...] = ()


def parse_page_selection(text) -> PageSelection:
    """«» / «all» → default; «3» → the first 3 pages; «1-3», «2 4 5», «2,4-6» → those pages.

    Raises ValueError with a readable message for anything else.
    """
    value = str(text or "").strip()
    if not value or value.casefold() in {"all", "default"}:
        return PageSelection("default")
    tokens = [token for token in re.split(r"[\s,;]+", value) if token]
    if len(tokens) == 1 and tokens[0].isdigit():
        count = int(tokens[0])
        if count < 1:
            raise ValueError("«Pages to give»: the number of pages must be at least 1.")
        return PageSelection("first", count=count)
    pages = set()
    for token in tokens:
        span = re.fullmatch(r"(\d+)\s*-\s*(\d+)", token)
        if span:
            low, high = int(span.group(1)), int(span.group(2))
            if low < 1 or high < low:
                raise ValueError("«Pages to give»: «{}» is not a valid range.".format(token))
            if high - low > PAGES_MAX:
                raise ValueError("«Pages to give»: «{}» is too long.".format(token))
            pages.update(range(low, high + 1))
        elif token.isdigit() and int(token) >= 1:
            pages.add(int(token))
        else:
            raise ValueError("«Pages to give»: «{}» is not a page number or a range like 1-3.".format(token))
    return PageSelection("list", pages=tuple(sorted(pages)))


def resolve_pages(selection: PageSelection, page_count, *, up_to=None, keep_first=0) -> List[int]:
    """The page numbers to give now, validated against the current page count."""
    if not page_count or page_count < 1:
        return []
    if selection.kind == "default":
        wanted = range(1, min(page_count, up_to or page_count) + 1)
    elif selection.kind == "first":
        wanted = range(1, min(page_count, selection.count) + 1)
    else:
        wanted = [page for page in selection.pages if page <= page_count]
    keep = max(0, int(keep_first or 0))
    return [page for page in wanted if page > keep]


def split_rounds(pages: Sequence[int], max_length=MAX_ROUND_MESSAGE_LENGTH) -> List[List[int]]:
    """«Page 1 2 3 …» messages short enough for one Discord message each."""
    rounds, current = [], []
    for page in pages:
        candidate = current + [page]
        if current and len(round_message(candidate)) > max_length:
            rounds.append(current)
            candidate = [page]
        current = candidate
    if current:
        rounds.append(current)
    return rounds


def round_message(pages: Sequence[int]) -> str:
    return "Page " + " ".join(str(page) for page in pages)


def renumber_after_give(pages: Sequence[int], given: Sequence[int]) -> List[int]:
    """Pages still to give, renumbered after ``given`` left the harem."""
    given = sorted(set(given))
    return [page - sum(1 for g in given if g < page) for page in pages if page not in given]


@dataclass(frozen=True)
class HaremGiveSettings:
    enabled: bool = False
    trigger: str = TRIGGER_PAGES
    pages: int = 10
    characters: int = 150
    value: int = 100000
    check_hours: int = 6
    selection: PageSelection = PageSelection("default")
    keep_first: int = 0
    daily_cap: int = 1

    @classmethod
    def from_preset(cls, data):
        data = data or {}
        defaults = HAREM_GIVE_DEFAULTS

        def number(key, minimum, maximum):
            found = _whole(data.get(key), defaults[key], minimum, maximum)
            return defaults[key] if found is None else found

        trigger = str(data.get("harem_give_trigger") or TRIGGER_PAGES).strip().casefold()
        try:
            selection = parse_page_selection(data.get("harem_give_pages_text", ""))
        except ValueError:
            selection = PageSelection("default")
        return cls(
            enabled=bool(data.get("auto_give_harem", False)),
            trigger=trigger if trigger in TRIGGERS else TRIGGER_PAGES,
            pages=number("harem_give_pages", 1, PAGES_MAX),
            characters=number("harem_give_characters", 1, CHARACTERS_MAX),
            value=number("harem_give_value", 1, VALUE_MAX),
            check_hours=number("harem_check_hours", 1, CHECK_HOURS_MAX),
            selection=selection,
            keep_first=number("harem_keep_first_pages", 0, PAGES_MAX),
            daily_cap=number("harem_give_daily_cap", 1, DAILY_CAP_MAX),
        )

    @property
    def threshold(self) -> int:
        return {TRIGGER_PAGES: self.pages, TRIGGER_CHARACTERS: self.characters, TRIGGER_VALUE: self.value}[self.trigger]

    @property
    def check_command(self) -> str:
        return TRIGGER_COMMANDS[self.trigger]


def validate_harem_give_settings(data):
    data = data or {}
    errors = []
    trigger = str(data.get("harem_give_trigger", TRIGGER_PAGES) or TRIGGER_PAGES).strip().casefold()
    if trigger not in TRIGGERS:
        errors.append("«Give when my harem reaches» must be pages, characters or value.")
    checks = (
        ("harem_give_pages", "Give when my harem reaches X pages", 1, PAGES_MAX),
        ("harem_give_characters", "Give when my harem reaches X characters", 1, CHARACTERS_MAX),
        ("harem_give_value", "Give when my harem value reaches X", 1, VALUE_MAX),
        ("harem_check_hours", "Check every N hours", 1, CHECK_HOURS_MAX),
        ("harem_keep_first_pages", "Keep the first N pages", 0, PAGES_MAX),
        ("harem_give_daily_cap", "At most N harem gives per day", 1, DAILY_CAP_MAX),
    )
    for key, label, minimum, maximum in checks:
        if _whole(data.get(key, HAREM_GIVE_DEFAULTS[key]), HAREM_GIVE_DEFAULTS[key], minimum, maximum) is None:
            errors.append("«{}» must be a whole number from {} to {:,}.".format(label, minimum, maximum))
    try:
        parse_page_selection(data.get("harem_give_pages_text", ""))
    except ValueError as error:
        errors.append(str(error))
    return errors


def trigger_reading(settings: HaremGiveSettings, page) -> Optional[int]:
    """The number the trigger compares with X, read from the check list's first page."""
    if page is None:
        return None
    if settings.trigger == TRIGGER_VALUE:
        return page.total_value
    return page.pages  # $mm: pages; $mmi: number of characters


def _trigger_words(settings: HaremGiveSettings, reading) -> str:
    unit = {TRIGGER_PAGES: "pages", TRIGGER_CHARACTERS: "characters", TRIGGER_VALUE: "value"}[settings.trigger]
    if settings.trigger == TRIGGER_VALUE:
        return "harem value {:,}".format(reading)
    return "{:,} {}".format(reading, unit)


# ---------------------------------------------------------------------------
# One give at a time per Main (a Main can only answer one question at a time)
# ---------------------------------------------------------------------------

_pairs_lock = threading.Lock()
_busy_mains = set()


def _claim_main(main_key) -> bool:
    with _pairs_lock:
        if main_key in _busy_mains:
            return False
        _busy_mains.add(main_key)
        return True


def _release_main(main_key):
    with _pairs_lock:
        _busy_mains.discard(main_key)


def main_receiving(main_key) -> bool:
    with _pairs_lock:
        return main_key in _busy_mains


# Key farming mode: the main's own rolls hold only while it answers «y»
# (mudae_core.main_alt_coop.receiver_holds_rolls), not for the whole give.
_confirming_mains = set()


def _set_confirming(main_key, on):
    with _pairs_lock:
        if on:
            _confirming_mains.add(main_key)
        else:
            _confirming_mains.discard(main_key)


def main_confirming(main_key) -> bool:
    with _pairs_lock:
        return main_key in _confirming_mains


# ---------------------------------------------------------------------------
# The flow
# ---------------------------------------------------------------------------

def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class _Stop(Exception):
    def __init__(self, reason, bot_text=""):
        super().__init__(reason)
        self.reason = reason
        self.bot_text = bot_text


@dataclass
class _Attempt:
    channel_id: object
    main_id: str
    own_id: str
    own_names: Tuple[str, ...]
    sent_ids: set = field(default_factory=set)
    open: Optional[str] = None  # None, "giver" (a procedure of ours) or "receiver" (the Main's question)
    rounds_done: int = 0
    counted: bool = False
    pages_given: List[int] = field(default_factory=list)


class HaremGiver:
    """One per side account.

    ``partner`` (the running Main, built by the glue) exposes ``key``, ``name``,
    ``user_id``, ``busy_reason()`` and ``async answer(channel_id, text)``
    (returns the sent message or None). ``send``/``click``/``wait`` are the side's
    own helpers.
    """

    def __init__(self, *, key, store, send, click, wait, log, clock=_now, monotonic=time.monotonic,
                 step_timeout=STEP_TIMEOUT_SECONDS, backoff_steps=BACKOFF_STEPS_SECONDS,
                 answer_delay=(1.1, 2.6), reader=None):
        self.key = key
        self.store = store
        self._send = send
        self._wait = wait
        self._log = log
        self._clock = clock
        self._monotonic = monotonic
        self.step_timeout = step_timeout
        self.backoff_steps = tuple(backoff_steps)
        self.answer_delay = answer_delay
        self.reader = reader or HaremListReader(send=send, click=click, wait=wait, log=log, monotonic=monotonic)
        self.state = IDLE
        self.status = "Harem give: idle."
        self.last_reading = None
        self._failures = 0
        self._retry_at = None
        self._attempt: Optional[_Attempt] = None
        self._queue: Optional[asyncio.Queue] = None

    # -- feeding replies -------------------------------------------------
    @property
    def active(self) -> bool:
        return self._attempt is not None or self.state != IDLE

    def on_message(self, message, text):
        """Every bot message in the side's channels: list replies and procedure replies."""
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

    def on_reply(self, reply: BotReply):
        if self._attempt is not None and self._queue is not None and reply.channel_id == self._attempt.channel_id:
            self._queue.put_nowait(("reply", reply))

    def on_edit(self, message):
        self.reader.on_edit(message)

    def on_refused(self, message_id):
        if self._attempt is not None and self._queue is not None:
            self._queue.put_nowait(("refused", message_id))

    def user_answered(self) -> bool:
        """The player answered the game bot's open question by hand: this flow never
        answers or cancels it itself (it stops at its next busy check). True when a
        question of ours was open."""
        attempt = self._attempt
        if attempt is None or attempt.open is None:
            return False
        attempt.open = None
        return True

    # -- schedule --------------------------------------------------------
    def today(self):
        return self._clock().date()

    def last_check(self) -> Optional[datetime.datetime]:
        record = self.store.get(self.key, STATE_SECTION_CHECK) or {}
        try:
            return datetime.datetime.fromisoformat(record.get("at"))
        except (TypeError, ValueError):
            return None

    def next_check_at(self, settings: HaremGiveSettings) -> datetime.datetime:
        last = self.last_check()
        if last is None:
            return self._clock()
        return last + datetime.timedelta(hours=settings.check_hours)

    def _record_check(self, reading):
        self.store.put(self.key, STATE_SECTION_CHECK, {"at": self._clock().isoformat(), "reading": reading})

    def gives_today(self) -> int:
        record = self.store.get(self.key, STATE_SECTION_GIVES) or {}
        return int(record.get("count", 0)) if record.get("day") == self.today().isoformat() else 0

    def _count_give(self) -> int:
        count = self.gives_today() + 1
        self.store.put(self.key, STATE_SECTION_GIVES, {"day": self.today().isoformat(), "count": count})
        return count

    # -- decisions -------------------------------------------------------
    def blocker(self, settings: HaremGiveSettings, *, role, own_id, main_id, partner, busy_reason=None) -> Optional[str]:
        if not settings.enabled:
            return "off"
        if role != "side":
            return "only a side account gives harem pages to its main"
        if not main_id:
            return "the main account is not known (set Main Account ID or pick a Main profile)"
        if own_id and str(main_id) == str(own_id):
            return "the main is this account itself"
        if partner is None:
            return "the main account is not running in this app, so nobody could answer y; no give was started"
        partner_id = getattr(partner, "user_id", None)
        if partner_id is not None and str(partner_id) != str(main_id):
            return "the running main is not the account in Main Account ID"
        if self._attempt is not None or self.state != IDLE:
            return "a harem give is already in progress"
        if busy_reason:
            return "busy: " + busy_reason
        if self._retry_at is not None and self._monotonic() < self._retry_at:
            return "backing off for about {} min after the last failed give".format(
                max(1, int((self._retry_at - self._monotonic()) // 60)))
        if self.gives_today() >= settings.daily_cap:
            return "the daily limit of {} harem give(s) is reached".format(settings.daily_cap)
        due = self.next_check_at(settings)
        if self._clock() < due:
            return "next harem check in about {} min".format(max(1, int((due - self._clock()).total_seconds() // 60)))
        return None

    async def maybe_give(self, channel, settings: HaremGiveSettings, *, role, own_id, own_names, main_id,
                         partner, prefix="$", busy: Callable[[], Optional[str]] = lambda: None) -> GiveOutcome:
        reason = self.blocker(settings, role=role, own_id=own_id, main_id=main_id, partner=partner,
                              busy_reason=busy())
        if reason is not None:
            return GiveOutcome("skipped", reason)
        names = tuple(name for name in own_names or () if name)

        # 1. The check (its own schedule; never $tu).
        self.state = CHECKING
        try:
            read = await self.reader.open(channel, settings.check_command, names, prefix=prefix)
        finally:
            self.state = IDLE
        if read.status != "ok":
            self._record_check(None)
            return self._finish(GiveOutcome("stopped", "the harem check failed: " + read.reason))
        reading = trigger_reading(settings, read.page)
        self.last_reading = reading
        self._record_check(reading)
        if reading is None:
            return self._finish(GiveOutcome("stopped", "the ${} reply had no number to compare".format(settings.check_command)))
        if reading < settings.threshold:
            outcome = GiveOutcome("skipped", "{} is below {:,}".format(_trigger_words(settings, reading), settings.threshold))
            self.status = "Harem give: " + outcome.reason + "."
            self._log("Harem check: " + outcome.reason + ".", "INFO")
            return outcome
        self._log("Harem check: {} reached {:,}; preparing the give.".format(
            _trigger_words(settings, reading), settings.threshold), "INFO")
        partner_busy = getattr(partner, "busy_reason", lambda: None)()
        if partner_busy:
            self._record_check_retry()
            return GiveOutcome("skipped", "the main is busy ({}); the give waits".format(partner_busy))
        if busy():
            self._record_check_retry()
            return GiveOutcome("skipped", "busy: " + busy())
        if not _claim_main(partner.key):
            self._record_check_retry()
            return GiveOutcome("skipped", "the main is receiving another give")

        self._attempt = _Attempt(channel_id=getattr(channel, "id", None), main_id=str(main_id),
                                 own_id=str(own_id or ""), own_names=names)
        self._queue = asyncio.Queue()
        try:
            first_list = read.page if settings.check_command == LIST_MM else None
            outcome = await self._run(channel, settings, partner, prefix, busy, first_list)
        except _Stop as stop:
            await self._cancel_open(channel, partner, prefix)
            outcome = GiveOutcome("stopped", stop.reason, bot_text=stop.bot_text)
        except asyncio.CancelledError:
            await self._cancel_open(channel, partner, prefix)
            raise
        except Exception as exc:
            await self._cancel_open(channel, partner, prefix)
            outcome = GiveOutcome("stopped", "error: {}".format(type(exc).__name__))
        finally:
            attempt = self._attempt
            self._attempt = None
            self._queue = None
            self.state = IDLE
            _set_confirming(partner.key, False)
            _release_main(partner.key)
        if outcome.status == "stopped" and attempt is not None and attempt.rounds_done:
            outcome.reason += " (after {} round(s) that gave page(s) {})".format(
                attempt.rounds_done, " ".join(map(str, attempt.pages_given)))
        return self._finish(outcome)

    def _record_check_retry(self):
        """A met trigger that had to wait: check again soon instead of after the full interval."""
        self.store.put(self.key, STATE_SECTION_CHECK, None)

    # -- the give --------------------------------------------------------
    async def _read_page_count(self, channel, prefix) -> int:
        read = await self.reader.open(channel, LIST_MM, self._attempt.own_names, prefix=prefix)
        if read.status != "ok":
            raise _Stop("could not read $mm: " + read.reason)
        return read.page.pages

    async def _run(self, channel, settings, partner, prefix, busy, first_list):
        attempt = self._attempt
        page_count = first_list.pages if first_list is not None else await self._read_page_count(channel, prefix)
        up_to = settings.pages if settings.trigger == TRIGGER_PAGES else None
        pages = resolve_pages(settings.selection, page_count, up_to=up_to, keep_first=settings.keep_first)
        if not pages:
            return GiveOutcome("skipped", "no page to give (harem has {} page(s), keep first {})".format(
                page_count, settings.keep_first))
        self._log("Harem give: giving page(s) {} of {} to the main {}.".format(
            " ".join(map(str, pages)), page_count, "⁨{}⁩".format(getattr(partner, "name", "main"))), "INFO")
        remaining = list(pages)
        while remaining:
            this_round = split_rounds(remaining)[0]
            if attempt.rounds_done:
                # Pages shifted: re-read the list instead of trusting the numbers.
                if not await self._wait(random.uniform(2.0, 3.5)):
                    raise _Stop("paused or stopping between rounds")
                now_count = await self._read_page_count(channel, prefix)
                if now_count != page_count:
                    raise _Stop("the harem now has {} page(s), expected {}; stopped to avoid giving the wrong pages".format(
                        now_count, page_count))
                if not await self._wait(random.uniform(1.0, 2.0)):
                    raise _Stop("paused or stopping between rounds")
            given = await self._one_round(channel, this_round, partner, prefix, busy)
            attempt.rounds_done += 1
            attempt.pages_given.extend(given)
            page_count -= len(this_round)
            remaining = renumber_after_give(remaining[len(this_round):], this_round)
        return GiveOutcome("given", "gave {} harem page(s) to the main in {} round(s) (give {} today)".format(
            len(attempt.pages_given), attempt.rounds_done, self.gives_today()))

    async def _send_tracked(self, channel, text):
        receipt = await self._send(channel, text)
        if not receipt:
            return False
        message_id = getattr(receipt, "id", None)
        if message_id is not None:
            self._attempt.sent_ids.add(message_id)
        return True

    async def _one_round(self, channel, pages, partner, prefix, busy):
        attempt = self._attempt
        self.state = GIVING
        if not await self._send_tracked(channel, "{}give <@{}>".format(prefix or "$", attempt.main_id)):
            raise _Stop("the $give command could not be sent")
        attempt.open = "giver"
        kind, reply = await self._next(self.step_timeout, expect="who")
        self._expect(kind, reply, "who", "the bot did not ask «Who do you want to give to» in time")

        self.state = CHOOSING
        await self._pause(busy, partner)
        if not await self._send_tracked(channel, round_message(pages)):
            raise _Stop("could not name the pages")
        kind, reply = await self._next(self.step_timeout, expect="confirm")
        self._expect(kind, reply, "confirm", "the bot did not ask the main to confirm in time")
        attempt.open = "receiver"
        question = parse_gift_question(reply.text)
        wrong = check_gift_question(question, main_id=attempt.main_id, giver_names=attempt.own_names, pages=pages)
        if wrong:
            raise _Stop(wrong + "; the main answered n", reply.text)

        self.state = CONFIRMING
        # From the confirm question until the «y» is out, the main's own rolls hold.
        _set_confirming(partner.key, True)
        try:
            await self._pause(busy, partner)
            receipt = await partner.answer(attempt.channel_id, "y")
        finally:
            _set_confirming(partner.key, False)
        if not receipt:
            raise _Stop("the main could not answer y")
        if getattr(receipt, "id", None) is not None:
            attempt.sent_ids.add(receipt.id)
        if not attempt.counted:
            # From the first y on, the give may have happened: it counts toward the daily cap.
            self._count_give()
            attempt.counted = True
        attempt.open = "giver"  # until the result arrives, $exit is the safe cancel

        self.state = AWAITING_DONE
        kind, reply = await self._next(self.step_timeout, expect="done")
        self._expect(kind, reply, "done", "no «given to» confirmation in time")
        done_pages, receiver = parse_gift_done(reply.text)
        attempt.open = None
        if receiver != attempt.main_id:
            raise _Stop("the bot says the pages went to another account", reply.text)
        if sorted(set(done_pages)) != sorted(set(pages)):
            raise _Stop("the bot gave page(s) {} instead of {}".format(
                " ".join(map(str, done_pages)), " ".join(map(str, pages))), reply.text)
        self._log("Harem give: page(s) {} given to the main.".format(" ".join(map(str, pages))), "SUCCESS")
        return list(pages)

    async def _pause(self, busy, partner):
        low, high = self.answer_delay
        if not await self._wait(random.uniform(low, high)):
            raise _Stop("paused or stopping")
        still_busy = busy()
        if still_busy:
            raise _Stop("this account became busy ({})".format(still_busy))
        partner_busy = getattr(partner, "busy_reason", lambda: None)()
        if partner_busy:
            raise _Stop("the main became busy ({})".format(partner_busy))

    @staticmethod
    def _expect(kind, reply, wanted, timeout_reason):
        if kind == wanted:
            return
        if kind == "timeout":
            raise _Stop(timeout_reason)
        if kind == "refused":
            raise _Stop("the game bot refused the message (⛔)")
        if kind == "stopped":
            raise _Stop("the game bot stopped the procedure", reply.text)
        raise _Stop("unexpected reply", reply.text if reply is not None else "")

    def _addressed_to_pair(self, reply: BotReply) -> bool:
        attempt = self._attempt
        text = _plain(reply.text)
        if reply.reference_id is not None and reply.reference_id in attempt.sent_ids:
            return True
        lead = re.match(r"^\s*<@!?(\d+)>", text)
        if lead:
            return lead.group(1) in {attempt.own_id, attempt.main_id}
        name = (re.match(r"^\s*([^,\n]{1,80})\s*,", text) or [None, ""])[1]
        return bool(name) and clean_line(name).casefold() in {clean_line(n).casefold() for n in attempt.own_names}

    def _after_our_messages(self, reply: BotReply) -> bool:
        sent = [value for value in self._attempt.sent_ids if isinstance(value, int)]
        return not (isinstance(reply.message_id, int) and sent and reply.message_id <= max(sent))

    async def _next(self, timeout, *, expect):
        attempt = self._attempt
        deadline = self._monotonic() + timeout
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return "timeout", None
            try:
                kind, payload = await asyncio.wait_for(self._queue.get(), timeout=min(remaining, 0.5))
            except asyncio.TimeoutError:
                continue
            if kind == "refused":
                if payload in attempt.sent_ids:
                    return "refused", None
                continue
            reply = payload
            if not self._after_our_messages(reply):
                continue
            who = parse_who_question(reply.text)
            if who is not None:
                if who[0] == attempt.own_id and who[1] == attempt.main_id:
                    return "who", reply
                continue
            question = parse_gift_question(reply.text)
            if question is not None:
                if question.receiver_id == attempt.main_id:
                    return "confirm", reply
                continue
            done = parse_gift_done(reply.text)
            if done is not None:
                if done[1] == attempt.main_id and expect == "done":
                    return "done", reply
                continue
            if not self._addressed_to_pair(reply):
                continue
            if _STOPPED_RE.search(reply.text or ""):
                attempt.open = None
                return "stopped", reply
            return "other", reply

    async def _cancel_open(self, channel, partner, prefix):
        attempt = self._attempt
        if attempt is None or attempt.open is None:
            return
        which, attempt.open = attempt.open, None
        if which == "receiver":
            try:
                if await partner.answer(attempt.channel_id, "n"):
                    return
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
        try:
            await self._send(channel, "{}exit".format(prefix or "$"))
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    def _finish(self, outcome: GiveOutcome) -> GiveOutcome:
        bot_text = " Bot said: «{}»".format(outcome.bot_text.strip()[:300]) if outcome.bot_text else ""
        if outcome.status == "given":
            self._failures = 0
            self._retry_at = None
            self.status = "Harem give: " + outcome.reason + "."
            self._log("Harem give: " + outcome.reason + ".", "SUCCESS")
        elif outcome.status == "stopped":
            self._failures += 1
            step = self.backoff_steps[min(self._failures, len(self.backoff_steps)) - 1]
            self._retry_at = self._monotonic() + step
            self.status = "Harem give stopped: {}. Next try in {} min.".format(outcome.reason, int(step // 60))
            self._log(self.status + bot_text, "WARN")
        else:
            self.status = "Harem give: " + outcome.reason + "."
        return outcome
