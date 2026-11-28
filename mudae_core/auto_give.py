"""Automatic gives to the main account: kakera (``$givek``) and spheres (``$givesp``).

An account whose preset sets «Main Account ID» gives to that account:

* kakera: once the kakera stock of the latest ``$tu`` reaches
  ``give_kakera_threshold`` (default 45,000), it gives all of it
  (``give_kakera_amount_mode`` = ``everything``) or exactly the threshold
  (``amount``); at most ``give_kakera_daily_cap`` gives a day.
* spheres: once the sphere games of the cycle are played out, it gives the
  whole sphere stock minus ``spheres_keep``, at most once every
  ``sphere_give_interval_min`` minutes. An account whose own perk-10 upgrade
  (``auto_perk10``) is on keeps its spheres: sphere give does nothing for it.

Flow (the ``$givek`` replies as seen on a live account; the ``$givesp``
replies are assumed to have the same shape):

    account: $givek <@MAIN_ID> 45132
    bot:     «<name>, do you really want to give 45132 <kakera> ? (y/n/yes/no)»
    account: Y      (only when the amount is ours, the emoji is of the right kind
                     and no other user is named; otherwise n)
    bot:     «<@account> just gifted 45132 <kakera> to <@main>»   (or ✅ on the command or the «Y»)

An account never gives to itself and never without a main id (one log line).
The stocks come only from replies the bot already gets; no extra ``$tu`` is
ever sent. Any other outcome stops cleanly (answers n while the question is
open), logs the bot's text and backs off with growing delays. One give at a
time, never while the account is busy. The daily count, the interval and the
back-off live in this object (one per account and kind) and start fresh when
the bot restarts.
"""

import asyncio
import datetime
import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple

from .sphere_stock import NUMBER, is_kakera_emoji, is_sphere_emoji, parse_amount

KAKERA = "kakera"
SPHERES = "spheres"
MODE_EVERYTHING = "everything"
MODE_AMOUNT = "amount"
AMOUNT_MODES = (MODE_EVERYTHING, MODE_AMOUNT)

AUTO_GIVE_DEFAULTS = {
    "auto_give_kakera": False,
    "give_kakera_threshold": 45000,
    "give_kakera_amount_mode": MODE_EVERYTHING,
    "give_kakera_daily_cap": 3,
    "auto_give_spheres": False,
    "sphere_give_interval_min": 30,
    "spheres_keep": 0,
}
THRESHOLD_MAX = 1_000_000_000
DAILY_CAP_MAX = 50
INTERVAL_MIN_MAX = 1440
KEEP_MAX = 1_000_000_000
QUESTION_TIMEOUT_SECONDS = 20.0
RESULT_TIMEOUT_SECONDS = 20.0
BACKOFF_STEPS_SECONDS = (600.0, 1800.0, 3600.0, 10800.0, 21600.0)

IDLE = "idle"
SENDING = "sending"
AWAITING_QUESTION = "awaiting question"
ANSWERING = "answering"
AWAITING_RESULT = "awaiting result"

_EMOJI = r"(?:<a?:(?P<raw>[A-Za-z0-9_~]+):\d+>|:(?P<rendered>[A-Za-z0-9_~]+):|(?P<bare>[A-Za-z][A-Za-z0-9_]*))"
_AMOUNT = r"\**\s*(?P<num>" + NUMBER + r")\s*\**\s*" + _EMOJI + r"?"
_YES_NO = re.compile(r"y\s*/\s*n|yes\s*/\s*no", re.IGNORECASE)
_QUESTION_RE = re.compile(
    r"(?:do you really want to give|de verdad quieres dar|voc[eê] quer mesmo dar)\s+" + _AMOUNT, re.IGNORECASE,
)
_SUCCESS_RE = re.compile(
    r"(?:<@!?(?P<sender>\d+)>|\*\*[^*]+\*\*|\S+)\s+(?:just gifted|acaba de regalar|acabou de dar)\s+" + _AMOUNT
    + r"\s*(?:to|a|para)\s+(?:<@!?(?P<receiver>\d+)>|\S+)",
    re.IGNORECASE,
)
_MENTION_RE = re.compile(r"<@!?(\d+)>")
_REFUSAL_WORDS = (
    "not enough", "don't have enough", "do not have enough", "you don't have", "you do not have",
    "disabled", "can't", "cannot", "not allowed", "procedure has been stopped", "invalid",
    "no tienes", "insuficiente",
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
    ("give_kakera_threshold", 1, THRESHOLD_MAX),
    ("give_kakera_daily_cap", 1, DAILY_CAP_MAX),
    ("sphere_give_interval_min", 1, INTERVAL_MIN_MAX),
    ("spheres_keep", 0, KEEP_MAX),
)


@dataclass(frozen=True)
class AutoGiveSettings:
    give_kakera: bool = False
    kakera_threshold: int = 45000
    kakera_mode: str = MODE_EVERYTHING
    kakera_daily_cap: int = 3
    give_spheres: bool = False
    sphere_interval_min: int = 30
    spheres_keep: int = 0
    perk10_on: bool = False  # the account's own perk-10 upgrade keeps its spheres

    @classmethod
    def from_preset(cls, data):
        data = data or {}

        def number(key, minimum, maximum):
            found = _whole(data.get(key), AUTO_GIVE_DEFAULTS[key], minimum, maximum)
            return AUTO_GIVE_DEFAULTS[key] if found is None else found

        values = {key: number(key, minimum, maximum) for key, minimum, maximum in _LIMITS}
        mode = str(data.get("give_kakera_amount_mode") or MODE_EVERYTHING).strip().casefold()
        return cls(
            give_kakera=bool(data.get("auto_give_kakera", False)),
            kakera_threshold=values["give_kakera_threshold"],
            kakera_mode=mode if mode in AMOUNT_MODES else MODE_EVERYTHING,
            kakera_daily_cap=values["give_kakera_daily_cap"],
            give_spheres=bool(data.get("auto_give_spheres", False)),
            sphere_interval_min=values["sphere_give_interval_min"],
            spheres_keep=values["spheres_keep"],
            perk10_on=bool(data.get("auto_perk10", False)),
        )


def validate_auto_give_settings(data):
    """Preset validation errors for the automatic-give settings (empty when valid)."""
    data = data or {}
    errors = []
    for key, minimum, maximum in _LIMITS:
        if _whole(data.get(key, AUTO_GIVE_DEFAULTS[key]), AUTO_GIVE_DEFAULTS[key], minimum, maximum) is None:
            errors.append("{} must be a whole number from {:,} to {:,}.".format(key, minimum, maximum))
    mode = str(data.get("give_kakera_amount_mode", MODE_EVERYTHING) or MODE_EVERYTHING).strip().casefold()
    if mode not in AMOUNT_MODES:
        errors.append("give_kakera_amount_mode must be «everything» or «amount».")
    return errors


# ---------------------------------------------------------------------------
# Decisions and reply parsing (pure)
# ---------------------------------------------------------------------------

def receiver_problem(own_id, main_id) -> Optional[str]:
    """Why this account may not give to the main (None: it may)."""
    main = str(main_id or "").strip()
    if not main:
        return "no Main Account ID is set"
    if str(own_id or "").strip() == main:
        return "this account is the Main Account itself"
    return None


def kakera_to_give(total, threshold, mode=MODE_EVERYTHING) -> Optional[int]:
    """45,132 with threshold 45,000 → 45,132 (everything) or 45,000 (amount); below the threshold → None."""
    if total is None or threshold is None or threshold < 1 or total < threshold:
        return None
    return int(threshold) if mode == MODE_AMOUNT else int(total)


def spheres_to_give(stock, keep=0) -> Optional[int]:
    """The whole stock minus the keep; None when unknown or nothing is above the keep."""
    if stock is None:
        return None
    amount = int(stock) - max(0, int(keep or 0))
    return amount if amount > 0 else None


def _emoji_kind(match) -> Optional[str]:
    name = match.group("raw") or match.group("rendered") or match.group("bare")
    if not name:
        return None
    if is_kakera_emoji(name):
        return KAKERA
    if is_sphere_emoji(name):
        return SPHERES
    return None


@dataclass(frozen=True)
class GiveQuestion:
    amount: Optional[int]
    kind: Optional[str]  # KAKERA / SPHERES from the emoji after the amount, None when not told
    mentions: Tuple[str, ...]


def parse_give_question(text) -> Optional[GiveQuestion]:
    """«<name>, do you really want to give N <emoji> ? (y/n/yes/no)» → GiveQuestion, else None."""
    folded = str(text or "")
    if not _YES_NO.search(folded):
        return None
    match = _QUESTION_RE.search(folded)
    if not match:
        return None
    return GiveQuestion(parse_amount(match.group("num")), _emoji_kind(match), tuple(_MENTION_RE.findall(folded)))


@dataclass(frozen=True)
class Gift:
    amount: int
    sender_id: Optional[str]
    receiver_id: Optional[str]
    kind: Optional[str]


def parse_give_success(text) -> Optional[Gift]:
    """«<@sender> just gifted N <emoji> to <@receiver>» → Gift, else None."""
    match = _SUCCESS_RE.search(str(text or ""))
    if not match:
        return None
    amount = parse_amount(match.group("num"))
    if amount is None:
        return None
    return Gift(amount, match.group("sender"), match.group("receiver"), _emoji_kind(match))


def looks_like_refusal(text) -> bool:
    folded = str(text or "").casefold()
    return any(word in folded for word in _REFUSAL_WORDS)


# ---------------------------------------------------------------------------
# The giver
# ---------------------------------------------------------------------------

@dataclass
class BotReply:
    """A game-bot message as the flow needs it."""
    message_id: object
    channel_id: object
    text: str
    reference_id: object = None


@dataclass
class GiveOutcome:
    status: str  # "given", "stopped", "skipped"
    reason: str = ""
    amount: Optional[int] = None
    bot_text: str = ""


@dataclass
class _Attempt:
    channel_id: object
    amount: int
    main_id: str
    own_id: str
    own_names: Tuple[str, ...]
    sent_ids: set = field(default_factory=set)
    command_id: object = None
    answer_id: object = None
    question_open: bool = False


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class MainAccountGiver:
    """Gives one kind (``KAKERA`` or ``SPHERES``) to the main account; one per account and kind.

    ``send(channel, text)`` returns the sent message (or None/False);
    ``wait(seconds)`` is the bot's interruptible delay (False when paused/stopping).
    """

    def __init__(self, kind, *, send, wait, log, clock=_now, monotonic=time.monotonic,
                 question_timeout=QUESTION_TIMEOUT_SECONDS, result_timeout=RESULT_TIMEOUT_SECONDS,
                 backoff_steps=BACKOFF_STEPS_SECONDS, answer_delay=(1.1, 2.6)):
        if kind not in (KAKERA, SPHERES):
            raise ValueError("kind must be KAKERA or SPHERES")
        self.kind = kind
        self.command = "givek" if kind == KAKERA else "givesp"
        self.label = "Kakera give" if kind == KAKERA else "Sphere give"
        self._send = send
        self._wait = wait
        self._log = log
        self._clock = clock
        self._monotonic = monotonic
        self.question_timeout = question_timeout
        self.result_timeout = result_timeout
        self.backoff_steps = tuple(backoff_steps)
        self.answer_delay = answer_delay
        self.state = IDLE
        self.status = self.label + ": idle."
        self._failures = 0
        self._retry_at = None  # monotonic seconds
        self._attempt: Optional[_Attempt] = None
        self._queue: Optional[asyncio.Queue] = None
        self._gives = (None, 0)  # (day, count)
        self._last_attempt_at: Optional[datetime.datetime] = None
        self._noted = None  # the «will not give» reason already logged once

    # -- feeding events --------------------------------------------------
    @property
    def active(self) -> bool:
        return self._attempt is not None

    def on_message(self, message, text):
        """Every game-bot message in the account's channels."""
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

    def on_ack(self, message_id):
        """The game bot put ✅ on a message."""
        if self._attempt is not None and self._queue is not None:
            self._queue.put_nowait(("ack", message_id))

    def on_refused(self, message_id):
        """The game bot put ⛔ on a message."""
        if self._attempt is not None and self._queue is not None:
            self._queue.put_nowait(("refused", message_id))

    # -- per-account memory ----------------------------------------------
    def today(self):
        return self._clock().date()

    def gives_today(self) -> int:
        day, count = self._gives
        return count if day == self.today() else 0

    def _count_give(self) -> int:
        count = self.gives_today() + 1
        self._gives = (self.today(), count)
        return count

    # -- decisions -------------------------------------------------------
    def _stock_value(self, stock):
        if stock is None:
            return None
        return getattr(stock, "kakera" if self.kind == KAKERA else "spheres", None)

    def amount_for(self, settings: AutoGiveSettings, value) -> Optional[int]:
        if self.kind == KAKERA:
            return kakera_to_give(value, settings.kakera_threshold, settings.kakera_mode)
        return spheres_to_give(value, settings.spheres_keep)

    def note(self, settings: AutoGiveSettings, *, own_id, main_id) -> Optional[str]:
        """A lasting reason this account never gives (no main id, itself, perk 10 on), else None."""
        enabled = settings.give_kakera if self.kind == KAKERA else settings.give_spheres
        if not enabled:
            return None
        problem = receiver_problem(own_id, main_id)
        if problem:
            return problem
        if self.kind == SPHERES and settings.perk10_on:
            return "the perk-10 upgrade is on for this account, so it keeps its spheres"
        return None

    def blocker(self, settings: AutoGiveSettings, *, own_id, main_id, value, games_reason=None,
                busy_reason=None) -> Optional[str]:
        """Why no give may start now (None: a give may start)."""
        enabled = settings.give_kakera if self.kind == KAKERA else settings.give_spheres
        if not enabled:
            return "off"
        lasting = self.note(settings, own_id=own_id, main_id=main_id)
        if lasting:
            return lasting
        if self._attempt is not None:
            return "a give is already in progress"
        if busy_reason:
            return "busy: " + busy_reason
        if self.kind == SPHERES and games_reason:
            return "sphere games first: " + games_reason
        if self._retry_at is not None and self._monotonic() < self._retry_at:
            return "backing off for about {} min after the last failed give".format(
                max(1, int((self._retry_at - self._monotonic()) // 60)))
        if value is None:
            return "the {} stock is unknown (it is read from the next $tu)".format(
                "kakera" if self.kind == KAKERA else "sphere")
        if self.amount_for(settings, value) is None:
            if self.kind == KAKERA:
                return "kakera {:,} is below {:,}".format(value, settings.kakera_threshold)
            return "no spheres above the {:,} to keep".format(settings.spheres_keep)
        if self.kind == KAKERA and self.gives_today() >= settings.kakera_daily_cap:
            return "the daily limit of {} give(s) is reached".format(settings.kakera_daily_cap)
        if self.kind == SPHERES and self._last_attempt_at is not None:
            if self._clock() < self._last_attempt_at + datetime.timedelta(minutes=settings.sphere_interval_min):
                return "the last sphere give was less than {} min ago".format(settings.sphere_interval_min)
        return None

    async def maybe_give(self, channel, settings: AutoGiveSettings, *, own_id, own_names, main_id, stock,
                         prefix="$", games: Callable[[], Optional[str]] = lambda: None,
                         busy: Callable[[], Optional[str]] = lambda: None) -> GiveOutcome:
        """One give when nothing blocks it; ``stock`` is the account's ``KakeraStock`` or ``SphereStock``."""
        lasting = self.note(settings, own_id=own_id, main_id=main_id)
        if lasting != self._noted:
            self._noted = lasting
            if lasting:
                self._log("{}: not giving to the main account: {}.".format(self.label, lasting), "INFO")
        reason = self.blocker(settings, own_id=own_id, main_id=main_id, value=self._stock_value(stock),
                              games_reason=games() if self.kind == SPHERES else None, busy_reason=busy())
        if reason is not None:
            self.status = self.label + (": off." if reason == "off" else " waits: {}.".format(reason))
            return GiveOutcome("skipped", reason)
        amount = self.amount_for(settings, self._stock_value(stock))
        self._attempt = _Attempt(
            channel_id=getattr(channel, "id", None), amount=amount, main_id=str(main_id).strip(),
            own_id=str(own_id or ""), own_names=tuple(str(name).casefold() for name in own_names or () if name),
        )
        self._queue = asyncio.Queue()
        self._last_attempt_at = self._clock()
        try:
            outcome = await self._run(channel, prefix, stock, busy)
        except asyncio.CancelledError:
            await self._answer_no_if_open(channel)
            raise
        except Exception as exc:
            await self._answer_no_if_open(channel)
            outcome = GiveOutcome("stopped", "error: {}".format(type(exc).__name__), amount)
        finally:
            self._attempt = None
            self._queue = None
            self.state = IDLE
        self._finish(outcome)
        return outcome

    # -- the flow --------------------------------------------------------
    async def _send_tracked(self, channel, text):
        receipt = await self._send(channel, text)
        if not receipt:
            return None
        message_id = getattr(receipt, "id", None)
        if message_id is not None and self._attempt is not None:
            self._attempt.sent_ids.add(message_id)
        return receipt

    async def _run(self, channel, prefix, stock, busy) -> GiveOutcome:
        attempt = self._attempt
        amount = attempt.amount
        unit = "kakera" if self.kind == KAKERA else "spheres"
        self.state = SENDING
        self._log("{}: giving {:,} {} to the main account.".format(self.label, amount, unit), "INFO")
        sent = await self._send_tracked(channel, "{}{} <@{}> {}".format(prefix or "$", self.command,
                                                                       attempt.main_id, amount))
        if not sent:
            return GiveOutcome("stopped", "the ${} command could not be sent".format(self.command), amount)
        attempt.command_id = getattr(sent, "id", None)

        self.state = AWAITING_QUESTION
        kind, reply = await self._next(self.question_timeout, answered=False)
        if kind == "timeout":
            return GiveOutcome("stopped", "the game bot did not ask for confirmation in time", amount)
        if kind == "refused":
            return GiveOutcome("stopped", "the game bot refused the command (⛔)", amount)
        text = reply.text
        if _YES_NO.search(text):
            attempt.question_open = True
        problem = self._question_problem(parse_give_question(text))
        if problem:
            answered_no = attempt.question_open
            await self._answer_no_if_open(channel)
            if not answered_no:
                problem = "the game bot refused the give" if looks_like_refusal(text) else "unexpected reply"
            return GiveOutcome("stopped", problem + ("; answered n" if answered_no else ""), amount, text)

        self.state = ANSWERING
        low, high = self.answer_delay
        if not await self._wait(random.uniform(low, high)):
            await self._answer_no_if_open(channel)
            return GiveOutcome("stopped", "paused or stopping before answering; answered n", amount)
        still_busy = busy()
        if still_busy:
            await self._answer_no_if_open(channel)
            return GiveOutcome("stopped", "became busy ({}); answered n".format(still_busy), amount)
        current = self._stock_value(stock)
        if current is not None and amount > current:
            await self._answer_no_if_open(channel)
            return GiveOutcome("stopped", "the known stock fell to {:,}; answered n".format(current), amount)
        self._drop_queued_acks()
        answered = await self._send_tracked(channel, "Y")
        if not answered:
            await self._answer_no_if_open(channel)
            return GiveOutcome("stopped", "could not answer Y", amount)
        attempt.answer_id = getattr(answered, "id", None)
        attempt.question_open = False

        self.state = AWAITING_RESULT
        kind, reply = await self._next(self.result_timeout, answered=True)
        if kind in ("success", "ack"):
            return self._given(reply, stock)
        # The give may or may not have happened: the stock is unknown until the
        # next $tu, and the attempt counts toward the daily limit.
        if stock is not None:
            stock.set(None)
        self._count_give()
        if kind == "timeout":
            return GiveOutcome("stopped", "no «just gifted» line or ✅ in time after Y", amount)
        if kind == "refused":
            return GiveOutcome("stopped", "the game bot refused the answer (⛔)", amount)
        reason = "the game bot refused the give after Y" if looks_like_refusal(reply.text) else "unexpected reply after Y"
        return GiveOutcome("stopped", reason, amount, reply.text)

    def _question_problem(self, question: Optional[GiveQuestion]) -> Optional[str]:
        """Why the bot's question must NOT be answered Y (None: it may be)."""
        attempt = self._attempt
        if question is None:
            return "the reply is not a recognised confirmation question"
        if question.amount != attempt.amount:
            return "the bot asked about {} instead of {:,}".format(
                "another amount" if question.amount is None else "{:,}".format(question.amount), attempt.amount)
        if question.kind is not None and question.kind != self.kind:
            return "the question is about {}, not {}".format(question.kind, self.kind)
        if self.kind == KAKERA and question.kind is None:
            return "the question does not name kakera"
        if any(mention not in (attempt.main_id, attempt.own_id) for mention in question.mentions):
            return "the question names another user"
        return None

    def _given(self, reply, stock) -> GiveOutcome:
        attempt = self._attempt
        gift = parse_give_success(reply.text) if isinstance(reply, BotReply) else None
        amount = gift.amount if gift else attempt.amount
        if stock is not None:
            stock.spend(amount)
        count = self._count_give()
        note = ""
        if gift and gift.receiver_id and gift.receiver_id != attempt.main_id:
            note = " (the confirmation names another receiver; check the log)"
        if amount != attempt.amount:
            note += " (confirmed {:,}, intended {:,})".format(amount, attempt.amount)
        unit = "kakera" if self.kind == KAKERA else "spheres"
        text = reply.text if isinstance(reply, BotReply) else ""
        return GiveOutcome("given", "gave {:,} {} to the main account (give {} today){}".format(
            amount, unit, count, note), amount, text)

    def _addressed_to_self(self, reply: BotReply) -> bool:
        attempt = self._attempt
        text = str(reply.text or "")
        if reply.reference_id is not None:
            return reply.reference_id in attempt.sent_ids
        lead = re.match(r"^\s*(?:\*\*)?<@!?(\d+)>", text)
        if lead:
            return lead.group(1) == attempt.own_id
        bold = re.match(r"^\s*\*\*([^*]+)\*\*", text)
        named = bold.group(1) if bold else None
        if named is None:
            plain = re.match(r"^\s*([^,\n]{1,80})\s*,", text)
            named = plain.group(1) if plain else None
        return bool(named) and named.strip(" *_`~").casefold() in attempt.own_names

    def _is_after_our_messages(self, reply: BotReply) -> bool:
        sent = [value for value in self._attempt.sent_ids if isinstance(value, int)]
        return not (isinstance(reply.message_id, int) and sent and reply.message_id <= max(sent))

    async def _next(self, timeout, *, answered):
        """The next relevant event: ("reply", BotReply), ("success", BotReply), ("ack"|"refused", id) or a timeout.

        Before Y only the bot's question (or refusal) counts; a «just gifted»
        line or a ✅ proves the give only once Y has been answered.
        """
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
                    return "refused", payload
                continue
            if kind == "ack":
                if answered and payload is not None and payload in (attempt.answer_id, attempt.command_id):
                    return "ack", payload
                continue
            reply = payload
            if not self._is_after_our_messages(reply):
                continue
            gift = parse_give_success(reply.text)
            if gift is not None:
                ours = gift.sender_id == attempt.own_id or (gift.sender_id is None and gift.amount == attempt.amount)
                if answered and ours and gift.kind in (None, self.kind):
                    return "success", reply
                continue
            if not self._addressed_to_self(reply):
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

    def _finish(self, outcome: GiveOutcome):
        bot_text = (" Bot said: «{}»".format(outcome.bot_text.strip()[:300])
                    if outcome.bot_text and outcome.status != "given" else "")
        if outcome.status == "given":
            self._failures = 0
            self._retry_at = None
            self.status = "{}: {}.".format(self.label, outcome.reason)
            self._log(self.status, "INFO")
        elif outcome.status == "stopped":
            self._failures += 1
            step = self.backoff_steps[min(self._failures, len(self.backoff_steps)) - 1]
            self._retry_at = self._monotonic() + step
            self.status = "{} stopped: {}. Next try in {} min.".format(self.label, outcome.reason, int(step // 60))
            self._log(self.status + bot_text, "WARN")
