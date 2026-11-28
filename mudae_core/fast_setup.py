"""«Fast setup»: send one ``$ta …`` message once per account, then never again.

The setting ``fast_setup`` (per profile, main and side) asks for it. The done
mark lives in the account state file under the account's stable key, so it
survives restarts, renames, config reloads and live apply on Android; the
setting itself then reads as off. «Send again» re-arms it on purpose: it
raises ``fast_setup_round`` (a counter in the preset) and switches the setting
on, and a round that has no done mark is due once more.
"""

import datetime

# The owner's exact message (arranges $tu so kakerastock and spherestock appear).
FAST_SETUP_MESSAGE = (
    "$ta claim rolls daily jump kakerareact kakerapower kakerainfo kakerastock "
    "jump rt dk vote jump oh spherestock perk9b perk8 perk8b perk9 omegakeys shop6"
)

FAST_SETUP_SECTION = "fast_setup"
FAST_SETUP_DEFAULTS = {"fast_setup": False, "fast_setup_round": 0}


def fast_setup_message(prefix="$"):
    """The message with the account's Mudae prefix (identical for the default ``$``)."""
    prefix = str(prefix or "$")
    return prefix + FAST_SETUP_MESSAGE[1:]


def setup_round(value) -> int:
    try:
        if isinstance(value, bool):
            return 0
        return max(0, int(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def validate_fast_setup_settings(data):
    errors = []
    value = (data or {}).get("fast_setup_round", 0)
    if isinstance(value, bool):
        errors.append("Fast setup round must be a whole number of 0 or more.")
    else:
        try:
            if int(str(value).strip()) < 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("Fast setup round must be a whole number of 0 or more.")
    return errors


class FastSetup:
    """Decides and records the one-time send for one account."""

    def __init__(self, store, key):
        self.store = store
        self.key = key

    def record(self):
        return self.store.get(self.key, FAST_SETUP_SECTION)

    def is_done(self, round_number) -> bool:
        record = self.record()
        return bool(record) and setup_round(record.get("round")) >= setup_round(round_number)

    def is_due(self, enabled, round_number) -> bool:
        return bool(enabled) and not self.is_done(round_number)

    def effective_enabled(self, enabled, round_number) -> bool:
        """What the setting shows: off once this round was sent."""
        return self.is_due(enabled, round_number)

    def mark(self, round_number, state="sent", when=None):
        when = when or datetime.datetime.now(datetime.timezone.utc)
        self.store.put(self.key, FAST_SETUP_SECTION, {
            "round": setup_round(round_number), "state": state, "at": when.isoformat(),
        })

    def clear(self):
        self.store.put(self.key, FAST_SETUP_SECTION, None)

    async def run(self, enabled, round_number, send, channel, prefix="$", log=None):
        """Send the message once if due. ``send`` returns truthy when it was sent.

        The mark is written BEFORE sending, so a crash mid-send can never cause a
        second message; a send that definitely did not happen (``send`` returned
        False) removes the mark again so it is tried later. Returns True when sent.
        """
        if not self.is_due(enabled, round_number):
            return False
        previous = self.record()
        self.mark(round_number, state="sending")
        try:
            sent = await send(channel, fast_setup_message(prefix))
        except Exception as exc:  # outcome unknown: never risk sending twice
            self.mark(round_number, state="uncertain")
            if log:
                log("Fast setup: sending failed ({}); it will not be sent again automatically. "
                    "Use «Send again» if it did not arrive.".format(type(exc).__name__), "WARN")
            return False
        if not sent:
            if previous is None:
                self.clear()
            else:
                self.store.put(self.key, FAST_SETUP_SECTION, previous)
            if log:
                log("Fast setup: not sent now (paused, inactive hours or channel unavailable); will try later.", "INFO")
            return False
        self.mark(round_number, state="sent")
        if log:
            log("Fast setup sent once in the command channel; the setting is now off.", "INFO")
        return True


def rearm(preset_data):
    """«Send again»: switch the setting on with a new round (mutates and returns the preset)."""
    preset_data["fast_setup_round"] = setup_round(preset_data.get("fast_setup_round", 0)) + 1
    preset_data["fast_setup"] = True
    return preset_data
