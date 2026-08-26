"""Cross-thread pause state and asyncio waiting helpers."""

import asyncio
import datetime
from dataclasses import dataclass
import random
import time

from .status import STATUS_FIELDS, mark_status_dirty


AUTOMATED_STAGGER_INTERVAL_SECONDS = 20.0


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
        if cycle_key != self.cycle_key:
            self.cycle_key = cycle_key
            self.deadline_utc = None
            self.random_delay_seconds = 0.0
            self.completed = False

        if self.completed:
            return now_utc
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

    def consume_text_origin(self, entry, response_message_id):
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
