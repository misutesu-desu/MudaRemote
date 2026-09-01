import asyncio
import datetime
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from mudae_core.coordinator import GlobalIntervalCoordinator
from mudae_core.runtime import (
    NormalRollActionOwner,
    RollActionTiming,
    get_normal_roll_cycle_state,
    is_tu_still_required,
    normal_roll_start_window,
    reconcile_authoritative_current_roll_count,
)
from mudae_core.status import (
    ResetAnchor,
    clear_status_dirty,
    mark_status_dirty,
    status_dirty_fields,
    status_refresh_reasons,
)


class _MockHandle:
    def __init__(self, callback, delay, args=()):
        self.callback = callback
        self.delay = delay
        self.args = args
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def cancelled(self):
        return self._cancelled

    def fire(self):
        if not self._cancelled:
            return self.callback(*self.args)


class _MockLoop:
    def __init__(self):
        self.handles = []
        self.created_tasks = []

    def call_later(self, delay, callback, *args):
        handle = _MockHandle(callback, delay, args)
        self.handles.append(handle)
        return handle

    def create_task(self, coroutine):
        self.created_tasks.append(coroutine)
        coroutine.close()
        return None

    def create_future(self):
        return asyncio.get_running_loop().create_future()


class _MockBot:
    def __init__(self, preset_name="test-preset", user_id=1001):
        self.loop = _MockLoop()
        self.user = SimpleNamespace(id=user_id, name=preset_name, display_name=preset_name)
        self._main_channel = None
        self.events = {}

    def event(self, function):
        self.events[function.__name__] = function
        return function

    def run(self, _token, reconnect=True):
        return None

    def get_channel(self, _channel_id):
        return None

    def is_closed(self):
        return False


def _create_test_client(
    preset_name="test_account",
    user_id=1001,
    server_reset_minute=58,
    trusted_capacity=None,
    trusted_confidence=False,
    rolling_enabled=True,
    last_tu_snapshot_complete=True,
):
    bot = _MockBot(preset_name=preset_name, user_id=user_id)
    mudae_bot._mobile_runtime_stop_event.clear()
    with mock.patch.object(mudae_bot.commands, "Bot", return_value=bot):
        mudae_bot.run_bot(
            token="dummy_token",
            prefix="!",
            target_channel_id=123456,
            roll_command="wa",
            min_kakera=100,
            delay_seconds=0,
            mudae_prefix="$",
            log_function=lambda *_args, **_kwargs: None,
            preset_name=preset_name,
            key_mode=False,
            start_delay=0,
            snipe_mode=False,
            snipe_delay=0,
            snipe_ignore_min_kakera_reset=False,
            wishlist=[],
            series_snipe_mode=False,
            series_snipe_delay=0,
            series_wishlist=[],
            roll_speed=1.5,
            kakera_snipe_mode_preset=False,
            kakera_snipe_threshold_preset=0,
            enable_reactive_self_snipe_preset=False,
            rolling_enabled=rolling_enabled,
            kakera_reaction_snipe_mode_preset=False,
            kakera_reaction_snipe_delay_preset=0,
            kakera_reaction_snipe_targets=[],
            server_reset_minute_preset=server_reset_minute,
            humanization_enabled=True,
            humanization_window_minutes=10,
        )
    bot.loop = _MockLoop()
    bot.last_tu_snapshot_complete = last_tu_snapshot_complete
    if trusted_confidence and trusted_capacity is not None:
        bot.normal_roll_replenishment_capacity = trusted_capacity
        bot.normal_roll_replenishment_capacity_confidence = True
    else:
        bot.normal_roll_replenishment_capacity = None
        bot.normal_roll_replenishment_capacity_confidence = False
    return bot


class PrivateRollSyncDelayTests(unittest.IsolatedAsyncioTestCase):
    """Mandatory regression tests for delayed private roll sync avoidance."""

    def test_mandatory_1_reproduce_delay_failure_and_verify_prompt_recovery(self):
        """Mandatory Test 1: Predicted reset with unknown roll count requests sync promptly without missing safe roll window."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        client = _create_test_client(
            preset_name="large_account_tester",
            user_id=9999,
            server_reset_minute=now_utc.minute,
            trusted_confidence=False,  # Unlearned capacity on startup / unknown
            last_tu_snapshot_complete=True,
        )

        client.roll_reset_anchor.authoritative_minute = now_utc.minute
        client.roll_reset_anchor.anchor_at_utc = now_utc
        client.roll_reset_anchor.next_boundary_at_utc = now_utc
        client.roll_reset_anchor.confidence = True

        # Advance predicted reset cycle at boundary
        advanced = client._advance_predicted_reset_cycles(now_utc)
        self.assertIn("rolls", advanced)
        current_cid = client.current_roll_cycle_id
        self.assertIsNotNone(current_cid)

        # Assert NEW behavior: Private roll count sync is scheduled promptly (delay <= 5.0s, NOT 444s)
        sync_handle = client._roll_count_sync_handle
        self.assertIsNotNone(sync_handle)
        self.assertLessEqual(sync_handle.delay, 5.0)
        self.assertGreaterEqual(sync_handle.delay, 0.1)

        # Assert private sync pending is recognized while handle is active
        req_before, reason_before = is_tu_still_required(client, proceed_to_rolls=True)
        self.assertFalse(req_before)
        self.assertEqual(reason_before, "private-roll-count-sync-pending")

        # Fire the prompt private sync callback (representing 0.5-3s elapsed)
        sync_handle.fire()
        self.assertIsNone(client._roll_count_sync_handle)

        # Now status is dirty for rolls and physical $tu is required promptly
        self.assertIn("rolls", status_dirty_fields(client))
        req_due, reason_due = is_tu_still_required(client, proceed_to_rolls=True)
        self.assertTrue(req_due)
        self.assertEqual(reason_due, "required")

        # Simulate authoritative $tu response arriving promptly reporting 1062 rolls
        tu_time = now_utc + datetime.timedelta(seconds=4)
        reconcile_authoritative_current_roll_count(
            client,
            1062,
            observation_kind="check-status",
            observed_at_utc=tu_time,
            rearm_existing_owner=lambda cid, deadline: client._schedule_owned_normal_roll_action(cid, deadline),
        )

        # Verify capacity was learned and state updated
        self.assertEqual(client.rolls_left, 1062)
        self.assertEqual(client.normal_roll_replenishment_capacity, 1062)
        self.assertTrue(client.normal_roll_replenishment_capacity_confidence)

        # Schedule the normal roll action with 1062 rolls
        client._schedule_owned_normal_roll_action(current_cid, tu_time)

        # Assert normal roll action is successfully pending and NOT deferred (59.9m remain in cycle, 1062 rolls fit easily)
        owner = client.normal_roll_action_owner
        self.assertEqual(owner.state, "pending")
        self.assertNotEqual(owner.state, "deferred_window")
        self.assertNotEqual(owner.state, "completed")

        # Conversely, verify that under OLD 444s delay + 734s pacing wait (arriving with only 24.6m left), 1062 rolls would fail safe window
        late_tu_time = now_utc + datetime.timedelta(seconds=444 + 735)
        next_reset_time = now_utc + datetime.timedelta(hours=1)
        _, fits_late = normal_roll_start_window(
            late_tu_time, next_reset_time, 1062, roll_speed=1.5, use_slash_rolls=True,
        )
        self.assertFalse(fits_late)

    def test_mandatory_2_trusted_capacity_path(self):
        """Mandatory Test 2: Confident predicted reset with trusted replenishment schedules rolls immediately without immediate physical $tu."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        client = _create_test_client(
            preset_name="trusted_account",
            user_id=2001,
            server_reset_minute=now_utc.minute,
            trusted_capacity=13,
            trusted_confidence=True,
            last_tu_snapshot_complete=True,
        )

        client.roll_reset_anchor.authoritative_minute = now_utc.minute
        client.roll_reset_anchor.anchor_at_utc = now_utc
        client.roll_reset_anchor.next_boundary_at_utc = now_utc
        client.roll_reset_anchor.confidence = True

        advanced = client._advance_predicted_reset_cycles(now_utc)
        self.assertIn("rolls", advanced)
        current_cid = client.current_roll_cycle_id

        # 1. Normal roll action is scheduled immediately from trusted capacity
        owner = client.normal_roll_action_owner
        self.assertEqual(owner.state, "pending")
        self.assertEqual(owner.cycle_id, current_cid)
        self.assertEqual(client.rolls_left, 13)

        # 2. No private sync handle is created
        self.assertIsNone(client._roll_count_sync_handle)

        # 3. No physical $tu is required / enqueued
        required, reason = is_tu_still_required(client, proceed_to_rolls=True)
        self.assertFalse(required)
        self.assertIn(reason, ("roll-action-already-pending", "policy-suppress-routine"))

    def test_mandatory_3_unknown_private_state_requires_prompt_tu(self):
        """Mandatory Test 3: Unknown private roll state requires physical $tu promptly and preserves rate-limit safety."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        client = _create_test_client(
            preset_name="unknown_state_account",
            user_id=3001,
            server_reset_minute=now_utc.minute,
            trusted_confidence=False,
            last_tu_snapshot_complete=True,
        )

        client.roll_reset_anchor.authoritative_minute = now_utc.minute
        client.roll_reset_anchor.anchor_at_utc = now_utc
        client.roll_reset_anchor.next_boundary_at_utc = now_utc
        client.roll_reset_anchor.confidence = True

        advanced = client._advance_predicted_reset_cycles(now_utc)
        self.assertIn("rolls", advanced)
        current_cid = client.current_roll_cycle_id

        # 1. Rolls cannot be scheduled yet (remaining is None)
        owner = client.normal_roll_action_owner
        self.assertEqual(owner.state, "idle")

        # 2. Private sync handle is registered promptly (delay <= 5.0s)
        sync_handle = client._roll_count_sync_handle
        self.assertIsNotNone(sync_handle)
        self.assertLessEqual(sync_handle.delay, 5.0)

        # 3. Once callback fires, physical $tu is strictly required and not permanently suppressed
        sync_handle.fire()
        required, reason = is_tu_still_required(client, proceed_to_rolls=True)
        self.assertTrue(required)
        self.assertEqual(reason, "required")

    def test_mandatory_4_high_account_burst_mix(self):
        """Mandatory Test 4: 60-account burst at predicted reset: trusted accounts do not enqueue $tu, unknown accounts request promptly without queue starvation."""
        pacer = GlobalIntervalCoordinator()
        guild_id = 888888
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        clients = []
        # Create 55 trusted accounts and 5 genuinely unknown accounts
        for i in range(60):
            is_unknown = (i >= 55)
            c = _create_test_client(
                preset_name=f"burst_bot_{i}",
                user_id=4000 + i,
                server_reset_minute=now_utc.minute,
                trusted_capacity=13 if not is_unknown else None,
                trusted_confidence=(not is_unknown),
                last_tu_snapshot_complete=True,
            )
            c.roll_reset_anchor.authoritative_minute = now_utc.minute
            c.roll_reset_anchor.anchor_at_utc = now_utc
            c.roll_reset_anchor.next_boundary_at_utc = now_utc
            c.roll_reset_anchor.confidence = True
            clients.append(c)

        # Reset boundary arrives for all 60 accounts simultaneously
        for c in clients:
            c._advance_predicted_reset_cycles(now_utc)

        # Verify trusted clients scheduled roll actions without $tu
        trusted_pending_roll_actions = sum(
            1 for c in clients[:55] if c.normal_roll_action_owner.state == "pending"
        )
        self.assertEqual(trusted_pending_roll_actions, 55)

        # Verify unknown clients scheduled prompt private syncs
        unknown_sync_handles = sum(
            1 for c in clients[55:] if c._roll_count_sync_handle is not None and c._roll_count_sync_handle.delay <= 5.0
        )
        self.assertEqual(unknown_sync_handles, 5)

        # Fire unknown client sync callbacks
        for c in clients[55:]:
            if c._roll_count_sync_handle:
                c._roll_count_sync_handle.fire()

        # Simulate pre-pacing validation across all 60 clients
        pacer_slots_reserved = 0
        skipped_clients = 0
        pacer_wait_durations = []

        for c in clients:
            required, _ = is_tu_still_required(c, proceed_to_rolls=True)
            if not required:
                skipped_clients += 1
                continue

            wait = pacer.reserve(guild_id, 20.0)
            pacer_slots_reserved += 1
            pacer_wait_durations.append(wait)

        # Assert: 55 trusted clients never entered the pacer queue
        self.assertEqual(skipped_clients, 55)
        # Assert: exactly 5 unknown clients reserved pacer slots
        self.assertEqual(pacer_slots_reserved, 5)
        # Max wait in queue is 4 * 20s = 80s (NOT 734s!)
        self.assertEqual(max(pacer_wait_durations), 80.0)
