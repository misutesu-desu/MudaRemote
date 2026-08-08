"""Pure helpers for Mudae Kakera reaction discounts."""

import re


_CHARACTER_SPHERE_EMOJIS = frozenset({
    "spP", "spB", "spT", "spG", "spY", "spO", "spR", "spW", "spL",
    "spD", "spM", "spU",
})


_KAKERA_RESULT_RE = re.compile(
    r"<a?:kakera[A-Za-z0-9_]*:\d+>\s*"
    r"\*{0,2}\s*(?P<user>[^*\r\n+]+?)\s*"
    r"\+\s*(?P<amount>[\d,\.\s]+)\s*\*{0,2}\s*"
    r"\(\s*\$k\s*\)",
    re.IGNORECASE,
)


def parse_kakera_result_amount(content: object, identities: object):
    """Return the earned Kakera amount for one of our identities, if present."""
    known_identities = {
        str(identity).strip().casefold()
        for identity in identities or ()
        if str(identity).strip()
    }
    if not known_identities:
        return None
    for match in _KAKERA_RESULT_RE.finditer(str(content or "")):
        if match.group("user").strip().casefold() not in known_identities:
            continue
        digits = re.sub(r"\D", "", match.group("amount"))
        if digits:
            return int(digits)
    return None


def has_op_perk_five_marker(description: object) -> bool:
    """Detect OP5 from Mudae's dedicated ``sp`` custom emoji."""
    return re.search(r"<a?:sp:\d+>", str(description or "")) is not None


def has_purple_kakera_button(components: object) -> bool:
    """Return whether a Mudae message contains a free purple Kakera button."""
    for component in components or ():
        for button in getattr(component, "children", ()) or ():
            if getattr(button, "disabled", False):
                continue
            name = getattr(getattr(button, "emoji", None), "name", None)
            if str(name or "").rstrip("2") == "kakeraP":
                return True
    return False


def has_perk_eight_discount(description: object) -> bool:
    """Detect Perk 8's rendered half-power marker across Unicode variants."""
    normalized = str(description or "").replace("\ufe0f", "").replace("\u20e3", "")
    return re.search(r"💎\s*(?:/|÷|➗)\s*2", normalized) is not None


def kakera_embed_text(embed: object) -> str:
    """Return all stable text locations where Mudae renders perk markers."""
    if embed is None:
        return ""
    parts = [str(getattr(embed, "description", "") or "")]
    footer = getattr(embed, "footer", None)
    parts.append(str(getattr(footer, "text", "") or ""))
    for field in getattr(embed, "fields", ()) or ():
        parts.append(str(getattr(field, "name", "") or ""))
        parts.append(str(getattr(field, "value", "") or ""))
    return "\n".join(part for part in parts if part)


def normalize_character_sphere_emoji(value: object) -> str:
    """Normalize character-roll sphere aliases and doubled variants.

    Mudae uses ``sp`` for the red sphere in some button payloads and ``spR``
    in others. This is separate from mini-game normalization, where ``sp`` has
    board-specific meaning.
    """
    name = str(value or "").strip()
    if name == "sp2":
        name = "sp"
    if name.endswith("2") and name[:-1] in _CHARACTER_SPHERE_EMOJIS:
        name = name[:-1]
    if name == "sp":
        return "spR"
    return name


def is_character_sphere_emoji(value: object) -> bool:
    """Return whether a component emoji is an Ouroperk sphere button."""
    return normalize_character_sphere_emoji(value) in _CHARACTER_SPHERE_EMOJIS


def sphere_target_matches(value: object, targets: object) -> bool:
    """Match a sphere button against configured targets with alias support."""
    normalized = normalize_character_sphere_emoji(value).casefold()
    configured = {
        normalize_character_sphere_emoji(target).casefold()
        for target in targets or ()
        if str(target or "").strip()
    }
    return bool(normalized and normalized in configured)


def get_kakera_emoji_targets(
    kakera_emojis: object,
    chaos_emojis: object,
    perk_eight_emojis: object,
    *,
    has_chaos_discount: bool = False,
    has_perk_eight_discount: bool = False,
    is_external_roll: bool = False,
):
    """Choose the one authoritative emoji list for a Kakera roll.

    The visible Perk 8 marker is authoritative even on another user's roll.
    The 10+ key/Chaos discount remains owner-only because an external roll does
    not prove that the reacting account owns the character.
    """
    if has_perk_eight_discount:
        return tuple(perk_eight_emojis or ())
    if has_chaos_discount and not is_external_roll:
        return tuple(chaos_emojis or ())
    return tuple(kakera_emojis or ())


def find_refreshed_component_button(components, *, custom_id, position, emoji_name):
    """Resolve the same button after a Discord component refresh.

    Mudae's repeated Kakera buttons can share or regenerate custom IDs, so the
    original grid position plus emoji must take precedence over ID matching.
    """
    rows = list(components or ())
    row_index, child_index = position
    if 0 <= row_index < len(rows):
        children = list(getattr(rows[row_index], "children", ()) or ())
        if 0 <= child_index < len(children):
            candidate = children[child_index]
            candidate_name = getattr(getattr(candidate, "emoji", None), "name", None)
            if candidate_name == emoji_name:
                return candidate

    if custom_id is None:
        return None
    for component in rows:
        for candidate in getattr(component, "children", ()) or ():
            candidate_name = getattr(getattr(candidate, "emoji", None), "name", None)
            if getattr(candidate, "custom_id", None) == custom_id and candidate_name == emoji_name:
                return candidate
    return None


def get_regular_kakera_filter_reason(
    *,
    wish_only: bool = False,
    is_wish: bool = False,
    op5_only: bool = False,
    has_op5: bool = False,
    mk_only: bool = False,
    is_mk_roll: bool = False,
    chaos_only: bool = False,
    is_external_roll: bool = False,
    has_chaos_discount: bool = False,
    has_perk_eight_discount: bool = False,
):
    """Apply roll-level filters to ordinary Kakera buttons.

    Purple Kakera and targeted sphere buttons are intentionally handled by the
    caller because they bypass these Kakera-only filters.
    """
    if wish_only and not is_wish:
        return "character is not wished/starwished"
    if op5_only and not has_op5:
        return "embed has no Ouroperk 5 sp emoji"
    if mk_only and not is_mk_roll:
        return "MK Only is enabled and this is not an $mk roll"
    if chaos_only and not is_mk_roll and (
        is_external_roll or (not has_chaos_discount and not has_perk_eight_discount)
    ):
        return "Chaos Only requires a half-power Kakera reaction on your own roll"
    return None


def calculate_kakera_power_cost(
    base_cost: float,
    *,
    has_chaos_discount: bool = False,
    has_perk_eight_discount: bool = False,
    is_external_roll: bool = False,
    is_free: bool = False,
):
    """Apply independent half-cost modifiers without collapsing stacked discounts.

    The 10+ key discount is only assumed for the bot's own rolls because external
    rolls do not prove that the reacting account owns the character. The visible
    The visible Perk 8 ``💎 / 2`` marker is authoritative and therefore
    applies to either roll source.
    """
    if is_free:
        return 0

    cost = max(0.0, float(base_cost or 0))
    if has_chaos_discount and not is_external_roll:
        cost /= 2.0
    if has_perk_eight_discount:
        cost /= 2.0

    cost = round(cost, 4)
    return int(cost) if cost.is_integer() else cost
