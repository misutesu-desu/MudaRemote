"""Pure helpers for Mudae Kakera reaction discounts."""

import re


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
