"""Pure helpers for Mudae Kakera reaction discounts."""

from dataclasses import dataclass
import re
from typing import NamedTuple


_CHARACTER_SPHERE_EMOJIS = frozenset({
    "spP", "spB", "spT", "spG", "spY", "spO", "spR", "spW", "spL",
    "spD", "spM", "spU",
})


_KAKERA_RESULT_RE = re.compile(
    r"<a?:(?P<emoji>kakera[A-Za-z0-9_]*):\d+>\s*"
    r"(?:\(\s*Free\s*\)\s*)?"
    r"\*{0,2}\s*(?P<user>[^*\r\n+]+?)\s*"
    r"\+\s*(?P<amount>[\d,\.\s]+)\s*\*{0,2}\s*"
    r"\(\s*\$k\s*\)",
    re.IGNORECASE,
)


class KakeraResult(NamedTuple):
    amount: int
    emoji_name: str


@dataclass(frozen=True)
class _PendingPowerClick:
    token: int
    emoji_name: str
    cost: float


def _normalize_kakera_emoji(value: object) -> str:
    return str(value or "").strip().rstrip("2").casefold()


class KakeraPowerLedger:
    """Reserve paid clicks and commit their cost only after Mudae confirms them."""

    def __init__(self):
        self._next_token = 1
        self._pending = []

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    def reserve(self, emoji_name: object, cost: object) -> int:
        numeric_cost = max(0.0, float(cost or 0))
        token = self._next_token
        self._next_token += 1
        self._pending.append(_PendingPowerClick(
            token=token,
            emoji_name=_normalize_kakera_emoji(emoji_name),
            cost=numeric_cost,
        ))
        return token

    def cancel(self, token: object) -> bool:
        for index, pending in enumerate(self._pending):
            if pending.token == token:
                self._pending.pop(index)
                return True
        return False

    def confirm(self, emoji_name: object):
        normalized = _normalize_kakera_emoji(emoji_name)
        for index, pending in enumerate(self._pending):
            if pending.emoji_name == normalized:
                return self._pending.pop(index).cost
        return None

    def available_power(self, confirmed_power: object):
        if confirmed_power is None:
            return None
        reserved = sum(pending.cost for pending in self._pending)
        available = max(0.0, float(confirmed_power) - reserved)
        return int(available) if available.is_integer() else available

    def clear(self):
        self._pending.clear()


def parse_kakera_result(content: object, identities: object):
    """Return the amount and emoji from Mudae's confirmation for this account."""
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
            return KakeraResult(int(digits), match.group("emoji"))
    return None


def parse_kakera_result_amount(content: object, identities: object):
    """Return the earned Kakera amount for one of our identities, if present."""
    result = parse_kakera_result(content, identities)
    return result.amount if result is not None else None


def should_refill_kakera_power(
    current_power: object,
    required_power: object,
    *,
    power_is_confirmed: bool,
    configured_trigger: object = 0,
) -> bool:
    """Allow automatic DK refill from confirmed or deterministically estimated power.

    A paid component click is unconfirmed until Mudae posts the account-specific
    Kakera result. Callers pass ``False`` while such a reservation is pending.
    """
    if current_power is None or not power_is_confirmed:
        return False
    trigger = float(configured_trigger or required_power or 0)
    return float(current_power) < trigger


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


def list_includes_purple(emoji_list: object) -> bool:
    """Return whether a configured emoji selection contains purple Kakera."""
    return any(
        str(item or "").strip().rstrip("2").casefold() == "kakerap"
        for item in emoji_list or ()
    )


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
    mk_emojis: object = None,
    *,
    has_chaos_discount: bool = False,
    has_perk_eight_discount: bool = False,
    is_mk_roll: bool = False,
    is_external_roll: bool = False,
):
    """Choose the one authoritative emoji list for a Kakera roll.

    Selection precedence, most specific first:
    1. The visible Perk 8 marker (authoritative even on another user's roll).
    2. ``$mk`` rolls use the dedicated MK selection; when that override is
       missing it inherits the regular selection instead of every colour.
    3. The 10+ key/Chaos discount remains owner-only because an external roll
       does not prove that the reacting account owns the character.
    4. Regular rolls fall back to the preset's Kakera selection.
    """
    if has_perk_eight_discount:
        return tuple(perk_eight_emojis or ())
    if is_mk_roll:
        if mk_emojis is not None:
            return tuple(mk_emojis or ())
        return tuple(kakera_emojis or ())
    if has_chaos_discount and not is_external_roll:
        return tuple(chaos_emojis or ())
    return tuple(kakera_emojis or ())


def queued_kakera_sort_key(priority: object, has_reaction_cooldown_bypass: bool = False):
    """Order deferred Kakera clicks without discarding the configured priority.

    Perk 8 and Chaos rolls can react through the normal Kakera cooldown.  When
    two deferred buttons have the same configured emoji priority, attempt that
    cooldown-safe click first so an ordinary click cannot make it wait behind
    a newly observed cooldown.
    """
    return (float(priority or 0), bool(has_reaction_cooldown_bypass))


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
