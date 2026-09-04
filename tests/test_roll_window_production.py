import asyncio
import datetime
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from mudae_core.runtime import (
    get_normal_roll_cycle_state,
    normal_roll_batch_fits_window,
    record_ambiguous_normal_roll_consumption,
    reconcile_authoritative_current_roll_count,
)
from mudae_core.status import ResetAnchor, status_refresh_reasons


class _Handle:
    def __init__(self, callback, args=()):
        self.callback = callback
        self.args = args
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def cancelled(self):
        return self._cancelled

    def fire(self):
        return self.callback(*self.args)


class _Loop:
    def __init__(self):
        self.handles = []
        self.created_tasks = []

    def call_later(self, _delay, callback, *args):
        handle = _Handle(callback, args)
        self.handles.append(handle)
        return handle

    def create_task(self, coroutine):
        self.created_tasks.append(coroutine)
        coroutine.close()
        return None

    def create_future(self):
        return asyncio.get_running_loop().create_future()


class _Bot:
    def __init__(self):
        self.loop = _Loop()
        self.user = SimpleNamespace(id=1001, name="AccountA", display_name="AccountA")
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


class _Channel:
    def __init__(self, channel_id=123):
        self.id = channel_id
        self.sent = []

    async def send(self, content, **_kwargs):
        self.sent.append(content)
        return SimpleNamespace(id=len(self.sent), created_at=datetime.datetime.now(datetime.timezone.utc))


def _build_runtime():
    bot = _Bot()
    mudae_bot._mobile_runtime_stop_event.clear()
    with mock.patch.object(mudae_bot.commands, "Bot", return_value=bot):
        mudae_bot.run_bot(
            token="token",
            prefix="!",
            target_channel_id=123,
            roll_command="wa",
            min_kakera=100,
            delay_seconds=0,
            mudae_prefix="$",
            log_function=lambda *_args, **_kwargs: None,
            preset_name="production-roll-window-test",
            key_mode=False,
            start_delay=0,
            snipe_mode=False,
            snipe_delay=0,
            snipe_ignore_min_kakera_reset=False,
            wishlist=[],
            series_snipe_mode=False,
            series_snipe_delay=0,
            series_wishlist=[],
            roll_speed=1.0,
            kakera_snipe_mode_preset=False,
            kakera_snipe_threshold_preset=0,
            enable_reactive_self_snipe_preset=False,
            rolling_enabled=True,
            kakera_reaction_snipe_mode_preset=False,
            kakera_reaction_snipe_delay_preset=0,
            kakera_reaction_snipe_targets=[],
        )
    bot.loop = _Loop()
    return bot


def _install_authoritative_cycle(client, cycle_id, boundary, remaining=1258):
    client.current_roll_cycle_id = cycle_id
    client.roll_reset_at_utc = boundary
    state = get_normal_roll_cycle_state(client, cycle_id)
    state.remaining = remaining
    state.remaining_authoritative = True
    state.count_uncertain = False
    client._normal_roll_action_roll_counts[cycle_id] = remaining
    return state


def _install_anchored_cycle(client, boundary, observed_at_utc, remaining=1002):
    anchor = ResetAnchor("roll", client.roll_interval)
    anchor.observe(boundary, observed_at_utc)
    client.roll_reset_anchor = anchor
    cycle_a = anchor.cycle_id_for_boundary(-1)
    cycle_b = anchor.cycle_id_for_boundary(0)
    state = _install_authoritative_cycle(client, cycle_a, boundary, remaining)
    return anchor, cycle_a, cycle_b, state


class ProductionRollWindowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = _build_runtime()
        self.channel = _Channel(self.client.target_channel_id)
        self.now = datetime.datetime.now(datetime.timezone.utc)
        self.cycle_a = ("roll", 500, 1)

    def _defer_through_ordinary_scheduler(self):
        boundary = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=10)
        _install_authoritative_cycle(self.client, self.cycle_a, boundary)
        self.client._runtime_schedule_owned_normal_roll_action(self.cycle_a, self.now)
        return boundary

    async def test_large_batch_is_admitted_with_reset_aware_owner(self):
        boundary = self.now + datetime.timedelta(minutes=4)
        _anchor, cycle_a, cycle_b, _state = _install_anchored_cycle(
            self.client, boundary, self.now,
        )
        self.client.normal_roll_replenishment_capacity = 1002
        self.client.normal_roll_replenishment_capacity_confidence = True

        self.client._runtime_schedule_owned_normal_roll_action(cycle_a, self.now)
        owner = self.client.normal_roll_action_owner

        self.assertFalse(
            normal_roll_batch_fits_window(
                self.now, boundary, 1002, self.client.roll_speed,
            )
        )
        self.assertEqual(owner.state, "pending")
        self.assertTrue(owner.cross_reset_capable)
        self.assertNotEqual(owner.state, "deferred_window")
        self.assertTrue(owner.start(cycle_a))
        self.client.auto_mk_enabled = False
        self.client.command_pacer.minimum_delay = 0
        self.client.command_pacer.maximum_delay = 0
        self.client.command_pacer._next_command_at = 0
        delay_calls = 0

        async def fast_pause(_client, _seconds, abort_on_pause=False):
            nonlocal delay_calls
            if abort_on_pause:
                delay_calls += 1
                if delay_calls == 3:
                    self.client._runtime_advance_predicted_reset_cycles(
                        boundary + datetime.timedelta(seconds=1),
                    )
            return True

        async def send_roll(content, **_kwargs):
            self.channel.sent.append(content)
            self.client._rolls_received += 1
            return SimpleNamespace(
                id=len(self.channel.sent),
                created_at=datetime.datetime.now(datetime.timezone.utc),
            )

        self.channel.send = send_roll
        with mock.patch.object(mudae_bot, "pause_interruptible_sleep", fast_pause):
            await self.client._runtime_start_roll_commands(
                self.client,
                self.channel,
                1002,
                False,
                False,
                cycle_a,
            )

        state_a = get_normal_roll_cycle_state(self.client, cycle_a)
        state_b = get_normal_roll_cycle_state(self.client, cycle_b)
        self.assertEqual(len(self.channel.sent), 3)
        self.assertEqual(state_a.remaining, 999)
        self.assertEqual(self.client.current_roll_cycle_id, cycle_b)
        self.assertEqual(owner.state, "executing")
        self.assertEqual(owner.queued_cycle_id, cycle_b)

        await self.client._runtime_complete_owned_normal_roll_transaction(
            cycle_a, self.channel,
        )
        self.assertEqual(owner.cycle_id, cycle_b)
        self.assertEqual(owner.state, "pending")
        self.assertIsNone(owner.queued_cycle_id)
        self.assertEqual(state_b.remaining, 1002)
        self.client._runtime_advance_predicted_reset_cycles(
            boundary + datetime.timedelta(seconds=1),
        )
        self.assertEqual(len(self.channel.sent), 3)

    async def test_trusted_successor_is_queued_once_without_replacing_old_counter(self):
        boundary = self.now + datetime.timedelta(minutes=4)
        anchor, cycle_a, cycle_b, state_a = _install_anchored_cycle(
            self.client, boundary, self.now, remaining=998,
        )
        state_a.known_consumed = 4
        self.client.normal_roll_replenishment_capacity = 1002
        self.client.normal_roll_replenishment_capacity_confidence = True
        owner = self.client.normal_roll_action_owner
        owner.schedule(cycle_id=cycle_a, now_utc=self.now)
        self.assertTrue(owner.start(cycle_a))
        self.client._active_normal_roll_cycle_id = cycle_a
        self.client.rolls_left = state_a.remaining

        self.client._runtime_advance_predicted_reset_cycles(boundary + datetime.timedelta(seconds=1))
        successor_state = get_normal_roll_cycle_state(self.client, cycle_b)

        self.assertEqual(self.client.current_roll_cycle_id, cycle_b)
        self.assertEqual(owner.state, "executing")
        self.assertEqual(owner.cycle_id, cycle_a)
        self.assertEqual(owner.queued_cycle_id, cycle_b)
        self.assertEqual(successor_state.remaining, 1002)
        self.assertEqual(state_a.remaining, 998)
        self.assertEqual(self.client.rolls_left, 998)

        self.client._runtime_advance_predicted_reset_cycles(boundary + datetime.timedelta(seconds=1))
        self.assertEqual(owner.queued_cycle_id, cycle_b)
        self.assertEqual(anchor.next_boundary_index, 1)

    async def test_unknown_successor_rebases_and_requests_one_private_sync(self):
        boundary = self.now + datetime.timedelta(minutes=4)
        _anchor, cycle_a, cycle_b, _state_a = _install_anchored_cycle(
            self.client, boundary, self.now, remaining=998,
        )
        owner = self.client.normal_roll_action_owner
        owner.schedule(cycle_id=cycle_a, now_utc=self.now)
        self.assertTrue(owner.start(cycle_a))
        self.client._active_normal_roll_cycle_id = cycle_a

        self.client._runtime_advance_predicted_reset_cycles(boundary + datetime.timedelta(seconds=1))
        self.assertEqual(self.client.current_roll_cycle_id, cycle_b)
        self.assertEqual(owner.state, "executing")
        self.assertIsNone(owner.queued_cycle_id)
        self.assertIsNotNone(self.client._roll_count_sync_handle)

        await self.client._runtime_complete_owned_normal_roll_transaction(
            cycle_a, self.channel,
        )

        self.assertEqual(owner.cycle_id, cycle_b)
        self.assertEqual(owner.state, "completed")
        self.assertEqual(self.client._roll_count_sync_cycle_id, cycle_b)
        self.assertEqual(
            status_refresh_reasons(self.client).count("private-roll-count-sync"),
            1,
        )

        reconcile_authoritative_current_roll_count(
            self.client,
            1002,
            observation_kind="cross-reset-regression-test",
        )
        self.assertIsNone(self.client._roll_count_sync_cycle_id)
        self.assertIsNone(self.client._roll_count_sync_requested_cycle_id)

    async def test_boundary_race_token_is_counted_once_in_successor_state(self):
        boundary = self.now + datetime.timedelta(minutes=4)
        _anchor, cycle_a, cycle_b, state_a = _install_anchored_cycle(
            self.client, boundary, self.now, remaining=1000,
        )
        successor_state = get_normal_roll_cycle_state(self.client, cycle_b)

        self.assertTrue(
            record_ambiguous_normal_roll_consumption(
                self.client, cycle_b, token="roll-token-1",
            )
        )
        self.assertFalse(
            record_ambiguous_normal_roll_consumption(
                self.client, cycle_b, token="roll-token-1",
            )
        )
        state_a.known_consumed = 2

        self.assertEqual(successor_state.known_consumed, 1)
        self.assertEqual(state_a.known_consumed, 2)
        self.assertEqual(state_a.remaining, 1000)

    async def test_kakera_extra_rolls_survive_trusted_cycle_handoff(self):
        boundary = self.now + datetime.timedelta(minutes=4)
        _anchor, cycle_a, cycle_b, state_a = _install_anchored_cycle(
            self.client, boundary, self.now, remaining=998,
        )
        self.client.normal_roll_replenishment_capacity = 1002
        self.client.normal_roll_replenishment_capacity_confidence = True
        self.client._local_extra_rolls_pending = 3
        self.client.rolls_left = state_a.remaining + 3
        owner = self.client.normal_roll_action_owner
        owner.schedule(cycle_id=cycle_a, now_utc=self.now)
        self.assertTrue(owner.start(cycle_a))
        self.client._active_normal_roll_cycle_id = cycle_a

        self.client._runtime_advance_predicted_reset_cycles(boundary + datetime.timedelta(seconds=1))
        self.assertEqual(self.client._local_extra_rolls_pending, 3)
        self.assertEqual(self.client.rolls_left, 1001)

        await self.client._runtime_complete_owned_normal_roll_transaction(
            cycle_a, self.channel,
        )
        self.assertEqual(owner.cycle_id, cycle_b)
        self.assertEqual(owner.state, "pending")
        self.assertEqual(self.client.rolls_left, 1005)
        self.assertEqual(get_normal_roll_cycle_state(self.client, cycle_b).remaining, 1002)

    async def test_claim_waiting_owner_is_handed_off_and_stale_wake_is_ignored(self):
        boundary = self.now + datetime.timedelta(minutes=4)
        _anchor, cycle_a, cycle_b, _state_a = _install_anchored_cycle(
            self.client, boundary, self.now, remaining=9,
        )
        self.client.normal_roll_replenishment_capacity = 9
        self.client.normal_roll_replenishment_capacity_confidence = True
        owner = self.client.normal_roll_action_owner
        owner.schedule(cycle_id=cycle_a, now_utc=self.now)
        self.assertTrue(owner.defer(cycle_a))
        wake_at = self.now + datetime.timedelta(minutes=1)
        self.client._runtime_schedule_daily_rolls_claim_wake(wake_at)
        stale_wake = self.client._daily_rolls_claim_wake_handle

        self.client._runtime_advance_predicted_reset_cycles(boundary + datetime.timedelta(seconds=1))

        self.assertTrue(stale_wake.cancelled())
        self.assertEqual(owner.cycle_id, cycle_b)
        self.assertEqual(owner.state, "pending")
        stale_wake.fire()
        self.assertEqual(owner.cycle_id, cycle_b)
        self.assertEqual(owner.state, "pending")

    async def test_tiny_remaining_window_still_defers_without_sending(self):
        boundary = self.now + datetime.timedelta(seconds=5)
        _anchor, cycle_a, _cycle_b, _state = _install_anchored_cycle(
            self.client, boundary, self.now, remaining=1002,
        )
        owner = self.client.normal_roll_action_owner
        owner.schedule(cycle_id=cycle_a, now_utc=self.now)
        self.assertTrue(owner.start(cycle_a))

        await self.client._runtime_start_roll_commands(
            self.client,
            self.channel,
            1002,
            False,
            False,
            cycle_a,
        )

        self.assertEqual(owner.state, "deferred_window")
        self.assertFalse(self.channel.sent)
        self.assertEqual(self.client._normal_roll_deferred_until_utc, boundary)

    async def test_scheduled_trigger_uses_atomic_production_defer(self):
        safe_boundary = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        _install_authoritative_cycle(self.client, self.cycle_a, safe_boundary)
        self.client._runtime_schedule_owned_normal_roll_action(self.cycle_a, self.now)
        owner = self.client.normal_roll_action_owner
        old_handle = self.client._predicted_roll_action_handle
        refresh_reasons_before = status_refresh_reasons(self.client)
        self.assertEqual(owner.state, "pending")

        exhausted_boundary = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=10)
        self.client.roll_reset_at_utc = exhausted_boundary
        self.client._runtime_schedule_owned_normal_roll_action(
            self.cycle_a, self.now, scheduled_trigger=True,
        )

        self.assertEqual(owner.cycle_id, self.cycle_a)
        self.assertEqual(owner.state, "deferred_window")
        self.assertNotEqual(owner.state, "completed")
        self.assertEqual(self.client._normal_roll_deferred_cycle_id, self.cycle_a)
        self.assertEqual(self.client._normal_roll_deferred_until_utc, exhausted_boundary)
        self.assertNotIn(self.cycle_a, self.client._normal_roll_action_scheduled_triggers)
        self.assertTrue(old_handle.cancelled())
        self.assertIsNone(self.client._predicted_roll_action_handle)
        self.assertEqual(status_refresh_reasons(self.client), refresh_reasons_before)
        _, recreated = owner.schedule(cycle_id=self.cycle_a, now_utc=self.now)
        self.assertFalse(recreated)

    async def test_ordinary_scheduler_failure_defers_pending_owner(self):
        refresh_reasons_before = status_refresh_reasons(self.client)
        boundary = self._defer_through_ordinary_scheduler()
        owner = self.client.normal_roll_action_owner

        self.assertEqual(owner.cycle_id, self.cycle_a)
        self.assertEqual(owner.state, "deferred_window")
        self.assertNotEqual(owner.state, "completed")
        self.assertEqual(self.client._normal_roll_deferred_until_utc, boundary)
        self.assertIsNone(self.client._predicted_roll_action_handle)
        self.assertEqual(status_refresh_reasons(self.client), refresh_reasons_before)

    async def test_start_roll_commands_final_check_defers_executing_owner_without_send(self):
        boundary = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=10)
        _install_authoritative_cycle(self.client, self.cycle_a, boundary)
        owner = self.client.normal_roll_action_owner
        owner.schedule(cycle_id=self.cycle_a, now_utc=self.now)
        self.assertTrue(owner.start(self.cycle_a))

        await self.client._runtime_start_roll_commands(
            self.client,
            self.channel,
            1258,
            False,
            False,
            self.cycle_a,
        )

        self.assertEqual(owner.state, "deferred_window")
        self.assertNotEqual(owner.state, "completed")
        self.assertFalse(self.channel.sent)
        self.assertEqual(self.client._normal_roll_deferred_until_utc, boundary)
        _, recreated = owner.schedule(cycle_id=self.cycle_a, now_utc=self.now)
        self.assertFalse(recreated)

    async def test_claim_wait_wake_transitions_waiting_to_pending_to_deferred(self):
        boundary = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=10)
        _install_authoritative_cycle(self.client, self.cycle_a, boundary)
        owner = self.client.normal_roll_action_owner
        owner.schedule(cycle_id=self.cycle_a, now_utc=self.now)
        self.assertTrue(owner.defer(self.cycle_a))
        self.client.claim_right_available = True

        wake_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=1)
        self.client._runtime_schedule_daily_rolls_claim_wake(wake_at)
        wake_handle = self.client._daily_rolls_claim_wake_handle
        with mock.patch.object(owner, "defer_window", wraps=owner.defer_window) as defer_window:
            wake_handle.fire()

        self.assertEqual(owner.cycle_id, self.cycle_a)
        self.assertEqual(owner.state, "deferred_window")
        self.assertEqual(defer_window.call_count, 1)
        self.assertEqual(self.client._normal_roll_deferred_cycle_id, self.cycle_a)
        self.assertEqual(self.client._normal_roll_deferred_until_utc, boundary)

    async def test_stale_claim_wake_cannot_clear_successor_wake_metadata(self):
        boundary = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        _install_authoritative_cycle(self.client, self.cycle_a, boundary, remaining=13)
        owner = self.client.normal_roll_action_owner
        owner.schedule(cycle_id=self.cycle_a, now_utc=self.now)
        self.assertTrue(owner.defer(self.cycle_a))
        first_wake = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
        self.client._runtime_schedule_daily_rolls_claim_wake(first_wake)
        stale_handle = self.client._daily_rolls_claim_wake_handle

        cycle_b = ("roll", 500, 2)
        owner.schedule(cycle_id=cycle_b, now_utc=self.now)
        self.assertEqual(owner.cycle_id, cycle_b)
        self.assertTrue(owner.defer(cycle_b))
        second_wake = first_wake + datetime.timedelta(minutes=5)
        self.client._runtime_schedule_daily_rolls_claim_wake(second_wake)
        successor_handle = self.client._daily_rolls_claim_wake_handle

        stale_handle.fire()

        self.assertIs(self.client._daily_rolls_claim_wake_handle, successor_handle)
        self.assertEqual(self.client._daily_rolls_claim_wake_at_utc, second_wake)
        self.assertEqual(owner.cycle_id, cycle_b)
        self.assertEqual(owner.state, "waiting_claim")

    async def test_materially_earlier_boundary_does_not_release_seal(self):
        sealed_boundary = self._defer_through_ordinary_scheduler()
        changed_cycle = ("roll", 499, 1)
        earlier_boundary = sealed_boundary - datetime.timedelta(minutes=5)
        _install_authoritative_cycle(self.client, changed_cycle, earlier_boundary)

        self.client._runtime_schedule_owned_normal_roll_action(changed_cycle, self.now)

        self.assertEqual(self.client.normal_roll_action_owner.cycle_id, self.cycle_a)
        self.assertEqual(self.client.normal_roll_action_owner.state, "deferred_window")
        self.assertEqual(self.client._normal_roll_deferred_until_utc, sealed_boundary)
        self.assertIsNone(self.client._predicted_roll_action_handle)

    async def test_same_boundary_refinement_does_not_release_seal(self):
        sealed_boundary = self._defer_through_ordinary_scheduler()
        refined_cycle = ("roll", 501, 1)
        refined_boundary = sealed_boundary + datetime.timedelta(seconds=125)
        _install_authoritative_cycle(self.client, refined_cycle, refined_boundary)

        self.client._runtime_schedule_owned_normal_roll_action(refined_cycle, self.now)

        self.assertEqual(self.client.normal_roll_action_owner.cycle_id, self.cycle_a)
        self.assertEqual(self.client.normal_roll_action_owner.state, "deferred_window")
        self.assertEqual(self.client._normal_roll_deferred_until_utc, sealed_boundary)

    async def test_later_successor_schedules_once_and_stale_callback_cannot_replace_it(self):
        safe_boundary = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        _install_authoritative_cycle(self.client, self.cycle_a, safe_boundary)
        self.client._runtime_schedule_owned_normal_roll_action(self.cycle_a, self.now)
        stale_handle = self.client._predicted_roll_action_handle
        exhausted_boundary = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=10)
        self.client.roll_reset_at_utc = exhausted_boundary
        self.client._runtime_schedule_owned_normal_roll_action(
            self.cycle_a, self.now, scheduled_trigger=True,
        )

        cycle_b = ("roll", 500, 2)
        successor_boundary = exhausted_boundary + datetime.timedelta(hours=1)
        _install_authoritative_cycle(self.client, cycle_b, successor_boundary)
        self.client._runtime_schedule_owned_normal_roll_action(cycle_b, self.now)
        successor_handle = self.client._predicted_roll_action_handle
        self.client._runtime_schedule_owned_normal_roll_action(cycle_b, self.now)

        self.assertEqual(self.client.normal_roll_action_owner.cycle_id, cycle_b)
        self.assertEqual(self.client.normal_roll_action_owner.state, "pending")
        self.assertIs(self.client._predicted_roll_action_handle, successor_handle)
        stale_handle.fire()
        self.assertIs(self.client._predicted_roll_action_handle, successor_handle)
        self.assertFalse(self.client.loop.created_tasks)
        _, stale_created = self.client.normal_roll_action_owner.schedule(
            cycle_id=self.cycle_a, now_utc=self.now,
        )
        self.assertFalse(stale_created)

    async def test_live_same_cycle_status_iteration_does_not_restart_or_send_tu(self):
        boundary = self._defer_through_ordinary_scheduler()
        owner = self.client.normal_roll_action_owner
        reconcile_authoritative_current_roll_count(
            self.client,
            1258,
            observation_kind="check-status",
            observed_at_utc=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=2),
        )

        await self.client._runtime_check_status(
            self.client,
            self.channel,
            self.client.mudae_prefix,
        )

        self.assertEqual(owner.cycle_id, self.cycle_a)
        self.assertEqual(owner.state, "deferred_window")
        self.assertFalse(self.channel.sent)
        self.assertEqual(self.client._normal_roll_deferred_until_utc, boundary)
        self.assertGreater(
            self.client._status_cycle_not_before_monotonic,
            mudae_bot.time.monotonic(),
        )

    async def test_round_three_auto_rolls_defers_panic_claim_when_roll_replenishment_precedes_claim_reset(self):
        boundary = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=20)
        _install_authoritative_cycle(self.client, self.cycle_a, boundary, remaining=0)
        owner = self.client.normal_roll_action_owner
        owner.schedule(cycle_id=self.cycle_a, now_utc=self.now)
        self.assertTrue(owner.start(self.cycle_a))

        self.client.auto_rolls_enabled = True
        self.client.auto_rolls_only_claim_hour = True
        self.client.claim_right_available = True
        self.client.next_claim_reset_at_utc = self.now + datetime.timedelta(minutes=45)
        self.client.roll_reset_at_utc = boundary
        self.client.enable_reactive_self_snipe = False

        dracula_msg = SimpleNamespace(
            id=777,
            embeds=[SimpleNamespace(author=SimpleNamespace(name="Dracula"), description="117<:kakera:123>")],
            components=[],
        )
        self.client.collected_rolls = [dracula_msg]
        self.client._preserve_collected_rolls = True

        await self.client._runtime_start_roll_commands(
            self.client,
            self.channel,
            0,
            False,
            False,
            self.cycle_a,
        )

        # Dracula was deferred, NOT processed immediately before Auto $rolls!
        self.assertEqual(self.client.collected_rolls, [dracula_msg])


if __name__ == "__main__":
    unittest.main()
