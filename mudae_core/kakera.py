"""Pure helpers for Mudae Kakera reaction discounts."""

import re


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
            name = getattr(getattr(button, "emoji", None), "name", None)
            if str(name or "").rstrip("2") == "kakeraP":
                return True
    return False


def has_perk_eight_discount(description: object) -> bool:
    """Detect Perk 8's rendered half-power marker across Unicode variants."""
    normalized = str(description or "").replace("\ufe0f", "").replace("\u20e3", "")
    return re.search(r"💎\s*(?:/|÷|➗)\s*2", normalized) is not None


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
