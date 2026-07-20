"""Shared, testable infrastructure for MudaRemote."""

from .config import atomic_write_json, load_json, validate_preset
from .claiming import ClaimEvidence, ClaimOutcome, classify_claim_owner, classify_claim_text, cooldown_deadline
from .coordinator import ClaimCoordinator
from .kakera import calculate_kakera_power_cost, has_perk_eight_discount
from .runtime import CommandPacer, pause_interruptible_sleep, set_client_paused, wait_until_resumed
from .secrets import SecretStore
from .status import (
    STATUS_FIELDS,
    clear_status_dirty,
    consume_tu_urgent_bypass,
    defer_tu_queries,
    initialize_status_tracking,
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
    "SecretStore",
    "STATUS_FIELDS",
    "UpdateError",
    "apply_update",
    "atomic_write_json",
    "calculate_kakera_power_cost",
    "classify_claim_owner",
    "classify_claim_text",
    "clear_status_dirty",
    "consume_tu_urgent_bypass",
    "compare_versions",
    "cooldown_deadline",
    "defer_tu_queries",
    "initialize_status_tracking",
    "is_newer_version",
    "has_perk_eight_discount",
    "load_json",
    "mark_status_dirty",
    "pause_interruptible_sleep",
    "record_tu_failure",
    "record_tu_success",
    "set_client_paused",
    "status_dirty_fields",
    "status_refresh_reasons",
    "tu_retry_wait",
    "validate_preset",
    "wait_until_resumed",
]
