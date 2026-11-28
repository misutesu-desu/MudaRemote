"""Auto-give spheres from a SIDE account to its Main (``$givesp <@MAIN_ID> AMOUNT``).

Modelled on ``kakera_give`` (same helpers, back-off steps and busy rules).
There is NO minimum: once the known sphere stock (read from the ``$tu`` replies
and sphere-game results the program already gets; never an extra ``$tu``) is
above what the account keeps (``spheres_keep``, default 0), it is given.

Order of work: every sphere game the automation plays is finished first. On a
side account whose perk-10 upgrade (``auto_perk10``) is ON, automatic giving is
off entirely (the side keeps its spheres for its own upgrades; the saved
``auto_give_spheres`` value is not changed, it just has no effect). The manual
«Give all spheres now» button is an explicit request and still works. At most one give per
``sphere_give_interval_min`` (default 30), one at a time per account, never
while the account is busy, growing back-off after a failure.

Flow (the owner's words: «$givesp <@id> then Y»; same shape as ``$givek``):

    side:  $givesp <@MAIN_ID> 1250          (the whole known stock minus the keep, re-read just before sending)
    bot:   «<side>, do you really want to give 1250 <sphere> ? (y/n/yes/no)»     [ASSUMED wording]
    side:  Y                                (only when the amount equals ours and no other receiver is named)
    bot:   «<@side> just gifted 1250 <sphere> to <@main>» or a ✅ on our Y       [ASSUMED wording]

The real reply wording of ``$givesp`` is NOT in the owner's samples, so every
pattern lives in the two tables below (``QUESTION_PATTERNS`` and
``SUCCESS_PATTERNS``) and is written tolerantly. Anything not recognised is
never answered with ``Y``: it is logged (shortened, ids masked) and the account
backs off.
"""

import asyncio
import datetime
import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple

from .kakera_give import (
    BACKOFF_STEPS_SECONDS, MANUAL_BUSY_WAIT_SECONDS, MANUAL_COOLDOWN_SECONDS, MANUAL_POLL_SECONDS,
    QUESTION_TIMEOUT_SECONDS, RESULT_TIMEOUT_SECONDS, BotReply, GiveOutcome, _whole, looks_like_refusal,
)
from .logs import redact_text, shorten_reply
from .totals import KAKERA, NUMBER, SOURCE_GIFT_RECEIVED, SOURCE_GIVE, SPHERES, emoji_kind, parse_amount

SPHERE_GIVE_DEFAULTS = {
    "auto_give_spheres": False,
    "sphere_give_interval_min": 30,
    "spheres_keep": 0,
}
INTERVAL_MIN_MAX = 1440
KEEP_MAX = 1_000_000_000
STATE_SECTION = "sphere_gives"

IDLE = "idle"
SENDING = "sending"
AWAITING_QUESTION = "awaiting question"
ANSWERING = "answering"
AWAITING_RESULT = "awaiting result"

_EMOJI = r"(?:<a?:(?P<raw>[A-Za-z0-9_~]+):\d+>|:(?P<rendered>[A-Za-z0-9_~]+):|(?P<bare>[A-Za-z][A-Za-z0-9_]*))"
_AMOUNT = r"\**\s*(?P<num>" + NUMBER + r")\s*\**\s*" + _EMOJI + r"?"

# ---------------------------------------------------------------------------
# ASSUMED reply wording (edit here when the owner sends the real replies).
# ---------------------------------------------------------------------------
# A confirmation question names the amount after one of these phrases.
QUESTION_PATTERNS = (
    re.compile(r"(?:do you really want to (?:give|gift|send))\s+" + _AMOUNT, re.IGNORECASE),
    re.compile(r"(?:de verdad quieres dar|voc[eê] quer mesmo dar)\s+" + _AMOUNT, re.IGNORECASE),
)
# A confirmation is recognised by this y/n shape.
YES_NO_SHAPE = re.compile(r"y\s*/\s*n|yes\s*/\s*no", re.IGNORECASE)
# Success lines: «<@sender> just gifted N <sphere> to <@receiver>» and close variants.
_SENDER = r"(?:<@!?(?P<sender>\d+)>|\*\*[^*]+\*\*|\S+)"
_RECEIVER = r"(?:to|a|para)\s+(?:<@!?(?P<receiver>\d+)>|(?P<receiver_name>\S+))"
SUCCESS_PATTERNS = (
    re.compile(_SENDER + r"\s+(?:just gifted|just gave|just sent|gifted|gave|acaba de regalar|acabou de dar)\s+"
               + _AMOUNT + r"\s*(?:spheres?)?\s*" + _RECEIVER, re.IGNORECASE),
    re.compile(_AMOUNT + r"\s*(?:spheres?)?\s*(?:have been |has been |were |was )?(?:gifted|given|sent|transferred)\s+"
               + _RECEIVER, re.IGNORECASE),
)


def _kind_of(match) -> Optional[str]:
    name = match.group("raw") or match.group("rendered") or match.group("bare")
    return emoji_kind(name) if name else None


@dataclass(frozen=True)
class SphereQuestion:
    amount: Optional[int]  # None: the question states no amount
    receivers: Tuple[str, ...]  # every mention in the text
    kakera: bool = False  # the question speaks of kakera, not spheres


def parse_sphere_question(text) -> Optional[SphereQuestion]:
    """A y/n confirmation about giving → amount and named receivers, else None."""
    folded = str(text or "")
    if not YES_NO_SHAPE.search(folded) or not re.search(r"give|gift|send|dar\b", folded, re.IGNORECASE):
        return None
    amount = None
    kakera = False
    for pattern in QUESTION_PATTERNS:
        match = pattern.search(folded)
        if match:
            amount = parse_amount(match.group("num"))
            kakera = _kind_of(match) == KAKERA
            break
    return SphereQuestion(amount=amount, receivers=tuple(re.findall(r"<@!?(\d+)>", folded)), kakera=kakera)


@dataclass(frozen=True)
class SphereGift:
    amount: int
    sender_id: Optional[str]
    receiver_id: Optional[str]


def parse_sphere_success(text) -> Optional[SphereGift]:
    """The bot's «gifted/given» style line → SphereGift, else None (kakera lines never match)."""
    for pattern in SUCCESS_PATTERNS:
        match = pattern.search(str(text or ""))
        if not match:
            continue
        if _kind_of(match) == KAKERA:
            continue
        amount = parse_amount(match.group("num"))
        if amount is None:
            continue
        groups = match.groupdict()
        return SphereGift(amount, groups.get("sender"), groups.get("receiver"))
    return None


def spheres_to_give(stock, keep=0) -> Optional[int]:
    """Whole known stock minus the keep; None when unknown or nothing above the keep."""
    if stock is None:
        return None
    amount = int(stock) - max(0, int(keep or 0))
    return amount if amount > 0 else None


def log_reply_text(text, limit=200) -> str:
    """The bot's reply as it goes into a log line: one line, ids masked, shortened."""
    return shorten_reply(redact_text(text), limit)


PERK10_OFF_REASON = "Sphere give is off because perk-10 upgrade is on for this account"


@dataclass(frozen=True)
class SphereGiveSettings:
    enabled: bool = False
    interval_min: int = 30
    keep: int = 0
    perk10_on: bool = False  # the account's own perk-10 upgrade is on: automatic giving is off

    @classmethod
    def from_preset(cls, data):
        data = data or {}
        interval = _whole(data.get("sphere_give_interval_min"), 30, 1, INTERVAL_MIN_MAX)
        keep = _whole(data.get("spheres_keep"), 0, 0, KEEP_MAX)
        return cls(
            enabled=bool(data.get("auto_give_spheres", False)),
            interval_min=30 if interval is None else interval,
            keep=0 if keep is None else keep,
            perk10_on=bool(data.get("auto_perk10", False)),
        )


def validate_sphere_give_settings(data):
    data = data or {}
    errors = []
    if _whole(data.get("sphere_give_interval_min", 30), 30, 1, INTERVAL_MIN_MAX) is None:
        errors.append("«At most one sphere give every N minutes» must be a whole number from 1 to {}.".format(INTERVAL_MIN_MAX))
    if _whole(data.get("spheres_keep", 0), 0, 0, KEEP_MAX) is None:
        errors.append("«Spheres to keep on this account» must be a whole number from 0 to {:,}.".format(KEEP_MAX))
    return errors


@dataclass
class _Attempt:
    channel_id: object
    amount: int
    main_id: str
    own_id: str
    own_names: Tuple[str, ...]
    sent_ids: set = field(default_factory=set)
    answer_id: object = None
    question_open: bool = False
    manual: bool = False


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class SphereGiver:
    """One per side account. ``send(channel, text)`` returns the sent message (or None/False)."""

    def __init__(self, *, key, store, send, wait, log, clock=_now, monotonic=time.monotonic,
                 question_timeout=QUESTION_TIMEOUT_SECONDS, result_timeout=RESULT_TIMEOUT_SECONDS,
                 backoff_steps=BACKOFF_STEPS_SECONDS, answer_delay=(1.1, 2.6)):
        self.key = key
        self.store = store
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
        self.status = "Sphere give: idle."
        self._failures = 0
        self._retry_at = None
        self._attempt: Optional[_Attempt] = None
        self._queue: Optional[asyncio.Queue] = None
        self.manual_status = "Give all spheres: not used yet."
        self._manual_in_flight = False
        self._manual_pressed_at = None

    # -- feeding events --------------------------------------------------
    @property
    def active(self) -> bool:
        return self._attempt is not None

    def on_reply(self, reply: BotReply):
        attempt = self._attempt
        if attempt is None or self._queue is None or reply.channel_id != attempt.channel_id:
            return
        self._queue.put_nowait(("reply", reply))

    def on_ack(self, message_id):
        """The game bot put ✅ on one of this account's messages."""
        if self._attempt is not None and self._queue is not None:
            self._queue.put_nowait(("ack", message_id))

    def on_refused(self, message_id):
        """The game bot put ⛔ on one of this account's messages."""
        if self._attempt is not None and self._queue is not None:
            self._queue.put_nowait(("refused", message_id))

    # -- persisted interval ----------------------------------------------
    def last_attempt_at(self) -> Optional[datetime.datetime]:
        record = self.store.get(self.key, STATE_SECTION) or {}
        try:
            return datetime.datetime.fromisoformat(record.get("last_at"))
        except (TypeError, ValueError):
            return None

    def _mark_attempt(self):
        self.store.put(self.key, STATE_SECTION, {"last_at": self._clock().isoformat()})

    # -- decisions -------------------------------------------------------
    def _basic_blocker(self, *, role, own_id, main_id) -> Optional[str]:
        if role != "side":
            return "only a side account gives spheres to its main"
        if not main_id:
            return "the main account is not known (set Main Account ID or pick a running Main profile)"
        if own_id and str(main_id) == str(own_id):
            return "the main is this account itself"
        return None

    def blocker(self, settings: SphereGiveSettings, *, role, own_id, main_id, stock, games_reason=None,
                busy_reason=None) -> Optional[str]:
        """Why no give may start now (None: a give may start)."""
        if not settings.enabled:
            return "off"
        basic = self._basic_blocker(role=role, own_id=own_id, main_id=main_id)
        if basic:
            return basic
        if settings.perk10_on:
            return PERK10_OFF_REASON
        if self._attempt is not None:
            return "a give is already in progress"
        if busy_reason:
            return "busy: " + busy_reason
        if games_reason:
            return "sphere games first: " + games_reason
        if self._retry_at is not None and self._monotonic() < self._retry_at:
            return "backing off for about {} min after the last failed give".format(
                max(1, int((self._retry_at - self._monotonic()) // 60)))
        if stock is None:
            return "the sphere stock is unknown (it is read from the next $tu or sphere game result)"
        if spheres_to_give(stock, settings.keep) is None:
            return "no spheres above the {:,} to keep".format(settings.keep) if settings.keep else "no spheres to give"
        last = self.last_attempt_at()
        if last is not None:
            next_at = last + datetime.timedelta(minutes=settings.interval_min)
            if self._clock() < next_at:
                return "the last sphere give was less than {} min ago".format(settings.interval_min)
        return None

    async def maybe_give(self, channel, settings: SphereGiveSettings, *, role, own_id, own_names, main_id,
                         totals, main_totals=None, prefix="$",
                         games: Callable[[], Optional[str]] = lambda: None,
                         busy: Callable[[], Optional[str]] = lambda: None) -> GiveOutcome:
        stock = totals.spheres if totals is not None else None
        reason = self.blocker(settings, role=role, own_id=own_id, main_id=main_id, stock=stock,
                              games_reason=games(), busy_reason=busy())
        if reason is not None:
            if reason == "off":
                self.status = "Sphere give: off."
            elif reason == PERK10_OFF_REASON:
                self.status = PERK10_OFF_REASON + "."
            else:
                self.status = "Sphere give waits: {}.".format(reason)
            return GiveOutcome("skipped", reason)
        return await self._start(channel, settings.keep, main_id, own_id, own_names, prefix, totals, main_totals,
                                 busy, manual=False)

    async def _start(self, channel, keep, main_id, own_id, own_names, prefix, totals, main_totals, busy, manual):
        amount = spheres_to_give(totals.spheres if totals is not None else None, keep)  # re-read just before sending
        if amount is None:
            return GiveOutcome("skipped", "no spheres to give")
        self._attempt = _Attempt(
            channel_id=getattr(channel, "id", None), amount=amount, main_id=str(main_id), own_id=str(own_id or ""),
            own_names=tuple(str(name).casefold() for name in own_names or () if name), manual=manual,
        )
        self._queue = asyncio.Queue()
        self._mark_attempt()
        try:
            outcome = await self._run(channel, prefix, totals, main_totals, busy)
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
        if manual:
            return self._manual_result(outcome)
        self._finish(outcome)
        return outcome

    # -- «Give all spheres now» -------------------------------------------
    async def give_all_now(self, channel, *, keep=0, role, own_id, own_names, main_id, totals, main_totals=None,
                           prefix="$", busy: Callable[[], Optional[str]] = lambda: None,
                           games: Callable[[], Optional[str]] = lambda: None,
                           total_wait_seconds=3600.0, busy_wait_seconds=MANUAL_BUSY_WAIT_SECONDS,
                           poll_seconds=MANUAL_POLL_SECONDS) -> GiveOutcome:
        """One give of the whole stock (minus the keep) to the main, started by hand.

        Ignores the switch and the interval, waits for busy work and an unknown
        stock (up to ``total_wait_seconds``; never sends ``$tu``), one at a
        time and at most one press per minute.
        """
        basic = self._basic_blocker(role=role, own_id=own_id, main_id=main_id)
        if basic:
            return self._manual_result(GiveOutcome("refused", basic))
        now = self._monotonic()
        if self._manual_in_flight:
            return GiveOutcome("ignored", "a «Give all spheres» request is already running")
        if self._manual_pressed_at is not None and now - self._manual_pressed_at < MANUAL_COOLDOWN_SECONDS:
            return GiveOutcome("ignored", "pressed again too soon; wait {} s".format(
                int(MANUAL_COOLDOWN_SECONDS - (now - self._manual_pressed_at)) + 1))
        self._manual_pressed_at = now
        self._manual_in_flight = True
        try:
            if totals is None or totals.spheres is None:
                self.manual_status = "Give all spheres: the stock is unknown; waiting for the next $tu (up to {} min).".format(
                    max(1, int(total_wait_seconds // 60)))
                self._log(self.manual_status, "INFO")
                deadline = self._monotonic() + total_wait_seconds
                while totals is None or totals.spheres is None:
                    if self._monotonic() >= deadline:
                        return self._manual_result(GiveOutcome("stopped", "the sphere stock is still unknown (no $tu reply read in time)"))
                    if not await self._wait(poll_seconds):
                        return self._manual_result(GiveOutcome("stopped", "paused or stopping"))
            deadline = self._monotonic() + busy_wait_seconds
            announced = False
            while True:
                reason = busy() or games() or ("an automatic give is in progress" if self._attempt is not None else None)
                if reason is None:
                    break
                if not announced:
                    announced = True
                    self.manual_status = "Give all spheres: deferred while {}; it runs right after.".format(reason)
                    self._log(self.manual_status, "INFO")
                if self._monotonic() >= deadline:
                    return self._manual_result(GiveOutcome("stopped", "still busy ({})".format(reason)))
                if not await self._wait(poll_seconds):
                    return self._manual_result(GiveOutcome("stopped", "paused or stopping"))
            stock = totals.spheres if totals is not None else None
            if stock is None:
                return self._manual_result(GiveOutcome("stopped", "the sphere stock became unknown"))
            if spheres_to_give(stock, keep) is None:
                return self._manual_result(GiveOutcome("skipped", "Only {:,} spheres — nothing above the {:,} to keep".format(stock, keep)))
            return await self._start(channel, keep, main_id, own_id, own_names, prefix, totals, main_totals, busy,
                                     manual=True)
        finally:
            self._manual_in_flight = False

    def _manual_result(self, outcome: GiveOutcome) -> GiveOutcome:
        bot_text = " Bot said: «{}»".format(log_reply_text(outcome.bot_text, 300)) if outcome.bot_text and outcome.status != "given" else ""
        if outcome.status == "given":
            self.manual_status = "Give all spheres: " + outcome.reason + "."
            self._log("Give all spheres: " + outcome.reason + ".", "SUCCESS")
        else:
            reason = outcome.reason[:1].upper() + outcome.reason[1:] if outcome.reason.startswith("Only ") else outcome.reason
            self.manual_status = "Give all spheres: not given — {}.".format(reason)
            self._log(self.manual_status + bot_text, "WARN" if outcome.status == "stopped" else "INFO")
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

    async def _run(self, channel, prefix, totals, main_totals, busy):
        attempt = self._attempt
        amount = attempt.amount
        self.state = SENDING
        command = "{}givesp <@{}> {}".format(prefix or "$", attempt.main_id, amount)
        self._log("{}: giving {:,} spheres to the main.".format(
            "Give all spheres" if attempt.manual else "Sphere give", amount), "INFO")
        if not await self._send_tracked(channel, command):
            return GiveOutcome("stopped", "the $givesp command could not be sent", amount)

        self.state = AWAITING_QUESTION
        kind, reply = await self._next(self.question_timeout)
        if kind == "timeout":
            return GiveOutcome("stopped", "the game bot did not ask for confirmation in time", amount)
        if kind == "refused":
            return GiveOutcome("stopped", "the game bot refused the command (⛔)", amount)
        if kind == "success":
            return self._given(reply, totals, main_totals)
        if kind != "question":
            reason = "the game bot refused the give" if kind == "refusal" else "unexpected reply (not answered)"
            return GiveOutcome("stopped", reason, amount, reply.text)
        attempt.question_open = True
        question = parse_sphere_question(reply.text)
        problem = self._question_problem(question, attempt)
        if problem:
            await self._answer_no_if_open(channel)
            return GiveOutcome("stopped", problem + "; answered n", amount, reply.text)

        self.state = ANSWERING
        low, high = self.answer_delay
        if not await self._wait(random.uniform(low, high)):
            await self._answer_no_if_open(channel)
            return GiveOutcome("stopped", "paused or stopping before answering", amount)
        still_busy = busy()
        if still_busy:
            await self._answer_no_if_open(channel)
            return GiveOutcome("stopped", "became busy ({}); answered n".format(still_busy), amount)
        current = totals.spheres if totals is not None else None
        if current is not None and amount > current:
            await self._answer_no_if_open(channel)
            return GiveOutcome("stopped", "the known stock fell to {:,} below {:,}; answered n".format(current, amount), amount)
        answered = await self._send_tracked(channel, "Y")
        if not answered:
            await self._answer_no_if_open(channel)
            return GiveOutcome("stopped", "could not answer Y", amount)
        attempt.answer_id = getattr(answered, "id", None)
        attempt.question_open = False

        self.state = AWAITING_RESULT
        kind, reply = await self._next(self.result_timeout, accept_ack=True)
        if kind in ("success", "ack"):
            return self._given(reply, totals, main_totals)
        # The give may or may not have happened: the stock is unknown until the next $tu.
        if totals is not None:
            totals.set_total(SPHERES, None, SOURCE_GIVE)
        if kind == "timeout":
            return GiveOutcome("stopped", "no «gifted» line or ✅ in time", amount)
        if kind == "refused":
            return GiveOutcome("stopped", "the game bot refused the answer (⛔)", amount)
        if kind == "refusal":
            return GiveOutcome("stopped", "the game bot refused the give after Y", amount, reply.text)
        return GiveOutcome("stopped", "unexpected reply after Y", amount, reply.text)

    @staticmethod
    def _question_problem(question: Optional[SphereQuestion], attempt: _Attempt) -> Optional[str]:
        """Why the bot's question must NOT be answered Y (None: it may be)."""
        if question is None:
            return "the reply is not a recognised confirmation question"
        if question.kakera:
            return "the question is about kakera, not spheres"
        if question.amount is None:
            return "the question states no amount"
        if question.amount != attempt.amount:
            return "the bot asked about {:,} instead of {:,}".format(question.amount, attempt.amount)
        others = [mention for mention in question.receivers if mention not in (attempt.main_id, attempt.own_id)]
        if others:
            return "the question names another receiver"
        return None

    def _given(self, reply, totals, main_totals):
        attempt = self._attempt
        gift = parse_sphere_success(reply.text) if isinstance(reply, BotReply) else None
        amount = gift.amount if gift else attempt.amount
        if totals is not None:
            totals.add(SPHERES, -amount, SOURCE_GIVE)
        if main_totals is not None:
            main_totals.add(SPHERES, amount, SOURCE_GIFT_RECEIVED)
        note = ""
        if gift and gift.receiver_id and gift.receiver_id != attempt.main_id:
            note = " (the confirmation names another receiver; check the log)"
        if amount != attempt.amount:
            note += " (confirmed {:,}, intended {:,})".format(amount, attempt.amount)
        text = reply.text if isinstance(reply, BotReply) else ""
        return GiveOutcome("given", "gave {:,} spheres to the main{}".format(amount, note), amount, text)

    def _addressed_to_self(self, reply: BotReply) -> bool:
        attempt = self._attempt
        text = str(reply.text or "")
        if reply.reference_id is not None and reply.reference_id in attempt.sent_ids:
            return True
        lead = re.match(r"^\s*(?:\*\*)?<@!?(\d+)>", text)
        if lead:
            return lead.group(1) == attempt.own_id
        bold = re.match(r"^\s*\*\*([^*]+)\*\*", text)
        name = bold.group(1) if bold else (re.match(r"^\s*([^,\n]{1,80})\s*,", text) or [None, ""])[1]
        return bool(name) and name.strip(" *_`~").casefold() in attempt.own_names

    def _is_after_our_messages(self, reply: BotReply) -> bool:
        sent = [value for value in self._attempt.sent_ids if isinstance(value, int)]
        return not (isinstance(reply.message_id, int) and sent and reply.message_id <= max(sent))

    async def _next(self, timeout, accept_ack=False):
        """The next relevant event: question/success/refusal/other/ack/refused, or a timeout."""
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
                if payload in self._attempt.sent_ids:
                    return "refused", None
                continue
            if kind == "ack":
                # A ✅ counts only on our own «Y» (a ✅ on the command alone proves nothing).
                if accept_ack and payload is not None and payload == self._attempt.answer_id:
                    return "ack", None
                continue
            reply = payload
            if not self._is_after_our_messages(reply):
                continue
            gift = parse_sphere_success(reply.text)
            if gift is not None:
                if (gift.sender_id == self._attempt.own_id
                        or (gift.sender_id is None and gift.amount == self._attempt.amount)):
                    return "success", reply
                continue
            if not self._addressed_to_self(reply):
                continue
            if parse_sphere_question(reply.text) is not None:
                return "question", reply
            return ("refusal" if looks_like_refusal(reply.text) else "other"), reply

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
        bot_text = " Bot said: «{}»".format(log_reply_text(outcome.bot_text, 300)) if outcome.bot_text and outcome.status != "given" else ""
        if outcome.status == "given":
            self._failures = 0
            self._retry_at = None
            self.status = "Sphere give: " + outcome.reason + "."
            self._log("Sphere give: " + outcome.reason + ".", "SUCCESS")
        elif outcome.status == "stopped":
            self._failures += 1
            step = self.backoff_steps[min(self._failures, len(self.backoff_steps)) - 1]
            self._retry_at = self._monotonic() + step
            self.status = "Sphere give stopped: {}. Next try in {} min.".format(outcome.reason, int(step // 60))
            # «Bot said:» makes the log classifier file this WARN line under ERROR.
            self._log(self.status + bot_text, "WARN")
