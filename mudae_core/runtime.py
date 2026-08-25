"""Cross-thread pause state and asyncio waiting helpers."""

import asyncio
import datetime
import random
import time

from .status import STATUS_FIELDS, mark_status_dirty


AUTOMATED_STAGGER_INTERVAL_SECONDS = 20.0


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
