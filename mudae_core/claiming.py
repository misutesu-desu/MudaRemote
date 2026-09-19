"""Pure helpers for interpreting Mudae claim outcomes and cooldowns."""

from dataclasses import dataclass
import datetime
from enum import Enum
import re
from typing import Iterable, Optional


class ClaimOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ClaimEvidence:
    outcome: ClaimOutcome
    winner: Optional[str] = None
    source: str = "none"


def _is_success_button_style(button: object) -> bool:
    style = getattr(button, "style", None)
    return bool(
        style is not None
        and (
            getattr(style, "value", None) == 3
            or str(style).casefold().endswith("success")
            or str(style) == "3"
        )
    )


def has_free_claim_button(components: object, claim_emojis: Iterable[object]) -> bool:
    """Detect Mudae's green claim button, which does not consume a claim right."""
    allowed = {str(emoji) for emoji in claim_emojis}
    for component in components or ():
        for button in getattr(component, "children", ()) or ():
            if getattr(button, "disabled", False):
                continue
            emoji = getattr(getattr(button, "emoji", None), "name", None)
            if emoji is not None and str(emoji) in allowed and _is_success_button_style(button):
                return True
    return False


def normalize_external_text(value: object) -> str:
    """Normalize Discord/Mudae text without depending on a specific markdown style."""
    text = str(value or "")
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"<@!?(\d+)>", r" user-\1 ", text)
    text = re.sub(r"[*_~`>|]+", " ", text)
    text = re.sub(r"[^\w]+", " ", text.casefold(), flags=re.UNICODE)
    return " ".join(text.split())


def _contains_normalized(haystack: str, needle: object) -> bool:
    normalized = normalize_external_text(needle).strip()
    if not normalized:
        return False
    return " {} ".format(normalized) in " {} ".format(haystack)


def identity_matches(value: object, identities: Iterable[object], user_id: Optional[int] = None) -> bool:
    normalized = normalize_external_text(value)
    if user_id is not None and _contains_normalized(normalized, "user-{}".format(user_id)):
        return True
    return any(_contains_normalized(normalized, identity) for identity in identities if identity)


def classify_claim_text(
    content: object,
    character_name: object,
    identities: Iterable[object],
    user_id: Optional[int] = None,
) -> ClaimEvidence:
    """Require a completed ownership statement and identify its actual claimant."""
    raw = str(content or "")
    character = normalize_external_text(character_name)
    if not character or not _contains_normalized(normalize_external_text(raw), character):
        return ClaimEvidence(ClaimOutcome.INCONCLUSIVE)

    def plain_text(value):
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", str(value))
        return re.sub(r"[*~`]", "", text).strip()

    character_pattern = re.escape(plain_text(character_name))
    owner_pattern = r"(?P<owner><@!?\d+>|[^<>\n!?]+?)"
    # Match the relationship, not arbitrary mentions elsewhere in the message.
    # Punctuation ends a confirmation; a following wish ping is not its owner.
    patterns = (
        rf"{owner_pattern} and {character_pattern} are now married",
        rf"{character_pattern} and {owner_pattern} are now married",
        rf"{owner_pattern} (?<!not )(?<!never )(?<!n't )(?:has claimed|claimed) {character_pattern}",
        rf"{owner_pattern} (?:se casou com|casou com|se casó con|a épousé) {character_pattern}",
        rf"{owner_pattern} e {character_pattern} (?:agora estão casados|estão agora casados)",
        rf"{owner_pattern} et {character_pattern} sont (?:maintenant |désormais )?mariés",
        rf"{owner_pattern} y {character_pattern} (?:ahora están casados|están ahora casados)",
    )
    owner_last_patterns = (
        rf"{character_pattern} (?:belongs to|is now married to|was claimed by|has been claimed by) {owner_pattern}",
        rf"{character_pattern} (?:foi reclamado por|foi reclamada por|foi reivindicado por|foi reivindicada por) {owner_pattern}",
    )
    own_names = {normalize_external_text(identity) for identity in identities if identity}
    own_names.discard(character)
    for line in raw.splitlines():
        # Prompts and quoted announcements do not confirm a new claim.
        if line.lstrip().startswith(">") or "?" in line:
            continue
        text = plain_text(line)
        match = next(
            (match for pattern in patterns
             if (match := re.match(rf"^{pattern}(?:[!.]|$)", text, flags=re.IGNORECASE))),
            None,
        )
        if match is None:
            match = next(
                (match for pattern in owner_last_patterns
                 if (match := re.fullmatch(rf"{pattern}[!.]*", text, flags=re.IGNORECASE))),
                None,
            )
        if match is None:
            continue
        owner = match.group("owner").strip()
        normalized_owner = normalize_external_text(owner)
        mention = re.fullmatch(r"<@!?(\d+)>", owner)
        if mention:
            is_self = user_id is not None and int(mention.group(1)) == user_id
        else:
            is_self = normalized_owner in own_names
        if not normalized_owner:
            continue
        return ClaimEvidence(
            ClaimOutcome.SUCCESS if is_self else ClaimOutcome.FAILURE,
            winner=None if is_self else owner,
            source="confirmation-text",
        )
    return ClaimEvidence(ClaimOutcome.INCONCLUSIVE)


def is_claim_announcement_for_character(content: object, character_name: object) -> bool:
    """Return whether a Mudae message announces that the character was claimed."""
    normalized = normalize_external_text(content)
    character = normalize_external_text(character_name)
    if not character or not _contains_normalized(normalized, character):
        return False

    # Forcedivorce prompts also contain relationship wording, but they are not
    # new claims and must never start another release cycle.
    excluded_markers = (
        "force the divorce",
        "forcedivorce",
        "belongs to",
        "divorced",
    )
    if any(marker in normalized for marker in excluded_markers):
        return False

    claim_markers = (
        "are now married",
        "is now married",
        "has claimed",
        " claimed ",
        "casou",
        "casado",
        "reclamado",
        "marie",
        "mariee",
        "epous",
        "se caso",
    )
    padded = " {} ".format(normalized)
    return any(marker in padded for marker in claim_markers)


def classify_claim_owner(
    owner: object,
    identities: Iterable[object],
    user_id: Optional[int] = None,
) -> ClaimEvidence:
    """Treat an owner on the edited character embed as authoritative evidence."""
    if not owner:
        return ClaimEvidence(ClaimOutcome.INCONCLUSIVE)
    if identity_matches(owner, identities, user_id=user_id):
        return ClaimEvidence(ClaimOutcome.SUCCESS, source="character-owner")
    return ClaimEvidence(ClaimOutcome.FAILURE, winner=str(owner), source="character-owner")


def cooldown_deadline(
    now: datetime.datetime,
    minutes: int,
    safety_seconds: float = 2.0,
) -> datetime.datetime:
    """Build a timezone-preserving deadline without truncating seconds early."""
    return now + datetime.timedelta(minutes=max(0, int(minutes)), seconds=max(0.0, safety_seconds))


def basic_panic_claim_fallback_is_active(
    enabled: bool,
    claim_right_available: bool,
    next_claim_reset_at_utc: Optional[datetime.datetime],
    now_utc: Optional[datetime.datetime] = None,
    final_round_minutes: int = 60,
) -> bool:
    """Whether the configured basic panic fallback is active in the final claim round."""
    if not enabled or not claim_right_available or next_claim_reset_at_utc is None:
        return False
    now = now_utc or datetime.datetime.now(datetime.timezone.utc)
    remaining_seconds = (next_claim_reset_at_utc - now).total_seconds()
    return 0 < remaining_seconds <= max(0, int(final_round_minutes)) * 60


def can_spend_restore_on_character(
    kakera_value: int,
    minimum_kakera: int,
    is_wishlist_target: bool,
    restore_for_wishlist: bool,
) -> bool:
    """Keep a panic claim's relaxed value floor from spending $rt on any card."""
    if is_wishlist_target and restore_for_wishlist:
        return True
    return int(kakera_value or 0) >= max(0, int(minimum_kakera or 0))
