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
# Main/Side hand-off lines; names sit inside Unicode isolates (U+2068 ... U+2069).
_SIDE_ASK = re.compile("^Main found nothing \u2014 asking side \u2068(?P<side>.+?)\u2069 to roll$")
_SIDE_CLAIM = re.compile("^Main claimed \u2068(?P<name>.+?)\u2069 from \u2068(?P<side>.+?)\u2069's roll$")
# «Main claims good rolls made by its alts» (mudae_core.alt_roll_claim).
_ALT_ROLL_TAKE = re.compile("^claiming \u2068(?P<name>.+?)\u2069 rolled by (?P<alt>.+?) \\((?P<why>[^()]*)\\)$")
_ALT_ROLL_LEFT = re.compile("^left \u2068(?P<name>.+?)\u2069 for (?P<taker>the main|alt \\d+)$")
# A profile running several accounts puts «main: » / «alt N: » in front of its lines.
_ACCOUNT_LABEL = re.compile(r"^(?P<label>main|alt \d+): ")
# Running totals and auto-give (see totals.AccountTotals.describe / kakera_give).
_TOTALS = re.compile(r"^Totals: kakera (?P<kakera>[\d,]+|unknown) \u00b7 spheres (?P<spheres>[\d,]+|unknown) \((?P<why>[^()]*)\)$")
_GIVE_OK = re.compile(r"^Auto-give: gave (?P<ka>[\d,]+) kakera to the main")
_GIVE_ALL = re.compile(r"^Give all kakera: (?P<what>gave (?P<ka>[\d,]+) kakera to the main|not given \u2014 .+?)\.?(?: Bot said: .*)?$")
_SPHERE_GIVE_OK = re.compile(r"^Sphere give: gave (?P<sp>[\d,]+) spheres to the main")
_SPHERE_GIVE_STOP = re.compile(r"^Sphere give stopped: (?P<why>.+?)\. Next try in")
_GIVE_ALL_SPHERES = re.compile(r"^Give all spheres: (?P<what>gave (?P<sp>[\d,]+) spheres to the main|not given \u2014 .+?)\.?(?: Bot said: .*)?$")
_HAREM_GIVE_OK = re.compile(r"^Harem give: gave (?P<pages>[\d,]+) harem page\(s\) to the main")
_HAREM_GIVE_STOP = re.compile(r"^Harem give stopped: (?P<why>.+?)\. Next try in")
# Automatic perk-10 upgrade (see perk_upgrade.PerkUpgrader._finish).
_PERK10_OK = re.compile(r"^Perk 10: upgraded (?P<n>[\d,]+) character\(s\) for (?P<sp>[\d,]+) spheres")
_PERK10_STOP = re.compile(r"^Perk 10 stopped: (?P<why>.+?)\. Next try in")


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
        labelled = _ACCOUNT_LABEL.match(text)
        if labelled:
            events = self.classify(level, text[labelled.end():])
            for _kind, data in events:
                data.setdefault("account", labelled.group("label"))
            return events

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
        found = _SIDE_ASK.match(text)
        if found:
            side = found.group("side")
            return [("side_roll", {"side": side, "message": "Asking side account {} to roll".format(side)})]
        found = _SIDE_CLAIM.match(text)
        if found:
            name, side = found.group("name"), found.group("side")
            return [("side_roll", {"character": name, "side": side,
                                   "message": "Claimed {} from {}'s roll".format(name, side)})]
        found = _ALT_ROLL_TAKE.match(text)
        if found:
            name, alt = found.group("name"), found.group("alt")
            return [("alt_roll_claim", {"character": name, "alt": alt, "why": found.group("why")[:60],
                                        "message": "Claiming {} rolled by {} ({})".format(name, alt, found.group("why"))})]
        found = _ALT_ROLL_LEFT.match(text)
        if found:
            return [("alt_roll_left", {"character": found.group("name"), "taker": found.group("taker"),
                                       "message": "Left {} for {}".format(found.group("name"), found.group("taker"))})]
        found = _TOTALS.match(text)
        if found:
            return [("totals", {"kakera": _number(found.group("kakera")), "spheres": _number(found.group("spheres")),
                                "message": "Kakera {} · spheres {}".format(found.group("kakera"), found.group("spheres"))})]
        found = _GIVE_OK.match(text)
        if found:
            kakera = _number(found.group("ka"))
            return [("kakera_give", {"kakera": kakera, "message": "Gave {} kakera to the main".format(found.group("ka"))})]
        found = _GIVE_ALL.match(text)
        if found:
            return [("kakera_give_now", {"kakera": _number(found.group("ka")),
                                         "message": "Give all kakera: " + found.group("what")[:200]})]
        found = _SPHERE_GIVE_OK.match(text)
        if found:
            return [("sphere_give", {"spheres": _number(found.group("sp")),
                                     "message": "Gave {} spheres to the main".format(found.group("sp"))})]
        found = _SPHERE_GIVE_STOP.match(text)
        if found:
            return [("sphere_give_stopped", {"message": "Sphere give stopped: {}".format(found.group("why")[:200])})]
        found = _GIVE_ALL_SPHERES.match(text)
        if found:
            return [("sphere_give_now", {"spheres": _number(found.group("sp")),
                                         "message": "Give all spheres: " + found.group("what")[:200]})]
        found = _HAREM_GIVE_OK.match(text)
        if found:
            pages = _number(found.group("pages"))
            return [("harem_give", {"pages": pages, "message": "Gave {} harem page(s) to the main".format(found.group("pages"))})]
        found = _HAREM_GIVE_STOP.match(text)
        if found:
            return [("harem_give_stopped", {"message": "Harem give stopped: {}".format(found.group("why")[:200])})]
        found = _PERK10_OK.match(text)
        if found:
            return [("perk10_upgrade", {"characters": _number(found.group("n")), "spheres": _number(found.group("sp")),
                                        "message": "Perk 10: upgraded {} character(s) for {} spheres".format(
                                            found.group("n"), found.group("sp"))})]
        found = _PERK10_STOP.match(text)
        if found:
            return [("perk10_stopped", {"message": "Perk 10 stopped: {}".format(found.group("why")[:200])})]
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
