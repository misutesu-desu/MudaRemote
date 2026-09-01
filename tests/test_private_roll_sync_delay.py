import asyncio
import datetime
import time
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
    humanization_enabled=True,
    humanization_window_minutes=30,
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
            humanization_enabled=humanization_enabled,
            humanization_window_minutes=humanization_window_minutes,
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


class _PacingChannel:
    def __init__(self, channel_id, guild_id):
        self.id = channel_id
        self.guild = SimpleNamespace(id=guild_id)


def _advance_at_reset(client, now_utc):
    client.roll_reset_anchor.authoritative_minute = now_utc.minute
    client.roll_reset_anchor.anchor_at_utc = now_utc
    client.roll_reset_anchor.next_boundary_at_utc = now_utc
    client.roll_reset_anchor.confidence = True
    advanced = client._advance_predicted_reset_cycles(now_utc)
    assert "rolls" in advanced
    return client.current_roll_cycle_id


class PrivateRollSyncDelayTests(unittest.IsolatedAsyncioTestCase):
    """Focused production scheduling coverage for humanized roll preparation."""

    def test_mandatory_1_unknown_private_state_syncs_near_humanized_target(self):
        """Unknown state defers its one physical $tu until just before the owned target."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        client = _create_test_client(
            preset_name="humanized_unknown",
            user_id=9999,
            server_reset_minute=now_utc.minute,
            trusted_confidence=False,
        )

        with mock.patch.object(mudae_bot.random, "uniform", return_value=17 * 60):
            current_cid = _advance_at_reset(client, now_utc)

        owner = client.normal_roll_action_owner
        sync_handle = client._roll_count_sync_handle
        self.assertEqual(owner.state, "pending")
        self.assertEqual(owner.cycle_id, current_cid)
        self.assertAlmostEqual((owner.deadline_utc - now_utc).total_seconds(), 17 * 60, delta=1.0)
        self.assertIsNotNone(sync_handle)
        self.assertGreater(sync_handle.delay, 60.0)
        self.assertLess(sync_handle.delay, 17 * 60)
        self.assertLess(client._roll_count_sync_at_utc, owner.deadline_utc)
        self.assertEqual(status_dirty_fields(client), set())
        self.assertIsNone(client._roll_count_sync_requested_cycle_id)
        sync_at_utc = client._roll_count_sync_at_utc

        # Fake scheduler advances to the planned preparation slot. No wall
        # sleep is used; this is the point where the physical $tu becomes due.
        sync_handle.fire()
        self.assertIn("rolls", status_dirty_fields(client))
        required, reason = is_tu_still_required(client, proceed_to_rolls=True)
        self.assertTrue(required)
        self.assertEqual(reason, "required")

        # An authoritative response re-arms the same pre-drawn roll callback.
        reconcile_authoritative_current_roll_count(
            client,
            1062,
            observation_kind="humanized-private-sync",
            observed_at_utc=sync_at_utc,
            rearm_existing_owner=lambda cid, deadline: client._schedule_owned_normal_roll_action(cid, deadline),
        )
        action_handle = client._predicted_roll_action_handle
        self.assertIsNotNone(action_handle)
        self.assertEqual(owner.deadline_utc, client.normal_roll_action_owner.deadline_utc)
        self.assertGreater(owner.deadline_utc, sync_at_utc)

        # Firing the fake action handle proves the production executor is
        # dispatched at the selected humanized deadline, not at reset.
        action_handle.fire()
        self.assertEqual(len(client.loop.created_tasks), 1)

    def test_mandatory_2_trusted_state_needs_no_roll_preparation_tu(self):
        """Trusted replenishment keeps the humanized target and skips pre-roll $tu."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        client = _create_test_client(
            preset_name="humanized_trusted",
            user_id=2001,
            server_reset_minute=now_utc.minute,
            trusted_capacity=13,
            trusted_confidence=True,
        )

        with mock.patch.object(mudae_bot.random, "uniform", return_value=17 * 60):
            current_cid = _advance_at_reset(client, now_utc)

        owner = client.normal_roll_action_owner
        self.assertEqual(owner.state, "pending")
        self.assertEqual(owner.cycle_id, current_cid)
        self.assertAlmostEqual((owner.deadline_utc - now_utc).total_seconds(), 17 * 60, delta=1.0)
        self.assertIsNone(client._roll_count_sync_handle)
        required, reason = is_tu_still_required(client, proceed_to_rolls=True)
        self.assertFalse(required)
        self.assertIn(reason, ("roll-action-already-pending", "policy-suppress-routine"))
        self.assertIsNotNone(client._predicted_roll_action_handle)

    def test_mandatory_3_humanization_disabled_preserves_prompt_sync(self):
        """Normal non-humanized unknown-state reconciliation remains prompt."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        client = _create_test_client(
            preset_name="non_humanized_unknown",
            user_id=3001,
            server_reset_minute=now_utc.minute,
            trusted_confidence=False,
            humanization_enabled=False,
            humanization_window_minutes=0,
        )

        _advance_at_reset(client, now_utc)

        self.assertEqual(client.normal_roll_action_owner.state, "idle")
        sync_handle = client._roll_count_sync_handle
        self.assertIsNotNone(sync_handle)
        self.assertGreaterEqual(sync_handle.delay, 0.1)
        self.assertLessEqual(sync_handle.delay, 3.0)

        sync_handle.fire()
        required, reason = is_tu_still_required(client, proceed_to_rolls=True)
        self.assertTrue(required)
        self.assertEqual(reason, "required")

    def test_mandatory_4_congested_pacer_advances_preparation_before_target(self):
        """Known global pacing congestion moves preparation forward instead of waiting for the roll deadline."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        client = _create_test_client(
            preset_name="congested_humanized",
            user_id=4001,
            server_reset_minute=now_utc.minute,
            trusted_confidence=False,
        )
        client._main_channel = _PacingChannel(channel_id=9101, guild_id=8801)

        original_coordinator = mudae_bot._tu_interval_coordinator
        coordinator = GlobalIntervalCoordinator()
        mudae_bot._tu_interval_coordinator = coordinator
        self.addCleanup(setattr, mudae_bot, "_tu_interval_coordinator", original_coordinator)

        with mock.patch.object(mudae_bot.random, "uniform", return_value=17 * 60):
            current_cid = _advance_at_reset(client, now_utc)

        original_handle = client._roll_count_sync_handle
        self.assertIsNotNone(original_handle)
        for _ in range(10):
            coordinator.reserve(8801, 20.0, now_monotonic=time.monotonic())

        # The regular owner recheck uses the new queue depth and advances the
        # one planned sync; it does not create another logical request.
        client._runtime_schedule_owned_normal_roll_action(current_cid, now_utc)

        owner = client.normal_roll_action_owner
        sync_handle = client._roll_count_sync_handle
        self.assertIsNotNone(sync_handle)
        self.assertTrue(original_handle.cancelled())
        # The queued ten global slots are included in the preparation lead,
        # so this happens materially before the un-congested near-target slot.
        self.assertLess(sync_handle.delay, 850.0)
        self.assertLess(client._roll_count_sync_at_utc, owner.deadline_utc - datetime.timedelta(seconds=180))

        sync_handle.fire()
        required, reason = is_tu_still_required(client, proceed_to_rolls=True)
        self.assertTrue(required)
        self.assertEqual(reason, "required")

    def test_mandatory_5_accounts_follow_independent_humanized_targets(self):
        """Shared-reset accounts retain independent target-aligned preparation work."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        clients = [
            _create_test_client(
                preset_name=f"humanized_side_{index}",
                user_id=5000 + index,
                server_reset_minute=now_utc.minute,
                trusted_confidence=False,
            )
            for index in range(3)
        ]

        with mock.patch.object(mudae_bot.random, "uniform", side_effect=[7 * 60, 12 * 60, 17 * 60]):
            for client in clients:
                _advance_at_reset(client, now_utc)

        targets = [client.normal_roll_action_owner.deadline_utc for client in clients]
        preparation_times = [client._roll_count_sync_at_utc for client in clients]
        self.assertEqual(len(set(targets)), 3)
        self.assertEqual(len(set(preparation_times)), 3)
        self.assertTrue(all(handle.delay > 60.0 for handle in (client._roll_count_sync_handle for client in clients)))
        self.assertTrue(all(sync_at < target for sync_at, target in zip(preparation_times, targets)))
