"""«Pause on key limit»: what it stops, and saying so where the owner looks.

When one of THIS account's own rolls shows Mudae's key-limit notice and
``pause_on_key_limit`` is on, the account pauses for about an hour
(``mudae_bot`` sets ``client.key_limit_hit``; each client has its own flag and
its own recovery task). This module only decides what the pause covers and
words the line/status, so it can be tested without Discord.

``key_limit_pause_scope``:
  * ``"everything"`` (default, the behaviour before this setting): own rolls,
    $us, $mk, the $tu status pass (and so $daily/$dk/sphere games that hang
    off it), alt hand-offs and gives all wait for the hour.
  * ``"rolls only"``: only this account's own rolls ($wa…, $us, $mk, rolling
    for its main) wait; the $tu status pass, claims, snipes, kakera reactions,
    sphere games and gives go on.
"""

import datetime

SCOPE_EVERYTHING = "everything"
SCOPE_ROLLS_ONLY = "rolls only"
KEY_LIMIT_SCOPES = (SCOPE_EVERYTHING, SCOPE_ROLLS_ONLY)
DEFAULT_SCOPE = SCOPE_EVERYTHING

AREA_ROLLS = "rolls"
AREA_OTHER = "other"


def normalize_scope(value):
    text = str(value or "").strip().lower().replace("_", " ")
    return text if text in KEY_LIMIT_SCOPES else DEFAULT_SCOPE


def validate_key_limit_settings(data):
    value = (data or {}).get("key_limit_pause_scope", DEFAULT_SCOPE)
    if str(value or "").strip().lower().replace("_", " ") not in KEY_LIMIT_SCOPES:
        return ["«When the key limit is reached, pause» must be «everything» or «rolls only»."]
    return []


def key_limit_blocks(client, area=AREA_OTHER):
    """Does this account's key-limit pause stop work of this area right now?"""
    if not getattr(client, "key_limit_hit", False):
        return False
    if area == AREA_ROLLS:
        return True
    return normalize_scope(getattr(client, "key_limit_pause_scope", DEFAULT_SCOPE)) == SCOPE_EVERYTHING


def _clock_text(moment):
    if moment is None:
        return ""
    try:
        local = moment.astimezone() if moment.tzinfo is not None else moment
    except (ValueError, OverflowError, OSError):
        local = moment
    return local.strftime("%H:%M")


def key_limit_pause_text(resume_at=None, scope=DEFAULT_SCOPE):
    """The one line used in the log and in the account's status while paused."""
    what = "rolls paused" if normalize_scope(scope) == SCOPE_ROLLS_ONLY else "paused"
    when = " (resumes about {})".format(_clock_text(resume_at)) if resume_at is not None else ""
    return ("{} for about 1 h — the key limit was reached{}. "
            "Turn off \"Pause on Key Limit\" to keep rolling.").format(what, when)


def key_limit_resumed_text():
    return "key-limit pause is over; rolling again."


def start_key_limit_pause(client, seconds, now=None):
    """Mark this client paused for ``seconds``; return the line to log."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    client.key_limit_hit = True
    client.key_limit_resume_at = now + datetime.timedelta(seconds=max(0.0, float(seconds)))
    client.key_limit_status = key_limit_pause_text(
        client.key_limit_resume_at, getattr(client, "key_limit_pause_scope", DEFAULT_SCOPE))
    return client.key_limit_status


def end_key_limit_pause(client):
    client.key_limit_hit = False
    client.key_limit_resume_at = None
    client.key_limit_status = None
    return key_limit_resumed_text()
