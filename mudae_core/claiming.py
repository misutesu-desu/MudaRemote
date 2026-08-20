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
    """Classify a textual claim confirmation using strict and permissive evidence."""
    raw = str(content or "")
    normalized = normalize_external_text(raw)
    character = normalize_external_text(character_name)
    if not character or not _contains_normalized(normalized, character):
        return ClaimEvidence(ClaimOutcome.INCONCLUSIVE)

    safe_identities = [identity for identity in identities if normalize_external_text(identity) != character]
    if identity_matches(raw, safe_identities, user_id=user_id):
        return ClaimEvidence(ClaimOutcome.SUCCESS, source="confirmation-text")

    labels = re.findall(r"\*\*(.+?)\*\*|\[([^\]]+)\]\([^\)]+\)", raw, flags=re.DOTALL)
    candidates = []
    for bold_label, link_label in labels:
        label = (bold_label or link_label).strip()
        normalized_label = normalize_external_text(label)
        if not normalized_label or normalized_label == character:
            continue
        if normalized_label.isdigit() or normalized_label in {"kakera", "claim", "claimed", "married"}:
            continue
        candidates.append(label)

    relationship_markers = (
        "married", "claimed", "belongs", "casou", "casado", "reclamado",
        "marié", "mariée", "épous", "se casar", "se casó",
    )
    if candidates and any(marker in normalized for marker in relationship_markers):
        return ClaimEvidence(ClaimOutcome.FAILURE, winner=candidates[0], source="confirmation-text")
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
