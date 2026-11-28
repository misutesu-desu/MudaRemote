"""Main & alts working together (6.0.2): three additions to the alt hand-offs.

1. «Main keeps rolling while an alt can claim» (``main_rolls_while_alt_can_claim``,
   off by default). The main's «no claim, so do not roll / stop rolling» gates
   count a running alt of the same profile that has a claim, or an ``$rt`` it
   may spend, as claim capacity. Good rolls the main cannot claim then go to
   that alt through the alts-claim-main hand-off (``mudae_core.alt_roll_claim``),
   which this option switches on for those rolls. Only here may the alt spend
   its ``$rt`` on a hand-off roll (its own $rt settings and minimum still
   apply). Capacity comes from the alt's live state; unknown = not available.

2. «Accounts take each other's kakera» (``accounts_share_kakera_reacts``, off by
   default). A kakera button on a roll of one account that the roller did not
   take (its own decision: no power, below its power rules, emoji not in its
   lists, paused…) is offered to ONE other running account of the profile
   (main first, then the alts in order); the first that would take it by its
   OWN rules and power clicks it. One decision per button, offered once; a
   timeout means nobody. While this is on, the accounts of a profile do not
   kakera-snipe each other's rolls on their own (the board decides), so a
   button is never clicked twice.

3. Key farming mode (``key_mode``): no account's rolling waits on another
   account. Side-roll turn-taking is skipped, hand-off waits run beside the
   roller's batch, and a harem give holds the main's rolls only while the main
   answers «y».

Pure logic (no Discord); ``mudae_bot.py`` wires it.
"""

import threading

ROLL_ON_SETTING = "main_rolls_while_alt_can_claim"
SHARE_KAKERA_SETTING = "accounts_share_kakera_reacts"

CAPACITY_CLAIM = "claim"
CAPACITY_RT = "rt"

KEY_MODE_LINE = "key mode: accounts roll independently"
# While the main answers «y» to an alt's $give (key mode), its batch holds at most this long.
CONFIRM_HOLD_MAX_SECONDS = 20.0


# ---------------------------------------------------------------------------
# 1. The main keeps rolling while an alt can claim
# ---------------------------------------------------------------------------

def alt_capacity(*, ready=False, paused=False, key_limited=False, same_channel=False, can_be_asked=False,
                 busy_for_main=False, claim_available=None, rt_available=None, auto_rt_enabled=False,
                 rt_only_self_rolls=False):
    """``"claim"``, ``"rt"`` or None for one running alt, from its live state.

    Only a known True counts: a claim/$rt the app has not seen yet is not
    capacity. ``$rt`` counts only when the alt may spend it on someone
    else's roll (Auto $rt on, «$rt only on own rolls» off).
    """
    if not ready or paused or key_limited or not same_channel or not can_be_asked or busy_for_main:
        return None
    if claim_available is True:
        return CAPACITY_CLAIM
    if rt_available is True and auto_rt_enabled and not rt_only_self_rolls:
        return CAPACITY_RT
    return None


def first_capacity(alts):
    """``(label, kind)`` of the alt the main counts on, or None.

    ``alts`` = [(label, kind)] in Account Tokens order. A free claim comes
    before an ``$rt`` (fewer commands)."""
    alts = [(label, kind) for label, kind in (alts or ()) if kind in (CAPACITY_CLAIM, CAPACITY_RT)]
    for label, kind in alts:
        if kind == CAPACITY_CLAIM:
            return label, kind
    return alts[0] if alts else None


def rolls_on(option_on, own_capacity, alt):
    """May the main use its rolls? ``(True, None)`` own capacity, ``(True, alt)``
    thanks to an alt, ``(False, None)`` today's «no claim» behaviour."""
    if own_capacity:
        return True, None
    if option_on and alt:
        return True, alt
    return False, None


def capacity_line(alt):
    """«rolling on — alt 1 has a claim» / «… has $rt» (the logger adds «main: »)."""
    if not alt:
        return "no alt has a claim or $rt left; rolling follows the main's own claim again"
    label, kind = alt
    return "rolling on — {} has {}".format(label or "an alt", "a claim" if kind == CAPACITY_CLAIM else "$rt")


def handoff_enabled(alts_claim_main_rolls, main_rolls_while_alt_can_claim):
    """The alts-claim-main hand-off runs with its own switch or implied by option 1."""
    return bool(alts_claim_main_rolls or main_rolls_while_alt_can_claim)


def alt_may_restore(*, option_on, from_main, claim_available, rt_available, auto_rt_enabled,
                    rt_only_self_rolls, kakera, restore_min_kakera, own_wish, restore_for_wishlist):
    """May this alt spend its ``$rt`` to take a roll the main handed to it?

    Only with option 1 on, only for a roll of the main, only when its claim is
    spent, and only by the alt's own $rt rules (Auto $rt, «$rt only on own
    rolls», «$rt minimum kakera», «$rt ignores the minimum for wishes»)."""
    if not option_on or not from_main or claim_available:
        return False
    if not rt_available or not auto_rt_enabled or rt_only_self_rolls:
        return False
    if own_wish and restore_for_wishlist:
        return True
    try:
        return int(kakera or 0) >= max(0, int(restore_min_kakera or 0))
    except (TypeError, ValueError):
        return False


def rt_taken_line(card):
    """«took X from the main with $rt» (the logger adds «alt 1: »)."""
    return "took ⁨{}⁩ from the main with $rt".format(card)


class ChangeNote:
    """Say a line once per change of a value, never once per check."""

    _UNSET = object()

    def __init__(self, initial=_UNSET):
        self._lock = threading.Lock()
        self._value = initial

    def update(self, value):
        """True when ``value`` differs from the last one (the first value counts as a change)."""
        with self._lock:
            if self._value is not self._UNSET and value == self._value:
                return False
            self._value = value
            return True

    def reset(self):
        with self._lock:
            self._value = self._UNSET


# ---------------------------------------------------------------------------
# 2. Accounts take each other's kakera
# ---------------------------------------------------------------------------

def shareable_kakera_button(name, *, disabled=False, is_sphere=False):
    """A kakera button another account may take: enabled, not a sphere (its
    quota is per account), not purple (Mudae refreshes purple after a claim
    for the claimer; the roller handles it)."""
    clean = str(name or "").rstrip("2")
    if disabled or is_sphere or not clean.startswith("kakera"):
        return False
    return clean != "kakeraP"


def left_kakera_buttons(buttons, roller_has):
    """Buttons the roller did not take: ``[(position, name)]``.

    ``buttons`` = [(position, name, disabled, is_sphere)]; ``roller_has(position,
    name)`` is True when the roller clicked it or is still clicking it."""
    left = []
    for position, name, disabled, is_sphere in buttons or ():
        if not shareable_kakera_button(name, disabled=disabled, is_sphere=is_sphere):
            continue
        try:
            taken = bool(roller_has(position, name))
        except Exception:
            taken = True   # unsure = the roller may still have it: never offer
        if not taken:
            left.append((position, name))
    return left


def share_order(accounts, roller_key):
    """Who is asked, in order: the main first, then the alts as listed.

    ``accounts`` = [(key, account_index)] of the profile's running accounts."""
    others = [(index, position, key) for position, (key, index) in enumerate(accounts or ())
              if key != roller_key]
    return [key for _, _, key in sorted(others, key=lambda item: (_index(item[0]), item[1]))]


def _index(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def kakera_share_blocker(*, ready=True, option_on=True, paused=False, key_limited=False, maintenance=False,
                         inactive_hour=False, same_channel=True, button_found=True, eligible=True,
                         already_has=False, power_known=True, power_ok=True):
    """Why this account does not take the offered kakera button, or None.

    ``eligible`` = the button is in this account's lists for someone else's
    roll; ``power_ok`` = its power and power rules allow the click now
    (without a $dk refill: the share never adds a command)."""
    if not ready:
        return "is not connected"
    if not option_on:
        return "has «take each other's kakera» off"
    if paused:
        return "is paused"
    if key_limited:
        return "is paused at the key limit"
    if maintenance:
        return "Mudae maintenance"
    if inactive_hour:
        return "is in its inactive hours"
    if not same_channel:
        return "does not roll in this channel"
    if not button_found:
        return "the button is gone"
    if already_has:
        return "already clicked it"
    if not eligible:
        return "the emoji is not in its lists"
    if not power_known:
        return "its power is not known yet"
    if not power_ok:
        return "not enough power for its rules"
    return None


def skip_own_snipe_of_sibling_roll(option_on, roller_is_sibling):
    """With sharing on, an account leaves a sibling's kakera to the board."""
    return bool(option_on and roller_is_sibling)


def kakera_taken_line(emoji, roller_label):
    """«took kakera kakeraR on the main's roll» (the logger adds «alt 1: »)."""
    owner = "the main" if str(roller_label or "") in ("", "main", "the main") else str(roller_label)
    return "took kakera {} on {}'s roll".format(emoji, owner)


# ---------------------------------------------------------------------------
# 3. Key farming mode: both keep rolling
# ---------------------------------------------------------------------------

def independent_rolling(key_mode):
    """In key mode every account rolls on its own schedule."""
    return bool(key_mode)


def side_turns_allowed(key_mode):
    """«Alts roll for the main when it finds nothing» takes turns only outside key mode."""
    return not independent_rolling(key_mode)


def handoff_wait_inline(key_mode):
    """Outside key mode the alt waits (≤ 4 s) for the main before its own claim
    paths; in key mode the decision runs beside the roller."""
    return not independent_rolling(key_mode)


def rolling_blocks_taking(key_mode):
    """Outside key mode an account busy with its own batch does not take a
    hand-off roll (A2); in key mode it may (both always roll)."""
    return not independent_rolling(key_mode)


def receiver_holds_rolls(key_mode, *, receiving, confirming):
    """Does a harem give hold the MAIN's (receiver's) own rolls now?

    Outside key mode: for the whole give (as before). In key mode: only while
    the main answers «y»."""
    if independent_rolling(key_mode):
        return bool(confirming)
    return bool(receiving)


def partner_busy_reason(key_mode, *, paused=False, maintenance=False, inactive=False, loot=False,
                        claiming=False, rolling=False, reading_tu=False, sphere_game=False,
                        rolling_for_main=False, own_procedure=None):
    """Why the main cannot take part in an alt's harem give now, or None.

    In key mode the main's own rolling does not count (its rolls hold only
    while it answers «y»)."""
    if paused:
        return "paused"
    if maintenance:
        return "maintenance"
    if inactive:
        return "inactive hours"
    if loot:
        return "loot mode"
    if claiming:
        return "rolling or claiming"
    if rolling and not independent_rolling(key_mode):
        return "rolling or claiming"
    if reading_tu:
        return "reading $tu"
    if sphere_game:
        return "playing a sphere game"
    if rolling_for_main:
        return "rolling for its main"
    return own_procedure or None


def quiet_wait_ignores(key_mode, *, author_id, interaction_user_id, sibling_ids):
    """Key mode: a sibling's message (or the game bot's answer to a sibling's
    slash command) does not make this account wait for a quiet channel."""
    if not independent_rolling(key_mode):
        return False
    siblings = {str(value) for value in (sibling_ids or ()) if value is not None}
    if not siblings:
        return False
    return str(author_id) in siblings or (interaction_user_id is not None and str(interaction_user_id) in siblings)
