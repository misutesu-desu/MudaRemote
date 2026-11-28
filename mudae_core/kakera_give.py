"""Auto-give kakera from a SIDE account to its Main (``$givek <@MAIN_ID> AMOUNT``).

Flow (game bot replies transcribed in the owner's samples):

    side:  $givek <@MAIN_ID> 45132
    bot:   «<side name>, do you really want to give 45132 <kakera> ? (y/n/yes/no)»
    side:  y                      (only when the asked amount equals ours, else n)
    bot:   «<@side> just gifted 45132 <kakera> to <@main>»

States: idle → sending → awaiting question → answering → awaiting result → idle.
Every other outcome stops cleanly: no reply in time, a refusal (⛔ on the
command, «not enough», trading disabled, …), any unexpected reply addressed to
this account, an amount mismatch (answers n), a failed send. A stop answers n
if the bot's question is still open, logs the bot's text, and backs off with a
growing delay (no retry storm). One give at a time; never while the account is
busy, never to itself, never when the main is unknown; at most N per day.
"""

import asyncio
import datetime
import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple

from .totals import KAKERA, NUMBER, SOURCE_GIFT_RECEIVED, SOURCE_GIVE, emoji_kind, parse_amount

GIVE_DEFAULTS = {
    "auto_give_kakera": False,
    "give_kakera_threshold": 45000,
    "give_kakera_extra": True,  # the 6.0.x switch; read only when ``give_kakera_amount_mode`` is absent
    "give_kakera_amount_mode": "everything",
    "give_kakera_daily_cap": 3,
    "give_kakera_button_minimum": 1000,
}
# «Give all kakera now» (a button, started by hand).
MANUAL_COOLDOWN_SECONDS = 60.0
MANUAL_BUSY_WAIT_SECONDS = 600.0
MANUAL_POLL_SECONDS = 3.0
GIVE_THRESHOLD_MAX = 1_000_000_000
GIVE_DAILY_CAP_MAX = 50
QUESTION_TIMEOUT_SECONDS = 20.0
RESULT_TIMEOUT_SECONDS = 20.0
# Growing pauses after each failed give in a row: 10 min, 30 min, 1 h, 3 h, 6 h.
BACKOFF_STEPS_SECONDS = (600.0, 1800.0, 3600.0, 10800.0, 21600.0)

IDLE = "idle"
SENDING = "sending"
AWAITING_QUESTION = "awaiting question"
ANSWERING = "answering"
AWAITING_RESULT = "awaiting result"

_EMOJI = r"(?:<a?:(?P<raw>[A-Za-z0-9_~]+):\d+>|:(?P<rendered>[A-Za-z0-9_~]+):|(?P<bare>[A-Za-z][A-Za-z0-9_]*))"
_QUESTION_RE = re.compile(
    r"(?:do you really want to give|de verdad quieres dar|voc[eê] quer mesmo dar)\s+\**\s*(?P<num>" + NUMBER
    + r")\s*\**\s*" + _EMOJI + r"?\s*\??",
    re.IGNORECASE,
)
_SUCCESS_RE = re.compile(
    r"(?:<@!?(?P<sender>\d+)>|\*\*[^*]+\*\*|\S+)\s+(?:just gifted|acaba de regalar|acabou de dar)\s+\**\s*(?P<num>"
    + NUMBER + r")\s*\**\s*" + _EMOJI + r"?\s*(?:to|a|para)\s+(?:<@!?(?P<receiver>\d+)>|(?P<receiver_name>\S+))",
    re.IGNORECASE,
)
_REFUSAL_WORDS = (
    "not enough", "don't have enough", "do not have enough", "you don't have", "you do not have",
    "trade", "disabled", "togglekakeratrade", "can't give", "cannot give", "can't", "cannot",
    "not allowed", "procedure has been stopped", "invalid", "no tienes", "insuficiente",
)


def _emoji_name(match):
    return match.group("raw") or match.group("rendered") or match.group("bare")


def parse_give_question(text) -> Optional[int]:
    """The amount in «… do you really want to give N <kakera> ? (y/n/yes/no)», else None."""
    folded = str(text or "")
    if not re.search(r"y\s*/\s*n|yes\s*/\s*no", folded, re.IGNORECASE):
        return None
    match = _QUESTION_RE.search(folded)
    if not match:
        return None
    name = _emoji_name(match)
    if name and emoji_kind(name) != KAKERA:
        return None
    return parse_amount(match.group("num"))


@dataclass(frozen=True)
class GiftResult:
    amount: int
    sender_id: Optional[str]
    receiver_id: Optional[str]


def parse_give_success(text) -> Optional[GiftResult]:
    """«<@sender> just gifted N <kakera> to <@receiver>» → GiftResult, else None."""
    match = _SUCCESS_RE.search(str(text or ""))
    if not match:
        return None
    name = _emoji_name(match)
    if name and emoji_kind(name) != KAKERA:
        return None
    amount = parse_amount(match.group("num"))
    if amount is None:
        return None
    return GiftResult(amount=amount, sender_id=match.group("sender"), receiver_id=match.group("receiver"))


def looks_like_refusal(text) -> bool:
    folded = str(text or "").casefold()
    return any(word in folded for word in _REFUSAL_WORDS)


def give_amount(total, threshold, give_extra) -> Optional[int]:
    """45132 with threshold 45000 → 45132 (extra on) or 45000 (extra off); below → None."""
    if total is None or threshold is None or threshold < 1 or total < threshold:
        return None
    return int(total) if give_extra else int(threshold)


def _whole(value, default, minimum, maximum):
    if isinstance(value, bool):
        return None
    try:
        number = int(str(value if value is not None else default).strip())
    except (TypeError, ValueError):
        return None
    return number if minimum <= number <= maximum else None


AMOUNT_MODE_EVERYTHING = "everything"
AMOUNT_MODE_AMOUNT = "amount"
AMOUNT_MODES = (AMOUNT_MODE_EVERYTHING, AMOUNT_MODE_AMOUNT)


def amount_mode_from_preset(data) -> str:
    """«give everything» or «give only the amount».

    ``give_kakera_amount_mode`` wins when it holds a valid choice; a stored
    profile without it keeps its old ``give_kakera_extra`` switch (on →
    everything, off → only the amount). Nothing is ever deleted.
    """
    data = data or {}
    mode = str(data.get("give_kakera_amount_mode", "") or "").strip().casefold()
    if mode in AMOUNT_MODES:
        return mode
    return AMOUNT_MODE_EVERYTHING if bool(data.get("give_kakera_extra", True)) else AMOUNT_MODE_AMOUNT


@dataclass(frozen=True)
class GiveSettings:
    enabled: bool = False
    threshold: int = 45000
    give_extra: bool = True
    daily_cap: int = 3

    @classmethod
    def from_preset(cls, data):
        data = data or {}
        threshold = _whole(data.get("give_kakera_threshold"), 45000, 1, GIVE_THRESHOLD_MAX)
        cap = _whole(data.get("give_kakera_daily_cap"), 3, 1, GIVE_DAILY_CAP_MAX)
        return cls(
            enabled=bool(data.get("auto_give_kakera", False)),
            threshold=45000 if threshold is None else threshold,
            give_extra=amount_mode_from_preset(data) == AMOUNT_MODE_EVERYTHING,
            daily_cap=3 if cap is None else cap,
        )


def validate_give_settings(data):
    errors = []
    data = data or {}
    if _whole(data.get("give_kakera_threshold", 45000), 45000, 1, GIVE_THRESHOLD_MAX) is None:
        errors.append("«Give kakera to my main when I reach» must be a whole number from 1 to {:,}.".format(GIVE_THRESHOLD_MAX))
    mode = str(data.get("give_kakera_amount_mode", "") or "").strip().casefold()
    if mode and mode not in AMOUNT_MODES:
        errors.append("«When kakera reaches the amount» must be «everything» or «amount».")
    if _whole(data.get("give_kakera_daily_cap", 3), 3, 1, GIVE_DAILY_CAP_MAX) is None:
        errors.append("«At most N gives per day» must be a whole number from 1 to {}.".format(GIVE_DAILY_CAP_MAX))
    if _whole(data.get("give_kakera_button_minimum", 1000), 1000, 1, GIVE_THRESHOLD_MAX) is None:
        errors.append("«Minimum for the button» must be a whole number from 1 to {:,}.".format(GIVE_THRESHOLD_MAX))
    return errors


@dataclass
class BotReply:
    """A game-bot message as the give flow needs it (built by the bot glue)."""
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
    manual: bool = False  # «Give all kakera now»: not counted toward the automatic daily cap


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class KakeraGiver:
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
        self.status = "Auto-give: idle."
        self._failures = 0
        self._retry_at = None  # monotonic seconds
        self._attempt: Optional[_Attempt] = None
        self._last_sent_id = None
        self._queue: Optional[asyncio.Queue] = None
        self.manual_status = "Give all kakera: not used yet."
        self._manual_in_flight = False
        self._manual_pressed_at = None  # monotonic seconds

    # -- feeding replies -------------------------------------------------
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
        """Mudae put ⛔ on one of this account's messages."""
        if self._attempt is not None and self._queue is not None:
            self._queue.put_nowait(("refused", message_id))

    # -- decisions -------------------------------------------------------
    def today(self):
        return self._clock().date()

    def blocker(self, settings: GiveSettings, *, role, own_id, main_id, total, busy_reason=None) -> Optional[str]:
        """Why no give may start now (None: a give may start)."""
        if not settings.enabled:
            return "off"
        if role != "side":
            return "only a side account gives kakera to its main"
        if not main_id:
            return "the main account is not known (set Main Account ID or pick a running Main profile)"
        if own_id and str(main_id) == str(own_id):
            return "the main is this account itself"
        if self._attempt is not None:
            return "a give is already in progress"
        if busy_reason:
            return "busy: " + busy_reason
        if self._retry_at is not None and self._monotonic() < self._retry_at:
            wait_minutes = max(1, int((self._retry_at - self._monotonic()) // 60))
            return "backing off for about {} min after the last failed give".format(wait_minutes)
        if total is None:
            return "the kakera total is unknown (it is read from the $tu replies)"
        if total < settings.threshold:
            return "kakera {:,} is below {:,}".format(total, settings.threshold)
        if self.store.gives_today(self.key, self.today()) >= settings.daily_cap:
            return "the daily limit of {} give(s) is reached".format(settings.daily_cap)
        return None

    async def maybe_give(self, channel, settings: GiveSettings, *, role, own_id, own_names, main_id,
                         totals, main_totals=None, prefix="$", busy: Callable[[], Optional[str]] = lambda: None):
        total = totals.kakera if totals is not None else None
        reason = self.blocker(settings, role=role, own_id=own_id, main_id=main_id, total=total, busy_reason=busy())
        if reason is not None:
            return GiveOutcome("skipped", reason)
        amount = give_amount(total, settings.threshold, settings.give_extra)
        self._attempt = _Attempt(
            channel_id=getattr(channel, "id", None), amount=amount, main_id=str(main_id), own_id=str(own_id or ""),
            own_names=tuple(str(name).casefold() for name in own_names or () if name),
        )
        self._queue = asyncio.Queue()
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
        self._finish(outcome)
        return outcome

    # -- «Give all kakera now» --------------------------------------------
    async def give_all_now(self, channel, *, minimum, role, own_id, own_names, main_id, totals, main_totals=None,
                           prefix="$", busy: Callable[[], Optional[str]] = lambda: None,
                           total_wait_seconds=3600.0, busy_wait_seconds=MANUAL_BUSY_WAIT_SECONDS,
                           poll_seconds=MANUAL_POLL_SECONDS) -> GiveOutcome:
        """One give of the WHOLE kakera total to the main, started by hand.

        Ignores the auto-give switch, threshold and daily cap; needs a known
        total of at least ``minimum`` (waits for the next ``$tu`` the program
        already sends when unknown), defers while busy, one at a time and at
        most one press per minute.
        """
        if role != "side":
            return self._manual_result(GiveOutcome("refused", "only a side account gives kakera to its main"))
        if not main_id:
            return self._manual_result(GiveOutcome(
                "refused", "the main account is not known (set Main Account ID or pick a running Main profile)"))
        if own_id and str(main_id) == str(own_id):
            return self._manual_result(GiveOutcome("refused", "the main is this account itself"))
        now = self._monotonic()
        if self._manual_in_flight:
            return GiveOutcome("ignored", "a «Give all kakera» request is already running")
        if self._manual_pressed_at is not None and now - self._manual_pressed_at < MANUAL_COOLDOWN_SECONDS:
            return GiveOutcome("ignored", "pressed again too soon; wait {} s".format(
                int(MANUAL_COOLDOWN_SECONDS - (now - self._manual_pressed_at)) + 1))
        self._manual_pressed_at = now
        self._manual_in_flight = True
        try:
            if totals is None or totals.kakera is None:
                self.manual_status = "Give all kakera: the total is unknown; waiting for the next $tu (up to {} min).".format(
                    max(1, int(total_wait_seconds // 60)))
                self._log(self.manual_status, "INFO")
                deadline = self._monotonic() + total_wait_seconds
                while totals is None or totals.kakera is None:
                    if self._monotonic() >= deadline:
                        return self._manual_result(GiveOutcome("stopped", "the kakera total is still unknown (no $tu reply read in time)"))
                    if not await self._wait(poll_seconds):
                        return self._manual_result(GiveOutcome("stopped", "paused or stopping"))
            deadline = self._monotonic() + busy_wait_seconds
            announced = False
            while True:
                reason = busy() or ("an automatic give is in progress" if self._attempt is not None else None)
                if reason is None:
                    break
                if not announced:
                    announced = True
                    self.manual_status = "Give all kakera: deferred while {}; it runs right after.".format(reason)
                    self._log(self.manual_status, "INFO")
                if self._monotonic() >= deadline:
                    return self._manual_result(GiveOutcome("stopped", "still busy ({})".format(reason)))
                if not await self._wait(poll_seconds):
                    return self._manual_result(GiveOutcome("stopped", "paused or stopping"))
            total = totals.kakera if totals is not None else None  # re-read just before sending
            if total is None:
                return self._manual_result(GiveOutcome("stopped", "the kakera total became unknown"))
            if total < minimum:
                return self._manual_result(GiveOutcome("skipped", "Only {:,} kakera — the minimum is {:,}".format(total, minimum)))
            self._attempt = _Attempt(
                channel_id=getattr(channel, "id", None), amount=int(total), main_id=str(main_id), own_id=str(own_id or ""),
                own_names=tuple(str(name).casefold() for name in own_names or () if name), manual=True,
            )
            self._queue = asyncio.Queue()
            try:
                outcome = await self._run(channel, prefix, totals, main_totals, busy)
            except asyncio.CancelledError:
                await self._answer_no_if_open(channel)
                raise
            except Exception as exc:
                await self._answer_no_if_open(channel)
                outcome = GiveOutcome("stopped", "error: {}".format(type(exc).__name__), int(total))
            finally:
                self._attempt = None
                self._queue = None
                self.state = IDLE
            return self._manual_result(outcome)
        finally:
            self._manual_in_flight = False

    def _manual_result(self, outcome: GiveOutcome) -> GiveOutcome:
        bot_text = " Bot said: «{}»".format(outcome.bot_text.strip()[:300]) if outcome.bot_text and outcome.status != "given" else ""
        if outcome.status == "given":
            self.manual_status = "Give all kakera: " + outcome.reason + "."
            self._log(self.manual_status, "SUCCESS")
        else:
            reason = outcome.reason[:1].upper() + outcome.reason[1:] if outcome.reason.startswith("Only ") else outcome.reason
            self.manual_status = "Give all kakera: not given — {}.".format(reason)
            self._log(self.manual_status + bot_text, "WARN" if outcome.status == "stopped" else "INFO")
        return outcome

    # -- the flow --------------------------------------------------------
    async def _send_tracked(self, channel, text):
        receipt = await self._send(channel, text)
        if not receipt:
            return False
        message_id = getattr(receipt, "id", None)
        if message_id is not None and self._attempt is not None:
            self._attempt.sent_ids.add(message_id)
        self._last_sent_id = message_id
        return True

    async def _run(self, channel, prefix, totals, main_totals, busy):
        attempt = self._attempt
        amount = attempt.amount
        self.state = SENDING
        command = "{}givek <@{}> {}".format(prefix or "$", attempt.main_id, amount)
        self._log("{}: giving {:,} kakera to the main.".format(
            "Give all kakera" if attempt.manual else "Auto-give", amount), "INFO")
        if not await self._send_tracked(channel, command):
            return GiveOutcome("stopped", "the $givek command could not be sent", amount)
        attempt.command_id = self._last_sent_id

        self.state = AWAITING_QUESTION
        kind, reply = await self._next(self.question_timeout)
        if kind == "timeout":
            return GiveOutcome("stopped", "the game bot did not ask for confirmation in time", amount)
        if kind == "refused":
            return GiveOutcome("stopped", "the game bot refused the command (⛔)", amount)
        if kind == "success":
            return self._given(reply, totals, main_totals)
        if kind == "refusal":
            return GiveOutcome("stopped", "the game bot refused the give", amount, reply.text)
        if kind != "question":
            return GiveOutcome("stopped", "unexpected reply", amount, reply.text)
        attempt.question_open = True
        asked = parse_give_question(reply.text)
        if asked != amount:
            await self._answer_no_if_open(channel)
            return GiveOutcome("stopped", "the bot asked about {} instead of {:,}; answered n".format(
                "{:,}".format(asked) if asked is not None else "another amount", amount), amount, reply.text)

        self.state = ANSWERING
        low, high = self.answer_delay
        if not await self._wait(random.uniform(low, high)):
            await self._answer_no_if_open(channel)
            return GiveOutcome("stopped", "paused or stopping before answering", amount)
        still_busy = busy()
        if still_busy:
            await self._answer_no_if_open(channel)
            return GiveOutcome("stopped", "became busy ({}); answered n".format(still_busy), amount)
        self._drop_queued_acks()
        if not await self._send_tracked(channel, "y"):
            await self._answer_no_if_open(channel)
            return GiveOutcome("stopped", "could not answer y", amount)
        attempt.answer_id = self._last_sent_id
        attempt.question_open = False

        self.state = AWAITING_RESULT
        kind, reply = await self._next(self.result_timeout, accept_ack=True)
        if kind in ("success", "ack"):
            return self._given(reply, totals, main_totals)
        # The give may or may not have happened: the total is unknown until the
        # next $tu, and the attempt counts toward the daily limit.
        if totals is not None:
            totals.set_total(KAKERA, None, SOURCE_GIVE)
        if not attempt.manual:
            self.store.count_give(self.key, self.today())
        if kind == "timeout":
            return GiveOutcome("stopped", "no «just gifted» confirmation in time", amount)
        if kind == "refused":
            return GiveOutcome("stopped", "the game bot refused the answer (⛔)", amount)
        if kind == "refusal":
            return GiveOutcome("stopped", "the game bot refused the give after y", amount, reply.text)
        return GiveOutcome("stopped", "unexpected reply after y", amount, reply.text)

    def _given(self, reply, totals, main_totals):
        attempt = self._attempt
        gift = parse_give_success(reply.text) if isinstance(reply, BotReply) else None
        amount = gift.amount if gift else attempt.amount
        if totals is not None:
            totals.add(KAKERA, -amount, SOURCE_GIVE)
        if main_totals is not None:
            main_totals.add(KAKERA, amount, SOURCE_GIFT_RECEIVED)
        text = reply.text if isinstance(reply, BotReply) else ""
        count = self.store.gives_today(self.key, self.today()) if attempt.manual else self.store.count_give(self.key, self.today())
        note = ""
        if gift and gift.receiver_id and gift.receiver_id != attempt.main_id:
            note = " (the confirmation names another receiver; check the log)"
        if amount != attempt.amount:
            note += " (confirmed {:,}, intended {:,})".format(amount, attempt.amount)
        if attempt.manual:
            return GiveOutcome("given", "gave {:,} kakera to the main{}".format(amount, note), amount, text)
        return GiveOutcome("given", "gave {:,} kakera to the main (give {} today){}".format(amount, count, note),
                           amount, text)

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
        """The next relevant event: question/success/refusal/other/ack, or a timeout."""
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
                # A ✅ counts on our own command or our «y», and only once y has been answered.
                attempt = self._attempt
                if (accept_ack and payload is not None and attempt.answer_id is not None
                        and payload in (attempt.answer_id, attempt.command_id)):
                    return "ack", None
                continue
            reply = payload
            if not self._is_after_our_messages(reply):
                continue
            gift = parse_give_success(reply.text)
            if gift is not None:
                if (gift.sender_id == self._attempt.own_id
                        or (gift.sender_id is None and gift.amount == self._attempt.amount)):
                    return "success", reply
                continue
            if not self._addressed_to_self(reply):
                continue
            if parse_give_question(reply.text) is not None:
                return "question", reply
            return ("refusal" if looks_like_refusal(reply.text) else "other"), reply

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
        bot_text = " Bot said: «{}»".format(outcome.bot_text.strip()[:300]) if outcome.bot_text and outcome.status != "given" else ""
        if outcome.status == "given":
            self._failures = 0
            self._retry_at = None
            self.status = "Auto-give: " + outcome.reason + "."
            self._log("Auto-give: " + outcome.reason + ".", "SUCCESS")
        elif outcome.status == "stopped":
            self._failures += 1
            step = self.backoff_steps[min(self._failures, len(self.backoff_steps)) - 1]
            self._retry_at = self._monotonic() + step
            self.status = "Auto-give stopped: {}. Next try in {} min.".format(outcome.reason, int(step // 60))
            self._log(self.status + bot_text, "WARN")
