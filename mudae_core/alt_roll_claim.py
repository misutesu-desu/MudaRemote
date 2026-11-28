"""«Main claims good rolls made by its alts» (``main_claims_alt_rolls``).

When an alt (an extra token of a profile) rolls a character, the main of the
same profile may claim it instead, judged with the MAIN's own claim rules and
live claim state, as if the main had rolled it. Off by default.

One decision point: the alt opens an offer on the process-wide
``AltRollBoard`` and waits; only the main may move it from ``pending`` to
``taking`` (it then clicks), and only the alt may move it to ``gave_up`` (on
timeout). Both moves happen under one lock, so at most one of the two ever
clicks the card. Once the main committed, the alt never claims that card.

Sub-option ``main_claims_alt_rolls_mode``:
- «when the alt would not claim» (default): the main only takes what the alt
  was going to pass on or cannot claim;
- «prefer the main»: the main takes anything good for it;
- «smart» (default for new presets): whoever can claim takes it, whoever rolled
  it. Any roll of any account of the profile that is good for ANY account's
  own rules goes to exactly one account with a claim (``smart_ranking``): the
  accounts it is good for first (the main, then the roller, then the alts in
  order), then the others with a claim, so the roll is not lost. In this mode
  ``main_claims_alt_rolls`` and ``alts_claim_main_rolls`` both count as on
  when either is on.

Mirror, ``alts_claim_main_rolls`` (off by default): a good roll of the MAIN
that the main will not or cannot claim goes to ONE alt, the first in list
order whose claim and state allow it (``AltRollBoard.offer_in_turn``, the same
board and judge with the roles swapped). A roll is offered once, so the two
options together never ping-pong.

Pure logic (no Discord); ``mudae_bot.py`` wires it.
"""

from collections import OrderedDict
import threading
import time

SETTING = "main_claims_alt_rolls"
MODE_SETTING = "main_claims_alt_rolls_mode"
# The mirror: an alt claims a good roll of the main that the main will not or
# cannot claim (the main always has priority on its own rolls). No mode.
MIRROR_SETTING = "alts_claim_main_rolls"
# The main does not hand off a roll it keeps for its coming claim reset.
KEEP_FOR_RESET_SECONDS = 20.0
MODE_WHEN_ALT_PASSES = "when the alt would not claim"
MODE_PREFER_MAIN = "prefer the main"
MODE_SMART = "smart"
MODES = (MODE_WHEN_ALT_PASSES, MODE_PREFER_MAIN, MODE_SMART)
DEFAULT_MODE = MODE_SMART
MODE_CHOICES = {
    MODE_WHEN_ALT_PASSES: "When the alt would not claim (the alt keeps its own good rolls)",
    MODE_PREFER_MAIN: "Prefer the main (the main takes anything good for it; alts keep their claims)",
    MODE_SMART: "Smart (whoever can claim takes it, whoever rolled it)",
}

# How long the alt waits for the main's decision, then for the click result.
DECISION_WAIT_SECONDS = 4.0
RESULT_WAIT_EXTRA_SECONDS = 30.0
# How long the main looks for its own copy of the roll message.
MESSAGE_LOOKUP_SECONDS = 1.5

PENDING = "pending"
TAKING = "taking"
CLAIMED = "claimed"     # the main sent its claim click / reaction
FAILED = "failed"       # the main committed but could not send a claim
PASSED = "passed"       # the main does not want it or cannot claim it
GAVE_UP = "gave_up"     # the alt stopped waiting before the main committed

ALT_MAY_CLAIM = frozenset((PASSED, FAILED, GAVE_UP))
TERMINAL = frozenset((CLAIMED, FAILED, PASSED, GAVE_UP))


def normalize_mode(value):
    text = str(value or "").strip().lower().replace("_", " ")
    if text in ("prefer the main", "prefer main"):
        return MODE_PREFER_MAIN
    if text == MODE_WHEN_ALT_PASSES:
        return MODE_WHEN_ALT_PASSES
    return DEFAULT_MODE


def validate_alt_roll_claim_settings(data):
    value = (data or {}).get(MODE_SETTING, DEFAULT_MODE)
    text = str(value or "").strip().lower().replace("_", " ")
    if text and text not in MODES and text != "prefer main":
        return ["«Main claims good rolls made by its alts» mode must be «{}», «{}» or «{}».".format(*MODES)]
    return []


def is_smart(mode):
    return normalize_mode(mode) == MODE_SMART


def smart_on(mode, main_claims_alt_rolls, alts_claim_main_rolls):
    """Smart mode decides when either direction switch is on (both then count as on)."""
    return is_smart(mode) and bool(main_claims_alt_rolls or alts_claim_main_rolls)


def main_should_be_asked(mode, alt_would_claim):
    """Does the alt offer this roll to its main at all? (Old modes; smart uses ``smart_ranking``.)"""
    if normalize_mode(mode) in (MODE_PREFER_MAIN, MODE_SMART):
        return True
    return not alt_would_claim


def smart_ranking(*, roller, order, good, can_claim, main_key=None):
    """Smart mode: the accounts that may claim one roll, best first ([] = nobody).

    ``roller`` rolled it; ``order`` = every account of the profile, the main
    first then the alts in Account Tokens order; ``good[key]`` = the roll is
    good under that account's OWN rules; ``can_claim[key]`` = that account has
    a claim now (or its existing rules would use $rt). Only one account ever
    claims: the first that commits on the board, asked in this order.

    1. an account without a claim is never chosen; nothing when the roll is
       good for nobody;
    2. the accounts it is good for come first, then the other accounts with a
       claim (so a good roll is not lost);
    3. inside each group: the main, then the roller, then the alts in order.
    """
    keys = list(dict.fromkeys(list(order or ()) + ([roller] if roller is not None else [])))
    good = good or {}
    can_claim = can_claim or {}
    if not any(good.get(key) for key in keys):
        return []
    main = main_key if main_key is not None else (keys[0] if keys else None)

    def rank(key):
        return (0 if key == main else 1 if key == roller else 2, keys.index(key))

    candidates = [key for key in keys if can_claim.get(key)]
    first = sorted((key for key in candidates if good.get(key)), key=rank)
    second = sorted((key for key in candidates if not good.get(key)), key=rank)
    return first + second


def smart_reason(chosen, *, roller, good, can_claim, labels=None):
    """Why ``chosen`` takes the roll, for the log: «alt 1 has no claim», …"""
    labels = labels or {}
    good = good or {}
    can_claim = can_claim or {}

    def name(key):
        return labels.get(key) or str(key)

    parts = []
    if chosen != roller:
        if not can_claim.get(roller):
            parts.append("{} has no claim".format(name(roller)))
        elif good.get(roller) and good.get(chosen):
            parts.append("good for both, {} comes first".format(name(chosen)))
        elif not good.get(roller):
            parts.append("not good for {}".format(name(roller)))
    if not good.get(chosen):
        owners = [key for key in labels if good.get(key) and key != chosen] or [
            key for key in good if good.get(key) and key != chosen]
        if owners:
            parts.append("good for {}, which cannot claim it".format(" and ".join(name(key) for key in owners)))
    return "; ".join(parts) or "good for {}".format(name(chosen))


def smart_line(card, roller_label, taker_label, reason):
    """«⁨X⁩ (rolled by alt 1) — claimed by the main (smart: alt 1 has no claim)»."""
    return "\u2068{}\u2069 (rolled by {}) \u2014 claimed by {} (smart: {})".format(
        card, roller_label or "an alt", taker_label or "an account", reason)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def card_interest(*, name, wishlist=(), avoid_list=(), series_hit=False, wished=False,
                  claim_rank=0, like_rank=0, max_claim_rank=0, max_like_rank=0,
                  kakera=0, min_kakera=0):
    """``(wanted, why)`` for one character with one account's claim rules.

    The same tests the account uses for its own rolls: wishlist, series
    wishlist, «wished by» line, rank limits, then the minimum kakera value.
    """
    key = str(name or "").strip().lower()
    if key in {str(item).strip().lower() for item in (avoid_list or ())}:
        return False, "on the avoid list"
    if key and key in {str(item).strip().lower() for item in (wishlist or ())}:
        return True, "wishlist"
    if series_hit:
        return True, "series wishlist"
    if wished:
        return True, "wished"
    claim_rank, like_rank = _int(claim_rank), _int(like_rank)
    if _int(max_claim_rank) > 0 and 0 < claim_rank <= _int(max_claim_rank):
        return True, "claim rank #{}".format(claim_rank)
    if _int(max_like_rank) > 0 and 0 < like_rank <= _int(max_like_rank):
        return True, "like rank #{}".format(like_rank)
    kakera, min_kakera = _int(kakera), _int(min_kakera)
    if kakera >= min_kakera:
        return True, "min kakera, {} ka".format(kakera)
    return False, "below min kakera ({} < {} ka)".format(kakera, min_kakera)


def is_value_reason(why):
    return str(why or "").startswith("min kakera,")


def claim_blocker(*, ready=True, paused=False, key_limited=False, maintenance=False,
                  inactive_hour=False, claim_available=True, key_mode_kakera_only=False,
                  claiming=False, rolling=False, judging_sides=False, lurking=False, why=""):
    """Why the main cannot take a wanted card now, or None.

    Never spends $rt (it would send a command): only the normal claim counts.
    While Lurker holds the main's rolls for its claim hour, only wishes are
    taken (the main's snipes act the same way); value-only cards wait.
    """
    if not ready:
        return "is not connected"
    if paused:
        return "is paused"
    if key_limited:
        return "is paused at the key limit"
    if maintenance:
        return "Mudae maintenance"
    if inactive_hour:
        return "is in its inactive hours"
    if key_mode_kakera_only:
        return "is in key mode (kakera only)"
    if not claim_available:
        return "has no claim now"
    if claiming:
        return "is busy claiming"
    if rolling:
        return "is rolling its own batch"
    if judging_sides:
        return "is judging a side's rolls"
    if lurking and is_value_reason(why):
        return "waits for its claim hour (Lurker)"
    return None


class Offer:
    """One roll offered by the account that rolled it (offerer) to one other
    account of the same profile (taker). ``candidates`` are every account that
    may be asked for this roll; none of them claims it outside the hand-off."""

    __slots__ = ("message_id", "taker_key", "offerer_key", "offerer_label", "card", "state", "reason",
                 "opened", "candidates", "asked")

    def __init__(self, message_id, taker_key, offerer_key, offerer_label, card, candidates):
        self.message_id = message_id
        self.taker_key = taker_key
        self.offerer_key = offerer_key
        self.offerer_label = offerer_label
        self.card = card
        self.state = PENDING
        self.reason = ""
        self.opened = time.monotonic()
        self.candidates = frozenset(candidates or ()) | {taker_key}
        self.asked = [taker_key]

    # Old names (alt → main direction), kept for readability of the alt path.
    @property
    def main_key(self):
        return self.taker_key

    @property
    def alt_key(self):
        return self.offerer_key


class AltRollBoard:
    """Process-wide, thread-safe record of rolls offered between the accounts
    of one profile (alt → main and main → alts). A roll is offered once: a
    taker that passes may hand it to the next candidate, never back."""

    def __init__(self, limit=300):
        self._lock = threading.Lock()
        self._offers = OrderedDict()
        self._limit = max(10, int(limit))

    def open(self, message_id, *, main_key=None, alt_key=None, alt_label="", card="",
             taker_key=None, offerer_key=None, offerer_label=None, candidates=()):
        """A new offer, or None when this roll was already offered (by anyone)."""
        taker = taker_key if taker_key is not None else main_key
        offerer = offerer_key if offerer_key is not None else alt_key
        label = offerer_label if offerer_label is not None else alt_label
        with self._lock:
            if message_id in self._offers:
                return None
            offer = Offer(message_id, taker, offerer, label, card, candidates)
            self._offers[message_id] = offer
            while len(self._offers) > self._limit:
                self._offers.popitem(last=False)
            return offer

    def pass_on(self, message_id, offerer_key, next_taker_key):
        """After a pass, offer the same roll to the next candidate (once each)."""
        with self._lock:
            offer = self._offers.get(message_id)
            if (offer is None or offer.offerer_key != offerer_key or offer.state != PASSED
                    or next_taker_key in offer.asked or next_taker_key not in offer.candidates):
                return False
            offer.taker_key = next_taker_key
            offer.asked.append(next_taker_key)
            offer.state = PENDING
            offer.reason = ""
            return True

    def get(self, message_id):
        with self._lock:
            return self._offers.get(message_id)

    def state(self, message_id):
        with self._lock:
            offer = self._offers.get(message_id)
            return offer.state if offer is not None else None

    def blocks_claim(self, message_id, account_key):
        """True when ``account_key`` must not claim this roll outside the hand-off.

        The taker may claim only once it committed; the offerer may claim again
        only after the taker passed, failed or was given up on; every other
        candidate never (one decision point)."""
        with self._lock:
            offer = self._offers.get(message_id)
            if offer is None or account_key is None:
                return False
            if account_key == offer.taker_key and offer.state == TAKING:
                return False
            if account_key == offer.offerer_key:
                return offer.state in (PENDING, TAKING, CLAIMED)
            return account_key in offer.candidates

    def main_commit(self, message_id, main_key):
        """The taker commits (it will click); alias kept for the alt → main path."""
        with self._lock:
            offer = self._offers.get(message_id)
            if offer is None or offer.taker_key != main_key or offer.state != PENDING:
                return False
            offer.state = TAKING
            return True

    def main_pass(self, message_id, main_key, reason=""):
        with self._lock:
            offer = self._offers.get(message_id)
            if offer is None or offer.taker_key != main_key or offer.state != PENDING:
                return False
            offer.state = PASSED
            offer.reason = str(reason or "")
            return True

    def main_finish(self, message_id, main_key, claimed, reason=""):
        with self._lock:
            offer = self._offers.get(message_id)
            if offer is None or offer.taker_key != main_key or offer.state != TAKING:
                return False
            offer.state = CLAIMED if claimed else FAILED
            offer.reason = str(reason or "")
            return True

    def alt_give_up(self, message_id, alt_key):
        """The offerer stops waiting. True when the taker can no longer take it."""
        with self._lock:
            offer = self._offers.get(message_id)
            if offer is None:
                return True
            if offer.offerer_key != alt_key:
                return False
            if offer.state == PENDING:
                offer.state = GAVE_UP
                offer.reason = "no answer in time"
                return True
            return offer.state in ALT_MAY_CLAIM

    # Role-neutral names for the same moves.
    taker_commit = main_commit
    taker_pass = main_pass
    taker_finish = main_finish
    offerer_give_up = alt_give_up

    async def wait_for_main(self, message_id, alt_key, *, sleep, decision_timeout=DECISION_WAIT_SECONDS,
                            result_timeout=RESULT_WAIT_EXTRA_SECONDS, step=0.1):
        """The offerer waits for the taker; returns the final state.

        ``sleep(seconds)`` is the offerer's interruptible delay (False = stop).
        ``taking`` is returned when the taker committed but did not finish in
        time: the offerer (and everyone else) must then leave the card alone.
        """
        waited = 0.0
        while True:
            state = self.state(message_id)
            if state is None:
                return GAVE_UP
            if state in TERMINAL:
                return state
            if state == PENDING and waited >= decision_timeout:
                if self.alt_give_up(message_id, alt_key):
                    return self.state(message_id) or GAVE_UP
                continue
            if state == TAKING and waited >= decision_timeout + result_timeout:
                return TAKING
            keep_going = await sleep(step)
            waited += step
            if keep_going is False:
                if self.alt_give_up(message_id, alt_key):
                    return self.state(message_id) or GAVE_UP
                state = self.state(message_id)
                return state if state in TERMINAL else TAKING

    wait_for_taker = wait_for_main

    async def offer_in_turn(self, message_id, *, offerer_key, offerer_label, card, takers, start, sleep,
                            decision_timeout=DECISION_WAIT_SECONDS, result_timeout=RESULT_WAIT_EXTRA_SECONDS,
                            step=0.1, candidates=None, deadline=None, clock=time.monotonic):
        """Offer one roll to ``takers`` in order until one claims it.

        ``start(taker_key)`` schedules that taker's judge (False = it could not
        be asked). Only a PASS moves on to the next taker; a timeout, a failed
        claim or a commit still running ends the round (nobody else tries).
        ``candidates`` (smart mode): every account that must leave the roll to
        the hand-off while it is open (the takers always are). ``deadline``
        (``clock()`` time): no further taker is asked after it (claim window).
        The offerer may be one of the takers (it then claims its own roll
        through the same judge). Returns ``(state, taker_key)``.
        """
        takers = list(takers)
        if not takers:
            return None, None
        if self.open(message_id, taker_key=takers[0], offerer_key=offerer_key, offerer_label=offerer_label,
                     card=card, candidates=list(takers) + list(candidates or ())) is None:
            return None, None
        for index, taker in enumerate(takers):
            if index and deadline is not None and clock() >= deadline:
                break
            if index and not self.pass_on(message_id, offerer_key, taker):
                break
            try:
                started = bool(start(taker))
            except Exception:
                started = False
            if not started:
                self.main_pass(message_id, taker, "could not be asked")
                continue
            state = await self.wait_for_main(message_id, offerer_key, sleep=sleep, decision_timeout=decision_timeout,
                                             result_timeout=result_timeout, step=step)
            if state != PASSED:
                return state, taker
        return self.state(message_id), None


def taken_line(card, roller_label, why):
    """The taker's log line: «claiming X rolled by alt 1 (wishlist)» / «… by the main (…)»."""
    return "claiming \u2068{}\u2069 rolled by {} ({})".format(card, roller_label or "its alt", why)


def left_line(card, taker_label="the main"):
    """The roller's log line: «left X for the main» / «left X for alt 1»."""
    return "left \u2068{}\u2069 for {}".format(card, taker_label or "the main")


def main_will_not_claim(*, key_limited=False, key_mode_kakera_only=False, claim_available=True,
                        restore_usable=False, keeping_for_reset=False):
    """Why the main gives up a good roll of its own, or None when it keeps it."""
    if keeping_for_reset:
        return None
    if key_limited:
        return "the main is paused at the key limit"
    if key_mode_kakera_only:
        return "the main is in key mode (kakera only)"
    if not claim_available and not restore_usable:
        return "the main has no claim now"
    return None


def roller_label_for(label):
    """How a taker names the roller: «alt 1», or «the main» for the main."""
    return "the main" if str(label or "") in ("", "main") else str(label)


def not_taken_line(card, alt_label, reason):
    return "not taking ⁨{}⁩ rolled by {}: {}".format(card, alt_label or "its alt", reason)
