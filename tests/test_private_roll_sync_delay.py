import asyncio
import datetime
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from mudae_core.status import mark_status_dirty


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
        self.close_created_tasks = True

    def call_later(self, delay, callback, *args):
        handle = _MockHandle(callback, delay, args)
        self.handles.append(handle)
        return handle

    def create_task(self, coroutine):
        self.created_tasks.append(coroutine)
        if self.close_created_tasks:
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
    bot.tu_query_count = int(last_tu_snapshot_complete)
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


class _StatusChannel(_PacingChannel):
    snapshot = (
        "You can claim now!\nNext claim reset in **60** min.\n"
        "You have **1** rolls left. Next rolls reset in **60** min.\n"
        "$rt is available!\nPower: **100%**\n0 $dk available\n"
        "$daily is on cooldown.\n$p is unavailable."
    )

    def __init__(self, channel_id=123456, guild_id=987654):
        super().__init__(channel_id, guild_id)
        self.sent = []
        self.recent_messages = []

    async def send(self, content, **_kwargs):
        self.sent.append(content)
        future = getattr(self.client, "_tu_response_future", None)
        if content == "$tu" and future is not None and not future.done():
            future.set_result(self.snapshot)
        elif content == "$wa":
            self.client._rolls_received += 1
        return SimpleNamespace(id=len(self.sent), created_at=datetime.datetime.now(datetime.timezone.utc))

    async def history(self, limit=1):
        for message in self.recent_messages[:limit]:
            yield message


def _attach_status_channel(client):
    channel = _StatusChannel()
    channel.client = client
    client._main_channel = channel
    client.command_channel = channel
    client.command_pacer.minimum_delay = 0
    client.command_pacer.maximum_delay = 0
    client.auto_p_enabled = False
    client.auto_dk_enabled = False
    client.auto_mk_enabled = False
    client.auto_oh_enabled = False
    client.auto_oc_enabled = False
    client.auto_us_enabled = False
    client.auto_rolls_enabled = False
    return channel


def _advance_at_reset(client, now_utc):
    client.roll_reset_anchor.authoritative_minute = now_utc.minute
    client.roll_reset_anchor.anchor_at_utc = now_utc
    client.roll_reset_anchor.next_boundary_at_utc = now_utc
    client.roll_reset_anchor.confidence = True
    advanced = client._advance_predicted_reset_cycles(now_utc)
    assert "rolls" in advanced
    return client.current_roll_cycle_id


class PrivateRollSyncDelayTests(unittest.IsolatedAsyncioTestCase):
    """Timing Variation delays the status prerequisite, never the owned roll."""

    async def test_later_tu_delays_once_then_releases_roll_immediately(self):
        client = _create_test_client(
            server_reset_minute=None,
            last_tu_snapshot_complete=False,
            humanization_window_minutes=30,
        )
        channel = _attach_status_channel(client)
        client.tu_query_count = 1

        with mock.patch.object(
            mudae_bot.random, "uniform",
            side_effect=lambda low, high: 17 * 60 if high == 30 * 60 else (low + high) / 2,
        ) as draw:
            await client._runtime_check_status(client, channel, "$")
            deadline = client._tu_timing_deadline_utc
            self.assertAlmostEqual(
                (deadline - datetime.datetime.now(datetime.timezone.utc)).total_seconds(),
                17 * 60,
                delta=2,
            )
            self.assertEqual(channel.sent, [])

            await client._runtime_check_status(client, channel, "$")
            self.assertEqual(client._tu_timing_deadline_utc, deadline)
            self.assertEqual(draw.call_count, 1)

            client._tu_timing_deadline_utc = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
            with mock.patch.object(mudae_bot._tu_interval_coordinator, "reserve", return_value=0), \
                    mock.patch.object(mudae_bot, "pause_interruptible_sleep", new=mock.AsyncMock(return_value=True)):
                await client._runtime_check_status(client, channel, "$")

            self.assertEqual(channel.sent, ["$tu"])
            self.assertIsNone(client._tu_timing_deadline_utc)
            handle = client._predicted_roll_action_handle
            self.assertIsNotNone(handle)
            self.assertLessEqual(handle.delay, 0.1)
            client.loop.close_created_tasks = False
            handle.fire()
            self.assertEqual(len(client.loop.created_tasks), 1)
            with mock.patch.object(mudae_bot, "pause_interruptible_sleep", new=mock.AsyncMock(return_value=True)):
                await client.loop.created_tasks.pop()
            self.assertEqual(channel.sent, ["$tu", "$wa"])
            self.assertEqual(draw.call_args_list.count(mock.call(0, 30 * 60)), 1)

    async def test_first_tu_skips_random_and_configured_query_delays(self):
        client = _create_test_client(
            server_reset_minute=None, last_tu_snapshot_complete=False,
            humanization_window_minutes=30,
        )
        channel = _attach_status_channel(client)
        client.delay_seconds = 600
        with mock.patch.object(mudae_bot.random, "uniform") as draw, \
                mock.patch.object(mudae_bot._tu_interval_coordinator, "reserve", return_value=0), \
                mock.patch.object(mudae_bot, "pause_interruptible_sleep", new=mock.AsyncMock(return_value=True)) as sleep:
            await client._runtime_check_status(client, channel, "$")
        self.assertEqual(channel.sent, ["$tu"])
        self.assertIsNone(client._tu_timing_deadline_utc)
        self.assertEqual(client.tu_query_count, 1)
        draw.assert_not_called()
        self.assertNotIn(mock.call(client, 600), sleep.call_args_list)
        self.assertLessEqual(client._predicted_roll_action_handle.delay, 0.1)

    async def test_roll_waits_for_actual_channel_quiet_period(self):
        client = _create_test_client(humanization_window_minutes=30)
        channel = _attach_status_channel(client)
        client.humanization_inactivity_seconds = 5
        channel.recent_messages = [SimpleNamespace(
            author=SimpleNamespace(id=999),
            created_at=datetime.datetime.now(datetime.timezone.utc),
        )]

        waits = []
        quiet_checked = False

        async def finish_quiet_wait(_client, seconds, abort_on_pause=True):
            nonlocal quiet_checked
            waits.append(seconds)
            if not quiet_checked:
                self.assertNotIn("$wa", channel.sent)
                channel.recent_messages.clear()
                quiet_checked = True
            return True

        with mock.patch.object(mudae_bot, "pause_interruptible_sleep", side_effect=finish_quiet_wait):
            await client._runtime_start_roll_commands(client, channel, 1, False, False)

        self.assertGreaterEqual(len(waits), 1)
        self.assertGreaterEqual(waits[0], 5)
        self.assertIn("$wa", channel.sent)

    async def test_predicted_unknown_count_uses_prompt_sync_then_central_tu_gate(self):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        client = _create_test_client(
            server_reset_minute=now_utc.minute,
            trusted_confidence=False,
            humanization_window_minutes=30,
        )
        channel = _attach_status_channel(client)
        cycle_id = _advance_at_reset(client, now_utc)
        sync_handle = client._roll_count_sync_handle
        self.assertIsNotNone(sync_handle)
        self.assertGreaterEqual(sync_handle.delay, 0.5)
        self.assertLessEqual(sync_handle.delay, 3.0)
        client._runtime_schedule_owned_normal_roll_action(cycle_id, now_utc)
        self.assertIs(client._roll_count_sync_handle, sync_handle)

        sync_handle.fire()
        with mock.patch.object(mudae_bot.random, "uniform", return_value=17 * 60) as draw:
            await client._runtime_check_status(client, channel, "$")
            self.assertEqual(draw.call_count, 1)
            self.assertEqual(channel.sent, [])
            client._tu_timing_deadline_utc = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
            with mock.patch.object(mudae_bot._tu_interval_coordinator, "reserve", return_value=0), \
                    mock.patch.object(mudae_bot, "pause_interruptible_sleep", new=mock.AsyncMock(return_value=True)):
                await client._runtime_check_status(client, channel, "$")

        self.assertEqual(channel.sent.count("$tu"), 1)
        self.assertTrue(client.normal_roll_action_owner.is_pending(client.current_roll_cycle_id))
        self.assertLessEqual(client._predicted_roll_action_handle.delay, 0.1)

    async def test_new_predicted_cycle_delays_pre_roll_tu_but_not_post_tu_roll(self):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        client = _create_test_client(
            server_reset_minute=now_utc.minute,
            trusted_capacity=1,
            trusted_confidence=True,
            humanization_window_minutes=30,
        )
        channel = _attach_status_channel(client)
        client.last_tu_query_utc = now_utc - datetime.timedelta(minutes=5)
        client._pre_roll_status_cycle_id = ("roll", 1, 0)
        cycle_id = _advance_at_reset(client, now_utc)
        self.assertTrue(client.normal_roll_action_owner.is_pending(cycle_id))
        self.assertLessEqual(client._predicted_roll_action_handle.delay, 0.1)

        client._pre_roll_status_required = True
        mark_status_dirty(client, {"claim", "rolls", "dk", "points"}, reason="pre-roll-status")
        with mock.patch.object(mudae_bot.random, "uniform", return_value=17 * 60) as draw:
            await client._runtime_check_status(client, channel, "$", proceed_to_rolls=False)
            self.assertEqual(draw.call_count, 1)
            self.assertEqual(channel.sent, [])
            client._tu_timing_deadline_utc = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
            with mock.patch.object(mudae_bot._tu_interval_coordinator, "reserve", return_value=0), \
                    mock.patch.object(mudae_bot, "pause_interruptible_sleep", new=mock.AsyncMock(return_value=True)):
                await client._runtime_check_status(client, channel, "$", proceed_to_rolls=False)
        client._pre_roll_status_required = False

        self.assertEqual(channel.sent.count("$tu"), 1)
        self.assertIsNone(client._tu_timing_deadline_utc)
        self.assertTrue(client.normal_roll_action_owner.is_pending(client.current_roll_cycle_id))
        self.assertLessEqual(client._predicted_roll_action_handle.delay, 0.1)

    async def test_zero_window_or_disabled_humanization_sends_tu_promptly(self):
        for enabled, window in ((True, 0), (False, 30)):
            with self.subTest(enabled=enabled, window=window):
                client = _create_test_client(
                    server_reset_minute=None,
                    last_tu_snapshot_complete=False,
                    humanization_enabled=enabled,
                    humanization_window_minutes=window,
                )
                channel = _attach_status_channel(client)
                with mock.patch.object(mudae_bot._tu_interval_coordinator, "reserve", return_value=0), \
                        mock.patch.object(mudae_bot, "pause_interruptible_sleep", new=mock.AsyncMock(return_value=True)):
                    await client._runtime_check_status(client, channel, "$")
                self.assertEqual(channel.sent.count("$tu"), 1)
                self.assertIsNone(client._tu_timing_deadline_utc)

    async def test_stale_same_cycle_status_refresh_does_not_delay_roll_again(self):
        client = _create_test_client(
            server_reset_minute=None, last_tu_snapshot_complete=False,
            humanization_window_minutes=0,
        )
        channel = _attach_status_channel(client)
        with mock.patch.object(mudae_bot._tu_interval_coordinator, "reserve", return_value=0), \
                mock.patch.object(mudae_bot, "pause_interruptible_sleep", new=mock.AsyncMock(return_value=True)):
            await client._runtime_check_status(client, channel, "$")
            client.humanization_window_minutes = 30
            client._pre_roll_status_requested_at -= datetime.timedelta(seconds=61)
            client.loop.close_created_tasks = False
            client._predicted_roll_action_handle.fire()
            with mock.patch.object(
                mudae_bot.random, "uniform", side_effect=lambda low, high: (low + high) / 2,
            ) as draw:
                await client.loop.created_tasks.pop()
            self.assertEqual(channel.sent, ["$tu", "$tu", "$wa"])
            self.assertNotIn(mock.call(0, 30 * 60), draw.call_args_list)

    async def test_clients_keep_independent_tu_deadlines(self):
        clients = [
            _create_test_client(
                preset_name=f"tu_side_{index}",
                user_id=5000 + index,
                server_reset_minute=None,
                last_tu_snapshot_complete=False,
                humanization_window_minutes=30,
            )
            for index in range(3)
        ]
        channels = [_attach_status_channel(client) for client in clients]
        for client in clients:
            client.tu_query_count = 1

        with mock.patch.object(mudae_bot.random, "uniform", side_effect=[7 * 60, 12 * 60, 17 * 60]):
            for client, channel in zip(clients, channels):
                await client._runtime_check_status(client, channel, "$")

        deadlines = [client._tu_timing_deadline_utc for client in clients]
        self.assertEqual(len(set(deadlines)), 3)
        self.assertTrue(all(channel.sent == [] for channel in channels))
