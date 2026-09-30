"""Turn the bot's log lines into structured activity events.

The bot reports everything as text with a level. A host that shows an activity feed (the Cloud, an app)
only wants a handful of moments: a character claimed or missed, a roll round, a kakera click, a wishlist hit.
Matching those moments on exact log lines, instead of on words such as "claimed" or "kakera" anywhere in a
line, keeps successful claims from going unnoticed and keeps technical lines (thresholds, timers) out of the
feed. Everything unmatched stays a plain ``log`` event.

Each event has a friendly ``message`` plus the structured fields a host may want (``character``, ``kakera``...).
"""

import re
from typing import Any, Dict, List, Optional, Tuple

Event = Tuple[str, Dict[str, Any]]

_NUMBER = r"[\d.,]+"
_CLAIM_OK = re.compile(r"^(?P<kind>Claim|Snipe) Verification: SUCCESS! We got (?P<name>.+?)\. \((?P<source>[^()]*)\)\s*$")
_CLAIM_MISS = re.compile(r"^Claim Verification: FAILED\. (?P<name>.+?) was not claimed")
_ATTEMPT = re.compile(r"^Claim attempt: (?P<name>.+?)(?: \((?P<ka>" + _NUMBER + r") ka\))?$")
_ATTEMPT_REACTION = re.compile(r"^Claiming (?P<name>.+?)(?: \((?P<ka>" + _NUMBER + r") ka\))? \(Reaction: .*\)$")
_ROLLING = re.compile(r"^Rolling (?P<n>\d+) times")
_KAKERA_CLICK = re.compile(r"^Kakera click sent: (?P<name>.+?) \[(?P<kind>[^\]]+)\]")
_DIVORCE = re.compile(r"^Auto-Divorce: Divorced (?P<name>.+?)(?: \(\+(?P<ka>\d+) kakera\))?$")
_WISH = (re.compile(r"^Wish detected on edited roll: (?P<name>.+?)\. Checking claim\."),
         re.compile(r"^Main Account Sync \(wished by Main\): (?P<name>.+?)!"))
_BONUS_ROLLS = re.compile(r"^Gained \+(?P<n>\d+) extra rolls from Kakera")


def _number(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text.split(".")[0])
    return int(digits) if digits else None


def _with_kakera(text: str, kakera: Optional[int]) -> str:
    return "{} ({} ka)".format(text, kakera) if kakera else text


class ActivityClassifier:
    """One per bot instance: it remembers the last claim attempt so the outcome can carry its kakera value."""

    def __init__(self) -> None:
        self._attempt: Dict[str, Optional[int]] = {}

    def _take(self, name: str) -> Optional[int]:
        return self._attempt.pop(name, None)

    def classify(self, level: str, message: str) -> List[Event]:
        """The events for one log line (usually none or one). ``ERROR`` lines are the caller's business."""
        text = str(message or "").strip()
        level = str(level or "").upper()

        found = _CLAIM_OK.match(text)
        if found:
            name = found.group("name")
            kakera = self._take(name)
            snipe = found.group("kind") == "Snipe"
            return [("claim", {"character": name, "kakera": kakera, "snipe": snipe, "source": found.group("source")[:60],
                               "message": _with_kakera("{} {}".format("Sniped" if snipe else "Claimed", name), kakera)})]
        found = _CLAIM_MISS.match(text)
        if found:
            name = found.group("name")
            kakera = self._take(name)
            return [("claim_failed", {"character": name, "kakera": kakera,
                                      "message": "Did not get {}; the claim is still available".format(name)})]
        found = _ATTEMPT.match(text) or _ATTEMPT_REACTION.match(text)
        if found:
            name, kakera = found.group("name"), _number(found.group("ka"))
            if len(self._attempt) > 20:
                self._attempt.clear()
            self._attempt[name] = kakera
            return [("claim_attempt", {"character": name, "kakera": kakera,
                                       "message": _with_kakera("Trying to claim {}".format(name), kakera)})]
        found = _ROLLING.match(text)
        if found:
            rolls = int(found.group("n"))
            return [("roll", {"rolls": rolls, "message": "Rolling {} time{}".format(rolls, "" if rolls == 1 else "s")})]
        found = _KAKERA_CLICK.match(text)
        if found:
            return [("kakera", {"character": found.group("name"), "kakera_type": found.group("kind"),
                                "message": "{} kakera on {}".format(found.group("kind"), found.group("name"))})]
        found = _DIVORCE.match(text)
        if found:
            kakera = _number(found.group("ka"))
            return [("divorce", {"character": found.group("name"), "kakera": kakera,
                                 "message": _with_kakera("Released {}".format(found.group("name")), kakera)})]
        for pattern in _WISH:
            found = pattern.match(text)
            if found:
                return [("wishlist", {"character": found.group("name"),
                                      "message": "Wishlist match: {}".format(found.group("name"))})]
        found = _BONUS_ROLLS.match(text)
        if found:
            return [("kakera", {"bonus_rolls": int(found.group("n")), "message": text})]

        if level == "KAKERA":                                    # kakera-level lines are all about kakera
            return [("kakera", {"message": text})]
        lowered = text.lower()
        if "reset" in lowered and "roll" in lowered:
            return [("roll_reset", {"message": text})]
        return []
