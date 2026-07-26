"""Shared, testable infrastructure for MudaRemote."""

from .config import atomic_write_json, load_json, validate_preset
from .claiming import (
    ClaimEvidence,
    ClaimOutcome,
    classify_claim_owner,
    classify_claim_text,
    cooldown_deadline,
    has_free_claim_button,
    is_claim_announcement_for_character,
)
from .coordinator import ClaimCoordinator
from .kakera import calculate_kakera_power_cost, has_perk_eight_discount
from .runtime import (
    AUTOMATED_STAGGER_INTERVAL_SECONDS,
    CommandPacer,
    active_stagger_seconds,
    pause_interruptible_sleep,
    prepare_active_presets,
    set_client_paused,
    wait_until_resumed,
)
from .secrets import SecretStore
from .spheres import (
    SphereGameStatus,
    chest_red_candidates,
    choose_chest_position,
    choose_chest_reward_position,
    choose_harvest_position,
    harvest_reveal_is_free,
    normalize_sphere_emoji,
    parse_sphere_game_status,
)
from .status import (
    STATUS_FIELDS,
    clear_status_dirty,
    consume_tu_urgent_bypass,
    defer_tu_queries,
    initialize_status_tracking,
    looks_like_tu_status_snapshot,
    mark_status_dirty,
    record_tu_failure,
    record_tu_success,
    status_dirty_fields,
    status_refresh_reasons,
    tu_retry_wait,
)
from .updater import UpdateError, apply_update
from .versioning import compare_versions, is_newer_version

__all__ = [
    "ClaimCoordinator",
    "ClaimEvidence",
    "ClaimOutcome",
    "CommandPacer",
    "AUTOMATED_STAGGER_INTERVAL_SECONDS",
    "SecretStore",
    "SphereGameStatus",
    "STATUS_FIELDS",
    "UpdateError",
    "apply_update",
    "active_stagger_seconds",
    "atomic_write_json",
    "calculate_kakera_power_cost",
    "classify_claim_owner",
    "classify_claim_text",
    "chest_red_candidates",
    "choose_chest_position",
    "choose_chest_reward_position",
    "choose_harvest_position",
    "clear_status_dirty",
    "consume_tu_urgent_bypass",
    "compare_versions",
    "cooldown_deadline",
    "defer_tu_queries",
    "has_free_claim_button",
    "harvest_reveal_is_free",
    "initialize_status_tracking",
    "is_claim_announcement_for_character",
    "is_newer_version",
    "has_perk_eight_discount",
    "load_json",
    "looks_like_tu_status_snapshot",
    "mark_status_dirty",
    "normalize_sphere_emoji",
    "pause_interruptible_sleep",
    "prepare_active_presets",
    "parse_sphere_game_status",
    "record_tu_failure",
    "record_tu_success",
    "set_client_paused",
    "status_dirty_fields",
    "status_refresh_reasons",
    "tu_retry_wait",
    "validate_preset",
    "wait_until_resumed",
]
