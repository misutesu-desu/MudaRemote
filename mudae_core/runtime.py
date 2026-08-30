"""Cross-thread pause state and asyncio waiting helpers."""

import asyncio
import datetime
from dataclasses import dataclass, field
import random
import time

from .status import STATUS_FIELDS, mark_status_dirty


AUTOMATED_STAGGER_INTERVAL_SECONDS = 20.0
NORMAL_ROLL_BATCH_SAFETY_MARGIN_SECONDS = 30.0
NORMAL_ROLL_PREROLL_RESERVE_SECONDS = 30.0


def mk_full_power_wait_is_unchanged(
    refresh_at,
    previous_signature,
    *,
    current_power,
    max_power,
    power_revision,
    now_monotonic,
):
    """Whether an existing full-power wake already represents this state."""
    signature = (int(current_power), int(max_power), int(power_revision or 0))
    return bool(
        refresh_at is not None
        and refresh_at > float(now_monotonic)
        and previous_signature == signature
    )


def normal_roll_behavior_flags(
    *,
    rolling_enabled,
    proceed_to_rolls,
    scheduled_roll_due,
    can_claim,
    is_lurking,
    key_mode,
    rt_available,
    is_timing_window,
    is_panic_window,
    pending_rolls=False,
    pending_us=False,
):
    """Return behavior-gated immediate/evaluation decisions for normal rolls."""
    if not rolling_enabled or not proceed_to_rolls:
        return False, False
    immediate = bool(
        scheduled_roll_due
        or (can_claim and not is_lurking)
        or key_mode
        or rt_available
        or is_timing_window
        or is_panic_window
    )
    return immediate, bool(immediate or pending_rolls or pending_us)


def estimate_roll_batch_seconds(roll_count, roll_speed, use_slash_rolls=False, fixed_overhead_seconds=5.0):
    """Conservative duration used to clamp a visible normal-roll start."""
    effective_speed = max(2.0, float(roll_speed or 0.0)) if use_slash_rolls else max(0.0, float(roll_speed or 0.0))
    return max(0, int(roll_count or 0)) * (effective_speed + 0.25) + max(0.0, float(fixed_overhead_seconds or 0.0))


def normal_roll_start_window(now_utc, next_reset_at_utc, roll_count, roll_speed,
                             use_slash_rolls=False, pre_roll_seconds=0.0,
                             safety_margin_seconds=NORMAL_ROLL_BATCH_SAFETY_MARGIN_SECONDS):
    """Return the latest safe start and whether that start is still reachable.

    The visible batch is not the only time between an action deadline and the
    next reset. Callers reserve predictable prerequisite time; the margin covers
    command pacing and ordinary transport jitter.
    """
    if next_reset_at_utc is None:
        return None, True
    duration = (
        estimate_roll_batch_seconds(roll_count, roll_speed, use_slash_rolls)
        + max(0.0, float(pre_roll_seconds or 0.0))
        + max(0.0, float(safety_margin_seconds or 0.0))
    )
    latest = next_reset_at_utc - datetime.timedelta(seconds=duration)
    return latest, latest >= now_utc


def normal_roll_batch_fits_window(now_utc, next_reset_at_utc, roll_count,
                                  roll_speed, use_slash_rolls=False,
                                  safety_margin_seconds=NORMAL_ROLL_BATCH_SAFETY_MARGIN_SECONDS):
    """Whether a batch may start *now* without knowingly crossing its reset."""
    _latest, fits = normal_roll_start_window(
        now_utc, next_reset_at_utc, roll_count, roll_speed, use_slash_rolls,
        safety_margin_seconds=safety_margin_seconds,
    )
    return fits


def normal_action_status_policy(*, owner_cycle_id, current_roll_cycle_id, owner_state,
                                state_dirty, reconciliation_cycle_ids=()):
    """Classify routine status work while a current normal action owns a cycle.

    A complete self-``$tu`` and a locally predicted ResetAnchor are both valid
    sources of a current action.  The policy therefore intentionally does not
    use a "predicted" flag.  Explicit Auto ``$rolls`` reconciliation is the
    narrow exception that may send a physical status command while executing.
    """
    if owner_state == "executing":
        # An executing batch owns its original logical transaction even if a
        # trusted ResetAnchor has already advanced the visible current cycle.
        # Only its explicitly correlated Auto $rolls reconciliation may use
        # the physical status lane until that batch releases the owner.
        if owner_cycle_id is None:
            return "none"
        if owner_cycle_id in set(reconciliation_cycle_ids or ()):
            return "allow-reconciliation"
        return "defer-executing"
    owns_current_cycle = (
        owner_cycle_id is not None
        and owner_cycle_id == current_roll_cycle_id
        and owner_state in {"pending", "waiting_claim", "deferred_window"}
    )
    if not owns_current_cycle:
        return "none"
    if not state_dirty:
        return "suppress-routine"
    return "none"


def interaction_command_name(interaction):
    """Extract a normalized slash-command name across discord.py variants."""
    if interaction is None:
        return None
    value = (
        getattr(interaction, "command_name", None)
        or getattr(interaction, "name", None)
    )
    data = getattr(interaction, "data", None)
    if value is None and isinstance(data, dict):
        value = data.get("name")
    normalized = str(value or "").strip().lstrip("/").casefold()
    return normalized or None


def roll_replenishment_cycle_key(next_reset_at_utc, bucket_seconds=300):
    """Return a stable key despite Mudae's minute-rounded reset estimates."""
    if next_reset_at_utc is None:
        return None
    seconds = max(1, int(bucket_seconds or 300))
    try:
        timestamp = float(next_reset_at_utc.timestamp())
    except (AttributeError, TypeError, ValueError, OSError):
        return None
    return int((timestamp + seconds / 2.0) // seconds)


@dataclass
class RollActionTiming:
    """Stable, one-draw action deadline for one normal-roll replenishment cycle."""

    cycle_key: object = None
    deadline_utc: datetime.datetime = None
    random_delay_seconds: float = 0.0
    completed: bool = False

    def schedule(
        self,
        *,
        cycle_key,
        now_utc,
        latest_action_at_utc=None,
        humanization_enabled=False,
        window_minutes=0,
        persistent_stagger_seconds=0,
        random_source=None,
    ):
        if cycle_key != self.cycle_key or self.completed:
            self.cycle_key = cycle_key
            self.deadline_utc = None
            self.random_delay_seconds = 0.0
            self.completed = False

        if self.deadline_utc is not None:
            return self.deadline_utc

        window_seconds = max(0.0, float(window_minutes or 0) * 60.0)
        random_delay = 0.0
        if humanization_enabled and window_seconds > 0:
            draw = random_source or random.uniform
            random_delay = max(0.0, min(window_seconds, float(draw(0.0, window_seconds))))
        stagger = max(0.0, float(persistent_stagger_seconds or 0.0))
        deadline = now_utc + datetime.timedelta(seconds=random_delay + stagger)
        if latest_action_at_utc is not None:
            deadline = min(deadline, max(now_utc, latest_action_at_utc))

        self.random_delay_seconds = random_delay
        self.deadline_utc = deadline
        return deadline

    def mark_completed(self, cycle_key) -> bool:
        if cycle_key != self.cycle_key:
            return False
        self.completed = True
        return True


@dataclass
class NormalRollActionOwner:
    """One authoritative normal-roll action for one logical reset cycle.

    The owner deliberately wraps (rather than replaces) ``RollActionTiming``:
    timing still owns the random draw, while this state machine owns whether a
    scheduler may create, start, or repeat the visible action.
    """

    timing: RollActionTiming
    cycle_id: object = None
    deadline_utc: datetime.datetime = None
    state: str = "idle"  # idle, pending, waiting_claim, executing, deferred_window, completed
    queued_cycle_id: object = None
    queued_deadline_utc: datetime.datetime = None
    post_claim_deadline_created: bool = False
    deferred_window_cycle_ids: list = field(default_factory=list)

    @staticmethod
    def _calculate_deadline(*, now_utc, latest_action_at_utc=None,
                            humanization_enabled=False, window_minutes=0,
                            persistent_stagger_seconds=0, random_source=None):
        window_seconds = max(0.0, float(window_minutes or 0) * 60.0)
        random_delay = 0.0
        if humanization_enabled and window_seconds > 0:
            draw = random_source or random.uniform
            random_delay = max(0.0, min(window_seconds, float(draw(0.0, window_seconds))))
        deadline = now_utc + datetime.timedelta(
            seconds=random_delay + max(0.0, float(persistent_stagger_seconds or 0.0))
        )
        if latest_action_at_utc is not None:
            deadline = min(deadline, max(now_utc, latest_action_at_utc))
        return deadline

    def schedule(self, *, cycle_id, **timing_kwargs):
        if cycle_id is None:
            return None, False
        if cycle_id in self.deferred_window_cycle_ids:
            return self.deadline_utc, False
        if cycle_id == self.cycle_id and self.state in {
            "pending", "waiting_claim", "executing", "deferred_window"
        }:
            return self.deadline_utc, False
        if self.state == "executing":
            # Coalesce missed cycles to the latest successor while retaining
            # exclusive ownership of the batch that is still running.
            if self.queued_cycle_id == cycle_id:
                return self.queued_deadline_utc, False
            self.queued_cycle_id = cycle_id
            self.queued_deadline_utc = self._calculate_deadline(**timing_kwargs)
            return self.queued_deadline_utc, False
        if self.state == "waiting_claim":
            # A simultaneous claim+roll boundary supersedes the stale waiting
            # opportunity atomically with the new actionable roll cycle.
            return self.supersede_waiting_claim(cycle_id=cycle_id, **timing_kwargs)
        deadline = self.timing.schedule(cycle_key=cycle_id, **timing_kwargs)
        self.cycle_id = cycle_id
        self.deadline_utc = deadline
        self.state = "pending"
        self.post_claim_deadline_created = False
        return deadline, True

    def is_pending(self, cycle_id):
        return cycle_id == self.cycle_id and self.state == "pending"

    def is_waiting_claim(self, cycle_id=None):
        return self.state == "waiting_claim" and (cycle_id is None or cycle_id == self.cycle_id)

    def start(self, cycle_id):
        if not self.is_pending(cycle_id):
            return False
        self.state = "executing"
        return True

    def complete(self, cycle_id):
        if cycle_id != self.cycle_id or self.state not in {"pending", "executing", "waiting_claim"}:
            return False
        self.state = "completed"
        self.timing.mark_completed(cycle_id)
        if self.queued_cycle_id is not None:
            queued_cycle = self.queued_cycle_id
            queued_deadline = self.queued_deadline_utc
            self.queued_cycle_id = None
            self.queued_deadline_utc = None
            self.cycle_id = queued_cycle
            self.deadline_utc = queued_deadline
            self.state = "pending"
            self.timing.cycle_key = queued_cycle
            self.timing.deadline_utc = queued_deadline
            self.timing.completed = False
        return True

    def defer(self, cycle_id):
        if cycle_id != self.cycle_id or self.state not in {"pending", "executing", "waiting_claim"}:
            return False
        self.state = "waiting_claim"
        return True

    def defer_window(self, cycle_id):
        """Seal a cycle whose trusted safe roll window has expired."""
        if cycle_id != self.cycle_id:
            return False
        if self.state == "deferred_window":
            return True
        if self.state not in {"pending", "executing"}:
            return False
        self.state = "deferred_window"
        self.deferred_window_cycle_ids.append(cycle_id)
        if len(self.deferred_window_cycle_ids) > 32:
            del self.deferred_window_cycle_ids[:-32]
        self.timing.mark_completed(cycle_id)
        return True

    def resume_claim(self, cycle_id):
        if cycle_id != self.cycle_id or self.state != "waiting_claim":
            return False
        self.state = "pending"
        return True

    def resume_after_claim(self, *, cycle_id, now_utc, latest_action_at_utc=None,
                           humanization_enabled=False, window_minutes=0,
                           persistent_stagger_seconds=0, random_source=None):
        if cycle_id != self.cycle_id or self.state != "waiting_claim":
            return self.deadline_utc, False
        created = False
        if self.deadline_utc is None or self.deadline_utc <= now_utc:
            if not self.post_claim_deadline_created:
                self.deadline_utc = self._calculate_deadline(
                    now_utc=now_utc,
                    latest_action_at_utc=latest_action_at_utc,
                    humanization_enabled=humanization_enabled,
                    window_minutes=window_minutes,
                    persistent_stagger_seconds=persistent_stagger_seconds,
                    random_source=random_source,
                )
                self.post_claim_deadline_created = True
                created = True
            self.timing.deadline_utc = self.deadline_utc
        self.state = "pending"
        return self.deadline_utc, created

    def supersede_waiting_claim(self, *, cycle_id, **timing_kwargs):
        if self.state != "waiting_claim" or cycle_id == self.cycle_id:
            return self.deadline_utc, False
        deadline = self.timing.schedule(cycle_key=cycle_id, **timing_kwargs)
        self.cycle_id = cycle_id
        self.deadline_utc = deadline
        self.state = "pending"
        self.post_claim_deadline_created = False
        return deadline, True

    def cancel(self, cycle_id=None):
        if cycle_id is not None and cycle_id != self.cycle_id:
            return False
        if self.state == "executing":
            return False
        self.state = "completed"
        self.queued_cycle_id = None
        self.queued_deadline_utc = None
        self.timing.mark_completed(self.cycle_id)
        return True


def defer_normal_roll_window(client, cycle_id, boundary_utc, *, now_utc=None,
                             monotonic_now=None):
    """Atomically seal one exhausted owned roll cycle.

    The owner transition is the authorization point for all associated cleanup.
    Repeating the operation for the already-sealed cycle is harmless and keeps
    the first trusted successor boundary and wake deadline intact.
    """
    owner = getattr(client, "normal_roll_action_owner", None)
    if owner is None:
        return False
    already_deferred = owner.cycle_id == cycle_id and owner.state == "deferred_window"
    if not owner.defer_window(cycle_id):
        return False

    predicted_cycle_id = getattr(client, "_predicted_roll_action_cycle_id", None)
    if predicted_cycle_id == cycle_id:
        handle = getattr(client, "_predicted_roll_action_handle", None)
        if handle is not None and not handle.cancelled():
            handle.cancel()
        client._predicted_roll_action_handle = None
        client._predicted_roll_action_cycle_id = None
    getattr(client, "_normal_roll_action_scheduled_triggers", set()).discard(cycle_id)

    if already_deferred:
        return True

    client._normal_roll_deferred_cycle_id = cycle_id
    client._normal_roll_deferred_until_utc = boundary_utc
    if boundary_utc is not None:
        now_utc = now_utc or datetime.datetime.now(datetime.timezone.utc)
        monotonic_now = time.monotonic() if monotonic_now is None else monotonic_now
        wait_seconds = max(3.0, (boundary_utc - now_utc).total_seconds())
        client._status_cycle_not_before_monotonic = max(
            float(getattr(client, "_status_cycle_not_before_monotonic", 0.0) or 0.0),
            monotonic_now + wait_seconds,
        )
    return True


def normal_roll_window_is_deferred(client, cycle_id, boundary_utc, *, tolerance_seconds=125.0):
    """Return whether an owned cycle is covered by the active exhausted-window seal.

    A small timer refinement is still the same boundary even if rebuilding the
    anchor changes its incidental cycle key. Only a different owner cycle plus
    a materially different successor boundary releases the seal.
    """
    sealed_cycle_id = getattr(client, "_normal_roll_deferred_cycle_id", None)
    sealed_boundary = getattr(client, "_normal_roll_deferred_until_utc", None)
    if sealed_cycle_id is None:
        return False
    if cycle_id == sealed_cycle_id:
        return True
    if boundary_utc is None or sealed_boundary is None:
        return True
    delta_seconds = (boundary_utc - sealed_boundary).total_seconds()
    if delta_seconds <= tolerance_seconds:
        return True
    client._normal_roll_deferred_cycle_id = None
    client._normal_roll_deferred_until_utc = None
    return False


@dataclass
class PendingMkRollOperation:
    """Ownership record for exactly one automated ``$mk`` response."""

    generation: int
    channel_id: int
    expected_user_id: int
    registered_at_utc: datetime.datetime
    future: object = None
    command_name: str = "mk"
    send_mode: str = None
    sent_at_utc: datetime.datetime = None
    source_message_id: int = None
    slash_nonce: str = None
    correlation_token: int = None
    receipt_finalized: bool = False
    receipt_event: object = None
    send_failed: bool = False
    processed_message_id: int = None

    def prearm(
        self, *, command_name, mode, correlation_token=None, sent_at_utc=None
    ) -> None:
        self.command_name = str(command_name or "").strip().lstrip("/").casefold()
        self.send_mode = str(mode or "").casefold()
        self.sent_at_utc = sent_at_utc or self.registered_at_utc
        self.source_message_id = None
        self.slash_nonce = None
        self.correlation_token = correlation_token
        self.receipt_finalized = False
        self.send_failed = False
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.receipt_event = None
        else:
            self.receipt_event = asyncio.Event()

    def mark_sent(self, receipt: object) -> None:
        receipt = receipt or {}
        mode = str(receipt.get("mode") or self.send_mode or "").casefold()
        if not self.send_mode:
            self.prearm(command_name=self.command_name, mode=mode)
        self.send_mode = mode
        self.sent_at_utc = receipt.get("sent_at_utc") or self.registered_at_utc
        self.source_message_id = receipt.get("message_id")
        self.slash_nonce = receipt.get("nonce")
        self.receipt_finalized = True
        self.send_failed = False
        if self.receipt_event is not None:
            self.receipt_event.set()

    def mark_send_failed(self) -> None:
        self.send_failed = True
        if self.receipt_event is not None:
            self.receipt_event.set()

    def matches(
        self,
        *,
        channel_id,
        message_id,
        created_at_utc,
        owner_id,
        command_name,
        source_message_id=None,
        source_mode=None,
        timeout_seconds=45.0,
    ) -> bool:
        if self.processed_message_id is not None or not self.send_mode or self.send_failed:
            return False
        if channel_id != self.channel_id or owner_id != self.expected_user_id:
            return False
        if str(command_name or "").strip().lstrip("/").casefold() != "mk":
            return False
        if source_mode and str(source_mode).casefold() != self.send_mode.casefold():
            return False
        if self.send_mode == "text":
            if self.source_message_id is None or source_message_id != self.source_message_id:
                return False
            if message_id is not None and int(message_id) <= int(self.source_message_id):
                return False
        if created_at_utc is not None and self.sent_at_utc is not None:
            try:
                elapsed = (created_at_utc - self.sent_at_utc).total_seconds()
            except (TypeError, ValueError):
                return False
            if elapsed < -1.0 or elapsed > max(1.0, float(timeout_seconds or 45.0)):
                return False
        return True


@dataclass
class OutgoingRollCommand:
    """One directly observed or pre-armed roll command from this client."""

    token: int
    channel_id: int
    owner_id: int
    owner_name: str
    command_name: str
    mode: str
    registered_at_utc: datetime.datetime
    operation_generation: int = None
    message_id: int = None
    sent_at_utc: datetime.datetime = None
    slash_nonce: str = None
    finalized: bool = False
    cancelled: bool = False
    response_message_id: int = None
    automation_owned: bool = False
    logical_roll_cycle_id: object = None
    expected_reset_boundary_utc: datetime.datetime = None
    send_start_utc: datetime.datetime = None
    send_end_utc: datetime.datetime = None


ROLL_BOUNDARY_ATTRIBUTION_GUARD_SECONDS = 3.0


@dataclass
class NormalRollCycleState:
    """Per-cycle executable rolls, separate from replenishment capacity.

    ``remaining`` is the current count: an authoritative snapshot reduced by
    definitely attributed local sends. ``remaining_authoritative`` records
    that this value is grounded in such a snapshot, not that no local sends
    have occurred since it was received.
    """

    remaining: object = None
    remaining_authoritative: bool = False
    proven_fresh: bool = False
    known_consumed: int = 0
    uncertainty_reasons: set = field(default_factory=set)
    last_authoritative_at_utc: datetime.datetime = None
    authoritative_revision: int = 0

    @property
    def count_uncertain(self) -> bool:
        return bool(self.uncertainty_reasons)

    @count_uncertain.setter
    def count_uncertain(self, value: bool):
        if not value:
            self.uncertainty_reasons.clear()
        elif not self.uncertainty_reasons:
            self.uncertainty_reasons.add("legacy-uncertainty")


def get_normal_roll_cycle_state(client, cycle_id):
    """Retrieve or create the authoritative per-cycle roll state."""
    if cycle_id is None:
        return None
    states = getattr(client, "_normal_roll_cycle_state", None)
    if states is None:
        client._normal_roll_cycle_state = {}
        states = client._normal_roll_cycle_state
    state = states.get(cycle_id)
    if state is None:
        state = NormalRollCycleState()
        states[cycle_id] = state
    return state


def mark_roll_cycle_proven_fresh(client, cycle_id):
    """Mark that this process observed this cycle begin cleanly without ambiguous cross-boundary commands."""
    state = get_normal_roll_cycle_state(client, cycle_id)
    if state is None:
        return
    state.proven_fresh = True
    state.known_consumed = 0


def refresh_legacy_uncertainty_view(client):
    """Synchronize client-level legacy uncertainty view with active cycle states."""
    if client is None:
        return
    states = getattr(client, "_normal_roll_cycle_state", None) or {}
    uncertain_cid = None
    for cid, st in states.items():
        if getattr(st, "count_uncertain", False):
            uncertain_cid = cid
            break
    if uncertain_cid is not None:
        client.cross_cycle_roll_count_uncertain = True
        client.cross_cycle_uncertain_cycle_id = uncertain_cid
    else:
        client.cross_cycle_roll_count_uncertain = False
        client.cross_cycle_uncertain_cycle_id = None


def add_roll_cycle_uncertainty(client, cycle_id, key, *, reason="uncertainty"):
    """Mark a cycle's roll count as uncertain with a specific reason/token key."""
    if cycle_id is None:
        return
    state = get_normal_roll_cycle_state(client, cycle_id)
    if state is not None:
        state.uncertainty_reasons.add(key)
        state.remaining_authoritative = False
    refresh_legacy_uncertainty_view(client)
    if hasattr(client, "_roll_batch_deferred_status_fields"):
        client._roll_batch_deferred_status_fields.add("rolls")
    try:
        from mudae_core.status import mark_status_dirty
        mark_status_dirty(client, {"rolls"}, reason=reason)
    except Exception:
        pass


def add_provisional_roll_cycle_uncertainty(client, cycle_id, key):
    """Record unresolved boundary evidence without requesting status work."""
    if cycle_id is None:
        return
    state = get_normal_roll_cycle_state(client, cycle_id)
    if state is not None:
        state.uncertainty_reasons.add(key)
        state.remaining_authoritative = False
    refresh_legacy_uncertainty_view(client)


def remove_roll_cycle_uncertainty(client, cycle_id, key):
    """Remove one specific uncertainty reason/token for a cycle."""
    if cycle_id is None:
        return
    state = get_normal_roll_cycle_state(client, cycle_id)
    if state is not None:
        state.uncertainty_reasons.discard(key)
    refresh_legacy_uncertainty_view(client)


def clear_roll_cycle_uncertainty(client, cycle_id):
    """Explicitly clear all uncertainty reasons for a cycle."""
    if cycle_id is None:
        return
    state = get_normal_roll_cycle_state(client, cycle_id)
    if state is not None:
        state.uncertainty_reasons.clear()
    refresh_legacy_uncertainty_view(client)


def mark_roll_cycle_count_uncertain(client, cycle_id, reason="uncertainty"):
    """Compatibility wrapper for marking a cycle uncertain with a generic reason."""
    add_roll_cycle_uncertainty(client, cycle_id, reason, reason=reason)


def clear_roll_cycle_count_uncertainty(client, cycle_id):
    """Compatibility wrapper for clearing all uncertainty on a resolved cycle."""
    clear_roll_cycle_uncertainty(client, cycle_id)


def unresolved_pending_roll_uncertainty_keys(client, cycle_id):
    """Return provisional boundary-command keys whose results are unresolved."""
    if cycle_id is None:
        return set()
    return {
        ("pending-boundary-origin", token)
        for token, info in getattr(client, "_pending_boundary_roll_origins", {}).items()
        if info.get("affected_cycle_id") == cycle_id
    }


def roll_cycle_has_only_pending_boundary_origins(state):
    """Whether every uncertainty reason is a still-provisional boundary command."""
    reasons = set(getattr(state, "uncertainty_reasons", set()) or set())
    return bool(reasons) and all(
        isinstance(reason, tuple)
        and len(reason) >= 2
        and reason[0] == "pending-boundary-origin"
        for reason in reasons
    )


def roll_cycle_needs_authoritative_reconcile(state):
    """Whether uncertainty requires status now instead of awaiting a result."""
    return bool(
        state is not None
        and state.count_uncertain
        and not roll_cycle_has_only_pending_boundary_origins(state)
    )


def roll_cycle_uncertainty_requires_status(state):
    """Whether a blocked successor lacks enough evidence to await its result."""
    return bool(
        state is None
        or state.remaining is None
        or roll_cycle_needs_authoritative_reconcile(state)
    )


def normal_roll_schedule_count(state):
    """Read the executable count used by scheduling without mutating evidence."""
    if state is None or state.remaining is None:
        return None
    return max(0, int(state.remaining))


def can_clear_roll_status_after_exact_batch(
    client,
    *,
    logical_roll_cycle_id,
    deferred_status_fields=(),
):
    """Whether exact old-batch completion proves current Rolls state clean."""
    if "rolls" in set(deferred_status_fields or ()):
        return False
    if getattr(client, "_roll_count_reconcile_cycle_id", None) is not None:
        return False
    if getattr(client, "_roll_count_sync_cycle_id", None) is not None:
        return False
    current_cycle_id = getattr(client, "current_roll_cycle_id", None)
    if logical_roll_cycle_id is not None and current_cycle_id != logical_roll_cycle_id:
        return False
    state = get_normal_roll_cycle_state(client, current_cycle_id)
    if state is not None and (state.remaining is None or state.count_uncertain):
        return False
    return True


def roll_cycle_is_same_or_newer(observed_cycle, requested_cycle):
    """Whether two roll IDs share a lineage and observed is not older."""
    if not (
        isinstance(observed_cycle, tuple)
        and isinstance(requested_cycle, tuple)
        and len(observed_cycle) >= 3
        and len(requested_cycle) >= 3
        and observed_cycle[0] == requested_cycle[0] == "roll"
        and observed_cycle[1] == requested_cycle[1]
    ):
        return False
    try:
        return int(observed_cycle[-1]) >= int(requested_cycle[-1])
    except (TypeError, ValueError):
        return False


def release_roll_count_reconciliation(client, cycle_id=None):
    """Release the active roll-count reconciliation lease."""
    claimed_cycle = getattr(client, "_roll_count_reconcile_cycle_id", None)
    if claimed_cycle is None:
        return False
    if cycle_id is not None and claimed_cycle != cycle_id:
        return False
    client._roll_count_reconcile_cycle_id = None
    client._roll_count_reconcile_started_at_utc = None
    return True


def claim_roll_count_reconciliation(client, cycle_id, *, now_utc=None):
    """Acquire the single timed count-reconciliation lease for a cycle."""
    if cycle_id is None:
        return False
    claimed_cycle = getattr(client, "_roll_count_reconcile_cycle_id", None)
    if claimed_cycle is not None:
        return False
    client._roll_count_reconcile_cycle_id = cycle_id
    client._roll_count_reconcile_started_at_utc = (
        now_utc or datetime.datetime.now(datetime.timezone.utc)
    )
    return True


def release_reconciliation_for_authoritative_cycle(
    client,
    observed_cycle,
    *,
    material_reanchor=False,
):
    """Release a lease fulfilled or superseded by authoritative roll state."""
    claimed_cycle = getattr(client, "_roll_count_reconcile_cycle_id", None)
    if claimed_cycle is None:
        return False
    if (
        material_reanchor
        or claimed_cycle == observed_cycle
        or roll_cycle_is_same_or_newer(observed_cycle, claimed_cycle)
    ):
        return release_roll_count_reconciliation(client)
    return False


def record_definite_normal_roll_consumption(client, cycle_id):
    """Apply one definitely same-cycle automated send to executable state."""
    state = get_normal_roll_cycle_state(client, cycle_id)
    if state is None:
        return False
    state.known_consumed += 1
    if state.remaining is not None:
        state.remaining = max(0, int(state.remaining) - 1)
        counts = getattr(client, "_normal_roll_action_roll_counts", None)
        if counts is not None:
            counts[cycle_id] = state.remaining
    return True


def rearm_existing_normal_roll_action(
    client,
    cycle_id,
    schedule_callback,
    *,
    now_utc=None,
):
    """Replace a pending owner's timer without changing its chosen deadline."""
    owner = getattr(client, "normal_roll_action_owner", None)
    state = get_normal_roll_cycle_state(client, cycle_id)
    if (
        owner is None
        or not owner.is_pending(cycle_id)
        or state is None
        or state.remaining is None
        or state.count_uncertain
    ):
        return False
    now_utc = now_utc or datetime.datetime.now(datetime.timezone.utc)
    deadline_utc = owner.deadline_utc or now_utc
    delay = max(0.0, (deadline_utc - now_utc).total_seconds())
    schedule_callback(cycle_id, delay, replace_existing=True)
    return True


def resolve_pending_boundary_roll_uncertainty(client, cycle_id, token):
    """Resolve one registered provisional boundary origin, if it is still live."""
    if cycle_id is None or token is None:
        return False
    pending = getattr(client, "_pending_boundary_roll_origins", {})
    info = pending.get(token)
    metadata_existed = bool(
        info is not None and info.get("affected_cycle_id") == cycle_id
    )
    state = get_normal_roll_cycle_state(client, cycle_id)
    key = ("pending-boundary-origin", token)
    reason_existed = bool(state is not None and key in state.uncertainty_reasons)
    if not metadata_existed and not reason_existed:
        return False
    if metadata_existed:
        pending.pop(token, None)
    remove_roll_cycle_uncertainty(client, cycle_id, key)
    return True


def resolve_pending_boundary_roll_and_rearm(
    client,
    cycle_id,
    token,
    schedule_callback,
    *,
    now_utc=None,
):
    """Resolve a live boundary origin and rearm only when its cycle is clean."""
    if not resolve_pending_boundary_roll_uncertainty(client, cycle_id, token):
        return False
    return rearm_existing_normal_roll_action(
        client,
        cycle_id,
        schedule_callback,
        now_utc=now_utc,
    )


def apply_authoritative_roll_remaining(
    client,
    cycle_id,
    remaining,
    *,
    observation_kind="tu",
    observed_at_utc=None,
    base_normal_remaining=None,
    material_reanchor=False,
):
    """Apply an authoritative roll count to the specified cycle and evaluate capacity learning."""
    if cycle_id is None:
        return
    remaining = max(0, int(remaining or 0))
    state = get_normal_roll_cycle_state(client, cycle_id)
    if state is None:
        return
    observed_at_utc = observed_at_utc or datetime.datetime.now(datetime.timezone.utc)
    state.remaining = remaining
    state.remaining_authoritative = True
    state.last_authoritative_at_utc = observed_at_utc
    state.authoritative_revision += 1
    # A snapshot supersedes prior confirmed/timeout ambiguity, but it cannot
    # settle a command whose result is still outstanding.  That result may
    # have been created after the snapshot and must first resolve or expire.
    pending_keys = unresolved_pending_roll_uncertainty_keys(client, cycle_id)
    state.uncertainty_reasons.intersection_update(pending_keys)
    state.uncertainty_reasons.update(pending_keys)
    refresh_legacy_uncertainty_view(client)

    release_reconciliation_for_authoritative_cycle(
        client,
        cycle_id,
        material_reanchor=material_reanchor,
    )

    counts = getattr(client, "_normal_roll_action_roll_counts", None)
    if counts is not None:
        counts[cycle_id] = remaining
    client.rolls_left = remaining

    # ONLY learn/update replenishment capacity if THIS cycle is PROVEN fresh, untouched, and NOT uncertain
    if (
        state.proven_fresh
        and state.known_consumed == 0
        and not state.count_uncertain
    ):
        capacity_value = (
            max(0, int(base_normal_remaining))
            if base_normal_remaining is not None
            else remaining
        )
        client.normal_roll_replenishment_capacity = capacity_value
        client.normal_roll_replenishment_capacity_confidence = True


def reconcile_authoritative_current_roll_count(
    client,
    remaining,
    *,
    observation_kind,
    observed_at_utc=None,
    base_normal_remaining=None,
    rearm_existing_owner=None,
    material_reanchor=False,
):
    """Apply authoritative count state without originating a roll action.

    The status parser runs before behavior gates such as Lurker Mode and
    ``proceed_to_rolls``.  It may therefore reconcile an owner that a behavior
    layer already created, but it must never create ownership from count state
    alone.
    """
    cycle_id = getattr(client, "current_roll_cycle_id", None)
    if cycle_id is None:
        return False

    observed_at_utc = observed_at_utc or datetime.datetime.now(datetime.timezone.utc)
    apply_authoritative_roll_remaining(
        client,
        cycle_id,
        remaining,
        observation_kind=observation_kind,
        observed_at_utc=observed_at_utc,
        base_normal_remaining=base_normal_remaining,
        material_reanchor=material_reanchor,
    )

    if getattr(client, "_roll_count_sync_cycle_id", None) == cycle_id:
        handle = getattr(client, "_roll_count_sync_handle", None)
        if handle is not None and not handle.cancelled():
            handle.cancel()
        client._roll_count_sync_handle = None
        client._roll_count_sync_cycle_id = None
        client._roll_count_sync_at_utc = None

    owner = getattr(client, "normal_roll_action_owner", None)
    if owner is None or not owner.is_pending(cycle_id):
        return True

    state = get_normal_roll_cycle_state(client, cycle_id)
    authoritative_remaining = state.remaining if state is not None else max(0, int(remaining or 0))
    if authoritative_remaining <= 0 and not getattr(client, "auto_rolls_enabled", False):
        owner.cancel(cycle_id)
        handle = getattr(client, "_predicted_roll_action_handle", None)
        if handle is not None and not handle.cancelled():
            handle.cancel()
        client._predicted_roll_action_handle = None
        return True

    if (
        state is not None
        and state.remaining is not None
        and not state.count_uncertain
        and rearm_existing_owner is not None
    ):
        rearm_existing_owner(
            cycle_id,
            owner.deadline_utc or observed_at_utc,
        )
    return True


def successor_roll_cycle_id(cycle_id):
    """Return the next logical successor cycle ID for a roll cycle."""
    if cycle_id is None:
        return None
    if isinstance(cycle_id, tuple) and len(cycle_id) >= 3 and cycle_id[0] == "roll":
        parts = list(cycle_id)
        parts[-1] = int(parts[-1]) + 1
        return tuple(parts)
    return None


def roll_cycle_matches_anchor_lineage(anchor, cycle_id):
    """Return whether a cycle_id belongs to the current anchor lineage."""
    if anchor is None or cycle_id is None:
        return False
    if not (isinstance(cycle_id, tuple) and len(cycle_id) >= 3 and cycle_id[0] == anchor.name):
        return False
    if getattr(anchor, "anchor_at_utc", None) is None:
        return False
    try:
        return int(cycle_id[1]) == int(anchor.anchor_at_utc.timestamp())
    except (ValueError, TypeError):
        return False


def is_roll_result_cross_boundary_ambiguous(command_entry, result_created_at_utc, boundary_utc, guard_seconds=1.5):
    """Determine whether an outgoing roll command or its result straddled the reset boundary.

    If command send timestamp, command completion, or result timestamp indicates
    that attribution between cycle R and cycle R+1 cannot be provably safe, returns True.
    """
    if command_entry is None or boundary_utc is None:
        return False
    boundary_dt = getattr(command_entry, "expected_reset_boundary_utc", None) or boundary_utc
    if boundary_dt is None:
        return False
    guard = max(0.0, float(guard_seconds or 1.5))

    # 1. Check if the Mudae character result message was created at or after the boundary
    if result_created_at_utc is not None and result_created_at_utc >= boundary_dt:
        return True

    # 2. Check if local send completion ended at or after the boundary
    send_end = getattr(command_entry, "send_end_utc", None)
    if send_end is not None and send_end >= boundary_dt:
        return True

    # 3. Check if command was sent within the guard window before the boundary
    command_sent = getattr(command_entry, "sent_at_utc", None) or getattr(command_entry, "registered_at_utc", None) or getattr(command_entry, "send_start_utc", None)
    if command_sent is not None:
        if command_sent >= (boundary_dt - datetime.timedelta(seconds=guard)):
            return True

    # 4. Check if result arrived suspiciously close to the boundary (within 0.5s)
    if result_created_at_utc is not None:
        if result_created_at_utc >= (boundary_dt - datetime.timedelta(seconds=0.5)):
            return True

    return False


class RollCommandCorrelation:
    """Bounded source of truth for this client's outgoing roll commands."""

    def __init__(self, max_entries=128, ttl_seconds=90.0):
        self.max_entries = max(8, int(max_entries or 128))
        self.ttl_seconds = max(45.0, float(ttl_seconds or 90.0))
        self._next_token = 0
        self._entries = []

    def _prune(self, now_utc=None):
        now = now_utc or datetime.datetime.now(datetime.timezone.utc)
        cutoff = now - datetime.timedelta(seconds=self.ttl_seconds)
        self._entries = [
            entry for entry in self._entries
            if not entry.cancelled and entry.registered_at_utc >= cutoff
        ][-self.max_entries:]

    def prearm(
        self,
        *,
        channel_id,
        owner_id,
        owner_name,
        command_name,
        mode,
        operation=None,
        registered_at_utc=None,
        automation_owned=False,
        logical_roll_cycle_id=None,
        expected_reset_boundary_utc=None,
        send_start_utc=None,
    ):
        registered = registered_at_utc or datetime.datetime.now(datetime.timezone.utc)
        self._prune(registered)
        if operation is not None and operation.correlation_token is not None:
            self.cancel(operation.correlation_token, notify_operation=False)
        self._next_token += 1
        entry = OutgoingRollCommand(
            token=self._next_token,
            channel_id=int(channel_id),
            owner_id=int(owner_id),
            owner_name=str(owner_name or "").casefold(),
            command_name=str(command_name or "").strip().lstrip("/").casefold(),
            mode=str(mode or "").casefold(),
            registered_at_utc=registered,
            operation_generation=getattr(operation, "generation", None),
            automation_owned=bool(automation_owned),
            logical_roll_cycle_id=logical_roll_cycle_id,
            expected_reset_boundary_utc=expected_reset_boundary_utc,
            send_start_utc=send_start_utc or registered,
        )
        self._entries.append(entry)
        if operation is not None:
            operation.prearm(
                command_name=entry.command_name,
                mode=entry.mode,
                correlation_token=entry.token,
                sent_at_utc=entry.registered_at_utc,
            )
        self._prune(registered)
        return entry.token

    def _entry(self, token):
        return next((entry for entry in self._entries if entry.token == token), None)

    def finalize(self, token, receipt, operation=None):
        entry = self._entry(token)
        if entry is None or entry.cancelled:
            return None
        receipt = receipt or {}
        entry.message_id = receipt.get("message_id") or entry.message_id
        entry.sent_at_utc = (
            receipt.get("sent_at_utc") or entry.sent_at_utc or entry.registered_at_utc
        )
        entry.send_end_utc = receipt.get("send_end_utc") or entry.send_end_utc
        entry.slash_nonce = receipt.get("nonce") or entry.slash_nonce
        entry.finalized = True
        if operation is not None and operation.correlation_token == token:
            operation.mark_sent({
                "mode": entry.mode,
                "message_id": entry.message_id,
                "sent_at_utc": entry.sent_at_utc,
                "nonce": entry.slash_nonce,
            })
        self._prune(entry.sent_at_utc)
        return entry

    def cancel(self, token, operation=None, notify_operation=True):
        entry = self._entry(token)
        if entry is not None:
            entry.cancelled = True
        if (
            notify_operation
            and operation is not None
            and operation.correlation_token == token
        ):
            operation.mark_send_failed()
        self._prune()

    def observe_text_command(
        self,
        *,
        channel_id,
        owner_id,
        owner_name,
        command_name,
        message_id,
        sent_at_utc,
    ):
        """Record a gateway-observed command, reconciling a pre-armed self send."""
        sent_at = sent_at_utc or datetime.datetime.now(datetime.timezone.utc)
        self._prune(sent_at)
        normalized = str(command_name or "").strip().lstrip("/").casefold()
        for entry in reversed(self._entries):
            if entry.cancelled or entry.mode != "text":
                continue
            if entry.message_id == message_id:
                return entry
            if (
                not entry.finalized
                and entry.channel_id == int(channel_id)
                and entry.owner_id == int(owner_id)
                and entry.command_name == normalized
            ):
                return self.finalize(entry.token, {
                    "mode": "text",
                    "message_id": message_id,
                    "sent_at_utc": sent_at,
                })
        token = self.prearm(
            channel_id=channel_id,
            owner_id=owner_id,
            owner_name=owner_name,
            command_name=normalized,
            mode="text",
            registered_at_utc=sent_at,
            automation_owned=False,
        )
        return self.finalize(token, {
            "mode": "text",
            "message_id": message_id,
            "sent_at_utc": sent_at,
        })

    def latest_text_origin(
        self, *, channel_id, message_id, created_at_utc, owner_id=None,
        max_age_seconds=None,
    ):
        self._prune(created_at_utc)
        eligible = []
        for entry in self._entries:
            if (
                entry.cancelled
                or not entry.finalized
                or entry.mode != "text"
                or entry.response_message_id is not None
            ):
                continue
            if entry.channel_id != int(channel_id):
                continue
            if owner_id is not None and entry.owner_id != int(owner_id):
                continue
            if entry.message_id is not None and message_id is not None:
                if int(entry.message_id) >= int(message_id):
                    continue
            elif created_at_utc is not None and entry.sent_at_utc is not None:
                elapsed = (created_at_utc - entry.sent_at_utc).total_seconds()
                if elapsed < -1.0 or elapsed > self.ttl_seconds:
                    continue
            if created_at_utc is not None and entry.sent_at_utc is not None:
                elapsed = (created_at_utc - entry.sent_at_utc).total_seconds()
                age_limit = self.ttl_seconds if max_age_seconds is None else max_age_seconds
                if elapsed < -1.0 or elapsed > max(1.0, float(age_limit)):
                    continue
            eligible.append(entry)
        if not eligible:
            return None
        return max(
            eligible,
            key=lambda entry: (
                int(entry.message_id or 0),
                entry.sent_at_utc or entry.registered_at_utc,
                entry.token,
            ),
        )

    def latest_slash_origin(
        self, *, channel_id, created_at_utc, owner_id=None, command_name=None,
        max_age_seconds=None,
    ):
        self._prune(created_at_utc)
        eligible = []
        normalized_cmd = str(command_name or "").strip().lstrip("/").casefold() if command_name else None
        for entry in self._entries:
            if (
                entry.cancelled
                or entry.mode != "slash"
                or entry.response_message_id is not None
            ):
                continue
            if entry.channel_id != int(channel_id):
                continue
            if owner_id is not None and entry.owner_id != int(owner_id):
                continue
            if normalized_cmd is not None and entry.command_name != normalized_cmd:
                continue
            if created_at_utc is not None and (entry.sent_at_utc or entry.registered_at_utc) is not None:
                sent_time = entry.sent_at_utc or entry.registered_at_utc
                elapsed = (created_at_utc - sent_time).total_seconds()
                age_limit = self.ttl_seconds if max_age_seconds is None else max_age_seconds
                if elapsed < -1.0 or elapsed > max(1.0, float(age_limit)):
                    continue
            eligible.append(entry)
        if not eligible:
            return None
        return max(
            eligible,
            key=lambda entry: (
                entry.sent_at_utc or entry.registered_at_utc,
                entry.token,
            ),
        )

    def consume_text_origin(self, entry, response_message_id):
        if entry is not None and entry in self._entries:
            entry.response_message_id = response_message_id

    def consume_slash_origin(self, entry, response_message_id):
        if entry is not None and entry in self._entries:
            entry.response_message_id = response_message_id

    async def route_pending_mk_response(
        self,
        *,
        operation,
        channel_id,
        message_id,
        created_at_utc,
        interaction_owner_id=None,
        interaction_command_name=None,
        handler,
        receipt_timeout_seconds=45.0,
    ):
        """Route one response to its automated $mk handler, suppressing duplicates."""
        if operation is None:
            return False
        if operation.processed_message_id is not None:
            return operation.processed_message_id == message_id
        if channel_id != operation.channel_id or not operation.send_mode:
            return False

        if operation.send_mode == "slash":
            matched = operation.matches(
                channel_id=channel_id,
                message_id=message_id,
                created_at_utc=created_at_utc,
                owner_id=interaction_owner_id,
                command_name=interaction_command_name,
                source_mode="slash",
            )
        else:
            if not operation.receipt_finalized and not operation.send_failed:
                event = operation.receipt_event
                if event is None:
                    return True
                try:
                    await asyncio.wait_for(
                        event.wait(),
                        timeout=max(0.01, float(receipt_timeout_seconds or 45.0)),
                    )
                except asyncio.TimeoutError:
                    # This response belongs to a known in-flight send candidate.
                    # Never let it silently fall through to normal-self handling.
                    return True
            if operation.send_failed:
                return False
            origin = self.latest_text_origin(
                channel_id=channel_id,
                message_id=message_id,
                created_at_utc=created_at_utc,
                max_age_seconds=receipt_timeout_seconds,
            )
            matched = bool(
                origin
                and origin.token == operation.correlation_token
                and origin.command_name == operation.command_name == "mk"
            )

        if not matched:
            return False
        if operation.send_mode == "text":
            self.consume_text_origin(origin, message_id)
        operation.processed_message_id = message_id
        try:
            await handler(is_mk_roll=True)
        finally:
            if operation.future is not None and not operation.future.done():
                operation.future.set_result(message_id)
        return True


def mudae_command_ack_matches(payload, message_id, target_bot_id) -> bool:
    """Match Mudae's checkmark reaction acknowledgement for one command."""
    return (
        getattr(payload, "message_id", None) == message_id
        and getattr(payload, "user_id", None) == target_bot_id
        and str(getattr(getattr(payload, "emoji", None), "name", "") or "") == "✅"
    )


def normalized_mudae_command_matches(content, prefix, command) -> bool:
    """Match one self-authored Mudae command without accepting arguments."""
    normalized = " ".join(str(content or "").split()).casefold()
    expected = "{}{}".format(str(prefix or ""), str(command or "")).casefold()
    return bool(expected) and normalized == expected


def daily_rolls_decision(
    *,
    enabled,
    only_claim_hour,
    claim_right_available,
    key_mode,
    auto_rolls_in_key_mode,
    next_claim_reset_at_utc,
    roll_reset_at_utc,
    used_this_interval,
    limit_reached,
    ack_retry_ready,
    claim_hour_active=False,
    now_utc=None,
):
    """Classify Auto ``$rolls`` work without conflating timing and claim state.

    ``wait-claim-reset`` deliberately remains actionable scheduling work: the
    current roll interval contains a forthcoming claim reset, but the normal
    claim right is not available yet.
    """
    if not enabled:
        return "disabled"
    if limit_reached:
        return "limit-reached"
    if used_this_interval:
        return "already-used"
    if not ack_retry_ready:
        return "ack-retry-wait"

    now = now_utc or datetime.datetime.now(datetime.timezone.utc)
    in_claim_hour = bool(claim_hour_active) or bool(
        next_claim_reset_at_utc
        and roll_reset_at_utc
        and now <= next_claim_reset_at_utc <= roll_reset_at_utc
    )
    claim_bypass = bool(key_mode and auto_rolls_in_key_mode)
    if only_claim_hour:
        if not in_claim_hour:
            return "outside-claim-hour"
        if claim_right_available or claim_bypass:
            return "execute"
        return "wait-claim-reset"
    if claim_right_available or claim_bypass:
        return "execute"
    return "claim-unavailable"


def next_daily_rolls_wake_deadline(decision, next_claim_reset_at_utc):
    """Return the hard wake boundary required by an Auto ``$rolls`` decision."""
    return next_claim_reset_at_utc if decision == "wait-claim-reset" else None


def humanized_claim_refresh_deadline(
    reset_at_utc,
    humanization_enabled=False,
    window_minutes=0,
    jitter=None,
):
    """Return a stable post-reset deadline for a claim status refresh."""
    if reset_at_utc is None:
        return None
    window_seconds = max(0.0, float(window_minutes or 0) * 60.0)
    if not humanization_enabled or window_seconds <= 0:
        return reset_at_utc
    jitter_source = jitter or random.uniform
    delay_seconds = max(0.0, min(window_seconds, float(jitter_source(0.0, window_seconds))))
    return reset_at_utc + datetime.timedelta(seconds=delay_seconds)


def split_command_batches(total, maximum_batch_size=10):
    """Split a command quantity into positive batches capped at the requested size."""
    remaining = max(0, int(total or 0))
    batch_size = int(maximum_batch_size or 0)
    if batch_size <= 0:
        raise ValueError("Maximum batch size must be greater than zero.")
    batches = []
    while remaining > 0:
        current = min(batch_size, remaining)
        batches.append(current)
        remaining -= current
    return batches


def active_stagger_seconds(active_index, interval=AUTOMATED_STAGGER_INTERVAL_SECONDS):
    """Return the deterministic delay for a preset's position in the active launch set."""
    return max(0, int(active_index or 0)) * max(0.0, float(interval or 0.0))


def can_resume_claim_interrupted_rolls(client) -> bool:
    """Return whether a deliberate claim pause can keep using its known rolls."""
    return bool(
        getattr(client, "rolling_enabled", False)
        and not getattr(client, "is_paused", False)
        and not getattr(client, "key_limit_hit", False)
        and getattr(client, "pending_claim", None) is None
        and int(getattr(client, "rolls_left", 0) or 0) > 0
        and (
            getattr(client, "key_mode", False)
            or getattr(client, "claim_right_available", False)
            or getattr(client, "rt_available", False)
            or getattr(client, "is_timing_mode_active", False)
        )
    )


def prepare_active_presets(preset_names, preset_mapping, start_index=0):
    """Expand preset accounts and assign compact stagger offsets in launch order."""
    prepared = []
    seen = set()
    for name in preset_names:
        if name in seen or name not in preset_mapping:
            continue
        seen.add(name)
        data = dict(preset_mapping[name])
        configured_tokens = data.get("tokens")
        if not isinstance(configured_tokens, (list, tuple)) or not configured_tokens:
            configured_tokens = [data.get("token")]
        tokens = []
        seen_tokens = set()
        for token in configured_tokens:
            cleaned = str(token or "").strip()
            if cleaned and cleaned not in seen_tokens:
                seen_tokens.add(cleaned)
                tokens.append(cleaned)
        for token_index, token in enumerate(tokens, 1):
            account_data = dict(data)
            account_data.pop("tokens", None)
            account_data["token"] = token
            active_index = max(0, int(start_index or 0)) + len(prepared)
            account_data["persistent_stagger_seconds"] = active_stagger_seconds(active_index)
            account_name = name if token_index == 1 else "{} #{}".format(name, token_index)
            prepared.append((account_name, account_data))
    return prepared


class CommandPacer:
    """Serialize outbound commands and keep a randomized gap between them."""

    def __init__(self, minimum_delay=0.6, maximum_delay=0.8, clock=None, jitter=None):
        minimum_delay = float(minimum_delay)
        maximum_delay = float(maximum_delay)
        if minimum_delay < 0 or maximum_delay < minimum_delay:
            raise ValueError("Command delay must satisfy 0 <= minimum <= maximum.")
        self.minimum_delay = minimum_delay
        self.maximum_delay = maximum_delay
        self._clock = clock or time.monotonic
        self._jitter = jitter or random.uniform
        self._lock = None
        self._next_command_at = 0.0

    def _get_lock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def run(self, action, wait, is_allowed=None):
        """Run one async command action after all earlier actions and their gap."""
        allowed = is_allowed or (lambda: True)
        if not allowed():
            return False

        async with self._get_lock():
            if not allowed():
                return False
            remaining = self._next_command_at - self._clock()
            if remaining > 0 and not await wait(remaining):
                return False
            if not allowed():
                return False

            result = await action()
            self._next_command_at = self._clock() + self._jitter(
                self.minimum_delay,
                self.maximum_delay,
            )
            return True if result is None else result


def _wake_runtime_events(client) -> None:
    if bool(getattr(client, "is_paused", False)):
        operation = getattr(client, "_pending_mk_roll", None)
        if operation is not None:
            client._pending_mk_roll = None
            future = getattr(operation, "future", None)
            if future is not None and not future.done():
                future.set_result(None)
    for name in ("_runtime_state_event", "_immediate_check_event"):
        event = getattr(client, name, None)
        if event is not None:
            event.set()


def set_client_paused(client, paused: bool) -> None:
    """Apply pause state and wake the owning asyncio loop safely."""
    paused = bool(paused)
    previous = bool(getattr(client, "is_paused", False))
    client.is_paused = paused
    if paused and not previous:
        client._pause_generation = int(getattr(client, "_pause_generation", 0)) + 1
    if paused and not previous:
        interrupted_fields = set()
        if getattr(client, "pending_claim", None) is not None:
            interrupted_fields.add("claim")
        if bool(getattr(client, "is_actively_rolling", False)):
            interrupted_fields.add("rolls")
        if getattr(client, "_pending_mk_roll", None) is not None:
            interrupted_fields.add("rolls")
        tu_future = getattr(client, "_tu_response_future", None)
        if tu_future is not None and not tu_future.done():
            interrupted_fields.update(STATUS_FIELDS)
        if interrupted_fields:
            mark_status_dirty(client, interrupted_fields, reason="pause-interrupted-active-work")

    loop = getattr(client, "loop", None)
    try:
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(_wake_runtime_events, client)
            return
    except (AttributeError, RuntimeError):
        pass
    _wake_runtime_events(client)


async def wait_until_resumed(client) -> None:
    """Wait without polling when a runtime event is available."""
    while bool(getattr(client, "is_paused", False)):
        event = getattr(client, "_runtime_state_event", None)
        if event is None:
            await asyncio.sleep(0.1)
            continue
        event.clear()
        if not bool(getattr(client, "is_paused", False)):
            break
        await event.wait()


async def pause_interruptible_sleep(client, seconds: float, abort_on_pause: bool = False) -> bool:
    """Sleep against wall time, optionally aborting as soon as pause is requested."""
    duration = max(0.0, float(seconds))
    deadline = time.monotonic() + duration
    start_generation = int(getattr(client, "_pause_generation", 0))

    while True:
        if abort_on_pause and (
            bool(getattr(client, "is_paused", False))
            or int(getattr(client, "_pause_generation", 0)) != start_generation
        ):
            return False
        if bool(getattr(client, "is_paused", False)):
            await wait_until_resumed(client)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True

        event = getattr(client, "_runtime_state_event", None)
        if event is None:
            await asyncio.sleep(min(remaining, 0.1))
            continue

        event.clear()
        if abort_on_pause and int(getattr(client, "_pause_generation", 0)) != start_generation:
            return False
        if bool(getattr(client, "is_paused", False)):
            continue
        try:
            await asyncio.wait_for(event.wait(), timeout=remaining)
        except asyncio.TimeoutError:
            return True
