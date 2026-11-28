"""Main and alt accounts of one profile: who is who, and why an account waits.

A profile's primary token (``token``) is the MAIN account. The extra entries
of its «Account Tokens (multi-account)» list are its ALTS (side accounts), in
the order they are listed. Every running account knows its position from
``_account_index`` (1 = the primary token), set where the token list is
expanded (``runtime.prepare_active_presets`` and
``bot_runtime.RuntimeManager.start_instances_from_preset``), so the role is a
fact of the profile, not a setting.

Legacy path (6.0.0): a whole profile explicitly saved with
``account_role = "side"`` AND a ``main_profile_id`` stays a side of that other
profile, exactly as before. Nothing else in the stored role is used any more,
and no stored key is ever deleted.

This module is pure (no Discord); ``mudae_bot.py`` and the coordinator use it.
"""

import re
import threading

ROLE_MAIN = "main"
ROLE_SIDE = "side"

SIDE_KIND_ALT = "alt"        # an extra token of the same profile
SIDE_KIND_LEGACY = "legacy"  # a separate profile marked side with a main profile id

NO_ALTS_HINT = "Add alt tokens under Account Tokens to use this"
ALTS_GROUP_INTRO = (
    "One profile, several accounts: the first token is the main; every extra token under "
    "«Account Tokens (multi-account)» is an alt. Set these once here: alts give to the main and "
    "roll for it; the main itself never gives."
)
TOKENS_FIELD_DESCRIPTION = "Extra tokens here are your alts. The first token (above) is the main."


def _value(source, name, default=None):
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _index(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 1
    return number if number >= 1 else 1


def is_legacy_side(stored_role, main_profile_id):
    """A separate profile saved as a side of another profile (the 6.0.0 way)."""
    return str(stored_role or "") == ROLE_SIDE and bool(str(main_profile_id or "").strip())


def side_kind(account_index=1, stored_role=ROLE_MAIN, main_profile_id=""):
    """``"legacy"``, ``"alt"`` or None (a main / ordinary account)."""
    if is_legacy_side(stored_role, main_profile_id):
        return SIDE_KIND_LEGACY
    if _index(account_index) > 1:
        return SIDE_KIND_ALT
    return None


def account_role(account_index=1, stored_role=ROLE_MAIN, main_profile_id=""):
    """The effective role: the primary token is the main, extra tokens are alts."""
    return ROLE_SIDE if side_kind(account_index, stored_role, main_profile_id) else ROLE_MAIN


def _stored_role_of(source):
    if isinstance(source, dict):
        return source.get("account_role", ROLE_MAIN)
    return getattr(source, "stored_account_role", getattr(source, "account_role", ROLE_MAIN))


def _index_of(source):
    if isinstance(source, dict):
        return source.get("_account_index", 1)
    return getattr(source, "account_index", 1)


def account_role_for(source):
    """The single source of truth for a running account (client) or a preset dict."""
    return account_role(_index_of(source), _stored_role_of(source), _value(source, "main_profile_id", ""))


def side_kind_for(source):
    return side_kind(_index_of(source), _stored_role_of(source), _value(source, "main_profile_id", ""))


def alt_number(account_index):
    """1 for the first extra token, 2 for the next…; 0 for the primary token."""
    return max(0, _index(account_index) - 1)


def account_label(account_index=1, account_count=1, stored_role=ROLE_MAIN, main_profile_id=""):
    """«main» / «alt N» when a profile runs several accounts, else "" (no label needed)."""
    if is_legacy_side(stored_role, main_profile_id):
        return ""
    try:
        count = int(account_count)
    except (TypeError, ValueError):
        count = 1
    index = _index(account_index)
    if count <= 1 and index <= 1:
        return ""
    return "main" if index == 1 else "alt {}".format(index - 1)


def account_label_for(source):
    count = source.get("_account_count", 1) if isinstance(source, dict) else getattr(source, "account_count", 1)
    return account_label(_index_of(source), count, _stored_role_of(source), _value(source, "main_profile_id", ""))


_TAG_RE = re.compile(r"^\[[^\]]+\]\s*")


def labelled_message(label, message):
    """Put the account label in front of a log message, after a leading «[TAG] »."""
    text = str(message)
    if not label:
        return text
    match = _TAG_RE.match(text)
    head = text[:match.end()] if match else ""
    return "{}{}: {}".format(head, label, text[len(head):])


def perk10_enabled(role, kind, auto_perk10, side_perk10):
    """Perk 10 on the main follows ``auto_perk10``; an alt also needs ``side_perk10``.

    A legacy side profile keeps its own ``auto_perk10`` as before.
    """
    if not auto_perk10:
        return False
    if role != ROLE_SIDE or kind == SIDE_KIND_LEGACY:
        return True
    return bool(side_perk10)


def perk10_enabled_for(source):
    return perk10_enabled(
        account_role_for(source), side_kind_for(source),
        bool(_value(source, "auto_perk10", False)), bool(_value(source, "side_perk10", False)),
    )


def _split_tokens(value):
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = re.split(r"[\s,;]+", str(value or ""))
    return [str(item).strip() for item in items if str(item or "").strip()]


def alt_count(primary="", tokens=(), additional=""):
    """How many alts a profile has: distinct tokens besides the primary one.

    Desktop stores ``tokens`` as [primary, alt1, …]; Android stores the extra
    tokens only. Both count the same. Values are compared, never shown.
    """
    seen = []
    first = str(primary or "").strip()
    for item in _split_tokens(tokens) + _split_tokens(additional):
        if item not in seen:
            seen.append(item)
    if not first and seen:
        first = seen[0]
    return len([item for item in seen if item != first])


def profile_chip_text(count):
    """Android profile chip: «Main + N alts»."""
    try:
        number = int(count)
    except (TypeError, ValueError):
        number = 0
    if number <= 0:
        return ""
    return "Main + {} alt{}".format(number, "" if number == 1 else "s")


# ---------------------------------------------------------------------------
# Why a roll batch does not start (and saying it once per change)
# ---------------------------------------------------------------------------

def roll_batch_blocker(*, paused=False, key_limit_hit=False, maintenance=False, rolling_for_main=False,
                       giving_kakera=False, giving_harem=False, main_receiving_harem=False,
                       giving_spheres=False, upgrading_perk10=False):
    """Why this account's own roll batch waits, or None when it may roll.

    Only this account's own state counts, plus a harem give the main itself
    must answer (``main_receiving_harem``). Used to say why an account waits.
    """
    if paused:
        return "paused"
    if key_limit_hit:
        return "key limit reached (pausing 1h)"
    if maintenance:
        return "Mudae maintenance"
    if rolling_for_main:
        return "rolling for its main"
    if giving_kakera:
        return "a kakera give to the main is in progress"
    if giving_harem:
        return "a harem give is in progress"
    if main_receiving_harem:
        return "answering an alt's harem give"
    if giving_spheres:
        return "a sphere give to the main is in progress"
    if upgrading_perk10:
        return "a perk-10 upgrade is in progress"
    return None


class IdleNote:
    """Say why an account waits once per change, never once per check."""

    def __init__(self):
        self._lock = threading.Lock()
        self._reason = None

    def update(self, reason):
        """Return the line to log when the reason changed, else None."""
        with self._lock:
            if reason == self._reason:
                return None
            self._reason = reason
        if reason is None:
            return None
        return "waiting — {}".format(reason)

    def clear(self):
        """The account works again; a later wait is announced afresh."""
        with self._lock:
            had = self._reason is not None
            self._reason = None
        return had

    @property
    def reason(self):
        return self._reason

