"""Pure helpers for Mudae Kakera reaction discounts."""

import re


def has_perk_eight_discount(description: object) -> bool:
    """Detect the Perk 8 half-power marker across common Unicode variants."""
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
    Perk 8 marker is authoritative and therefore applies to either roll source.
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
