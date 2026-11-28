"""«Claim the best roll when nothing meets the minimum» (``claim_best_when_nothing_qualifies``).

When a round of rolls of a profile (the main and its alts, or a single
account) ends without any roll that the normal rules would claim, the app may
claim the highest-value roll that is still claimable. Off by default.

A roll's claim button stays usable for ``CLAIM_WINDOW_SECONDS`` after the roll
appeared; ``CLAIM_SAFETY_MARGIN_SECONDS`` is kept for the click and its delay.
Because early rolls expire while later ones are still coming:

- the best candidate so far is claimed when it is about to expire, if the
  policy allows a claim now and no account of the profile is still rolling
  (a later roll of the round could still beat it in time); otherwise it is
  let go and the next best is tracked;
- when the round ends (no account rolling, then a short settle), the best
  candidate still inside its window is claimed;
- best = highest kakera value, ties go to the newest roll.

The feature stands down for the whole round as soon as one roll qualified
under the normal rules (or any account of the profile claimed a character in
the round): it never fires while a qualifying claim is still possible.

One decision per round: ``commit`` succeeds once, so the round makes at most
one claim action. Pure logic (no Discord); ``mudae_bot.py`` wires it.
"""

import threading

SETTING = "claim_best_when_nothing_qualifies"
WHEN_SETTING = "claim_best_when"
FLOOR_SETTING = "claim_best_min_kakera"

CLAIM_WINDOW_SECONDS = 45
CLAIM_SAFETY_MARGIN_SECONDS = 6
# After the last batch of the profile ends, wait this long for another account
# of the profile to start its batch (an alt asked to roll for its main).
ROUND_SETTLE_SECONDS = 3.0
# How often the round driver looks at the round.
DRIVER_STEP_SECONDS = 0.5

WHEN_LAST_ROUND = "last round"
WHEN_EVERY_ROUND = "every round"
WHENS = (WHEN_LAST_ROUND, WHEN_EVERY_ROUND)
DEFAULT_WHEN = WHEN_LAST_ROUND
WHEN_CHOICES = {
    WHEN_LAST_ROUND: "Only the last round before the claim reset",
    WHEN_EVERY_ROUND: "Every round",
}

OPEN = "open"
CLAIMING = "claiming"
DONE = "done"


def normalize_when(value):
    text = str(value or "").strip().lower().replace("_", " ")
    if text in (WHEN_EVERY_ROUND, "every", "always"):
        return WHEN_EVERY_ROUND
    return DEFAULT_WHEN


def normalize_floor(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(number, 1_000_000_000))


def validate_best_roll_settings(data):
    data = data or {}
    errors = []
    value = data.get(WHEN_SETTING, DEFAULT_WHEN)
    text = str(value or "").strip().lower().replace("_", " ")
    if text and text not in WHENS:
        errors.append("«Claim the best roll» timing must be «{}» or «{}».".format(*WHENS))
    floor = data.get(FLOOR_SETTING, 0)
    if floor not in (None, ""):
        try:
            if int(floor) < 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("«Claim the best roll» minimum must be a whole number of at least 0.")
    return errors


def claim_deadline(appeared_at, window=CLAIM_WINDOW_SECONDS, margin=CLAIM_SAFETY_MARGIN_SECONDS):
    """The last moment a click may still be started for a roll (monotonic seconds)."""
    return float(appeared_at) + float(window) - float(margin)


def is_last_round(*, now, claim_reset_at, next_batches):
    """Will no further roll batch of the profile finish before the claim reset?

    ``now`` and ``claim_reset_at`` are comparable times (datetimes or
    seconds); ``next_batches`` is one ``(start, seconds)`` per account of the
    profile that rolls: the start of its next batch (its roll reset) and how
    long a batch takes. An unknown claim reset or an unknown start is not
    «the last round» (the safer answer: no claim).
    """
    if claim_reset_at is None or now is None or claim_reset_at <= now:
        return False
    for start, seconds in next_batches:
        if start is None:
            return False
        finish = start + seconds if seconds else start
        if finish < claim_reset_at:
            return False
    return True


def claimer_order(roller_key, main_key, alt_keys):
    """Who is asked to claim: the roller, then the main, then the alts in order."""
    order = []
    for key in [roller_key, main_key, *list(alt_keys or ())]:
        if key is not None and key not in order:
            order.append(key)
    return order


def choose_claimer(order, why_not):
    """The first account in ``order`` that may claim now (``why_not(key)`` → None), or None."""
    for key in order:
        try:
            reason = why_not(key)
        except Exception:
            reason = "could not be checked"
        if reason is None:
            return key
    return None


class Candidate:
    __slots__ = ("message_id", "card", "kakera", "roller_key", "roller_label", "channel_id", "appeared_at")

    def __init__(self, message_id, card, kakera, roller_key, roller_label, channel_id, appeared_at):
        self.message_id = message_id
        self.card = str(card or "")
        try:
            self.kakera = int(kakera or 0)
        except (TypeError, ValueError):
            self.kakera = 0
        self.roller_key = roller_key
        self.roller_label = str(roller_label or "")
        self.channel_id = channel_id
        self.appeared_at = float(appeared_at)

    @property
    def deadline(self):
        return claim_deadline(self.appeared_at)

    def rank(self):
        return (self.kakera, self.appeared_at)


class Decision:
    """What the driver should do now.

    kind: ``wait`` (nothing yet), ``claim`` (commit and claim ``candidate``),
    ``let_go`` (``candidate`` expired unclaimed), ``below_floor``,
    ``not_now`` (round over, the policy does not allow a claim), ``stand_down``
    (a roll qualified normally), ``empty`` (round over, nothing to claim),
    ``idle`` (no open round).
    """

    __slots__ = ("kind", "candidate", "reason")

    def __init__(self, kind, candidate=None, reason=""):
        self.kind = kind
        self.candidate = candidate
        self.reason = reason

    def __repr__(self):
        return "Decision({!r}, {!r})".format(self.kind, getattr(self.candidate, "card", None))


class _Round:
    __slots__ = ("state", "candidates", "qualified", "driver", "quiet_since", "below_floor", "number",
                 "claim_reason", "claimed")

    def __init__(self, number):
        self.number = number
        self.state = OPEN
        self.candidates = {}
        self.qualified = ""
        self.driver = None
        self.quiet_since = None
        self.below_floor = None
        self.claim_reason = ""
        self.claimed = False


class BestRollBoard:
    """Process-wide, thread-safe rounds, one per profile (``profile_id``)."""

    def __init__(self, *, settle_seconds=ROUND_SETTLE_SECONDS):
        self._lock = threading.Lock()
        self._rounds = {}
        self._numbers = {}
        self.settle_seconds = float(settle_seconds)

    def _open(self, profile):
        current = self._rounds.get(profile)
        if current is None or current.state == DONE:
            number = self._numbers.get(profile, 0) + 1
            self._numbers[profile] = number
            current = _Round(number)
            self._rounds[profile] = current
        return current

    def round_number(self, profile):
        with self._lock:
            current = self._rounds.get(profile)
            return current.number if current is not None else 0

    def state(self, profile):
        with self._lock:
            current = self._rounds.get(profile)
            return current.state if current is not None else None

    def _claim_driver(self, current, driver_key):
        if current.driver is None and current.state == OPEN:
            current.driver = driver_key
            return True
        return False

    def add(self, profile, candidate, *, floor=0, driver_key=None):
        """Keep a roll that did not qualify. True when the caller must start the round driver."""
        with self._lock:
            current = self._open(profile)
            if current.state != OPEN:
                return False
            if candidate.kakera < normalize_floor(floor):
                best = current.below_floor
                if best is None or candidate.rank() >= best.rank():
                    current.below_floor = candidate
            else:
                current.candidates[candidate.message_id] = candidate
            current.quiet_since = None
            return self._claim_driver(current, driver_key)

    def mark_qualified(self, profile, why="a roll met the minimum", *, driver_key=None):
        """A roll qualified under the normal rules (or a character was claimed): stand down this round."""
        with self._lock:
            current = self._open(profile)
            if current.state != OPEN:
                return False
            if not current.qualified:
                current.qualified = str(why or "a roll met the minimum")
            current.quiet_since = None
            return self._claim_driver(current, driver_key)

    def note_claimed(self, profile, why="a character was claimed this round"):
        """Any account of the profile claimed a character: an open round stands down (no new round opens)."""
        with self._lock:
            current = self._rounds.get(profile)
            if current is None or current.state != OPEN:
                return False
            if not current.qualified:
                current.qualified = str(why)
            return True

    def discard(self, profile, message_id):
        with self._lock:
            current = self._rounds.get(profile)
            if current is not None:
                current.candidates.pop(message_id, None)

    def step(self, profile, now, *, rolling, policy_allows, exclude=None):
        """One look at the round. ``exclude(candidate)`` → reason to skip it, or None.

        Moves to ``claiming`` itself when it returns ``claim`` (the single
        decision of the round); the caller then calls ``finish``.
        """
        with self._lock:
            current = self._rounds.get(profile)
            if current is None or current.state != OPEN:
                return Decision("idle")
            if current.qualified:
                current.state = DONE
                return Decision("stand_down", reason=current.qualified)
            if rolling:
                current.quiet_since = None
            elif current.quiet_since is None:
                current.quiet_since = now
            # Skip what the rules exclude now (claimed by another account, owned, avoided, …).
            if exclude is not None:
                for message_id, candidate in list(current.candidates.items()):
                    try:
                        reason = exclude(candidate)
                    except Exception:
                        reason = "could not be checked"
                    if reason:
                        current.candidates.pop(message_id, None)
            # Rolls past their window are gone; only the best one is reported.
            ranked = sorted(current.candidates.values(), key=Candidate.rank, reverse=True)
            best = ranked[0] if ranked else None
            best_expired = False
            for candidate in ranked:
                if now >= candidate.deadline:
                    current.candidates.pop(candidate.message_id, None)
                    best_expired = best_expired or candidate is best
            if best_expired:
                # The best so far is about to expire: claim it only when nothing of
                # this round can still come to beat it, else let it go.
                if not rolling and policy_allows:
                    current.state = CLAIMING
                    return Decision("claim", best, "about to expire")
                return Decision("let_go", best, "expired")
            settled = (not rolling and current.quiet_since is not None
                       and now - current.quiet_since >= self.settle_seconds)
            if not settled:
                return Decision("wait")
            live = sorted(current.candidates.values(), key=Candidate.rank, reverse=True)
            if not live:
                current.state = DONE
                if current.below_floor is not None:
                    return Decision("below_floor", current.below_floor, "below your floor")
                return Decision("empty")
            if not policy_allows:
                current.state = DONE
                return Decision("not_now", live[0], "not the last round before the claim reset")
            current.state = CLAIMING
            return Decision("claim", live[0], "round over")

    def finish(self, profile, claimed, reason=""):
        """After the one claim action of the round (sent or not): the round is done."""
        with self._lock:
            current = self._rounds.get(profile)
            if current is None or current.state != CLAIMING:
                return False
            current.state = DONE
            current.claimed = bool(claimed)
            current.claim_reason = str(reason or "")
            return True

    def close(self, profile):
        with self._lock:
            current = self._rounds.get(profile)
            if current is not None and current.state == OPEN:
                current.state = DONE

    def is_open(self, profile):
        return self.state(profile) == OPEN


def roller_text(label):
    text = str(label or "")
    return "the main" if text in ("", "main") else text


def claiming_line(card, kakera, roller_label):
    return "nothing met the minimum this round — claiming the best roll, ⁨{}⁩ ({} ka), rolled by {}".format(
        card, kakera, roller_text(roller_label))


def let_go_line(card, kakera):
    return "nothing met the minimum this round — let ⁨{}⁩ ({} ka) go: expired".format(card, kakera)


def below_floor_line(card, kakera, floor):
    return "nothing met the minimum this round — skipped ⁨{}⁩ ({} ka): below your floor of {}".format(
        card, kakera, floor)


def not_now_line(card, kakera):
    return "nothing met the minimum this round — not claiming ⁨{}⁩ ({} ka): not the last round before the claim reset".format(
        card, kakera)


def nobody_line(card, kakera, reason):
    return "nothing met the minimum this round — not claiming ⁨{}⁩ ({} ka): {}".format(card, kakera, reason)
