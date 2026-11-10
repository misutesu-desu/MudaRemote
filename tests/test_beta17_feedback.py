"""Reproduce the September 13 feedback through the production runtime."""
import asyncio
import datetime
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import mudae_bot
from mudae_core import clear_status_dirty, status_dirty_fields, status_refresh_reasons
from mudae_core.spheres import parse_sphere_game_status
from tests.test_roll_window_production import _build_runtime, _Channel, _install_anchored_cycle


def closure(function, name):
    return function.__closure__[function.__code__.co_freevars.index(name)]


class Beta17RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_tu_oh_stock_plays_before_long_claim_and_roll_reset_wait(self):
        bot = _build_runtime()
        channel = _Channel()
        bot._main_channel = bot.command_channel = channel
        bot.auto_oh_enabled = True
        bot.auto_oc_enabled = bot.auto_p_enabled = bot.auto_dk_enabled = False
        bot.command_pacer.minimum_delay = bot.command_pacer.maximum_delay = 0
        bot._immediate_check_event = None
        snapshot = (
            "Next claim reset in **34** min.\n"
            "You have **0** rolls left. Next rolls reset in **34** min.\n"
            "1 $oh, 0 $oc, 0 $oq and 0 $ot.\n3h 35 min before the refill.\n"
            "Power: **100%**\n0 $dk available\n$daily is on cooldown.\n$p is unavailable."
        )
        long_waits = []
        clock = [mudae_bot.time.monotonic()]
        fake_time = mock.Mock(wraps=mudae_bot.time)
        fake_time.monotonic.side_effect = lambda: clock[0]

        async def send(content, **_kwargs):
            channel.sent.append(content)
            if content == '$tu':
                bot._tu_response_future.set_result(snapshot)
            elif content == '$oh 1':
                bot._sphere_game_response_future.set_result(SimpleNamespace(id=len(channel.sent)))
            return SimpleNamespace(id=len(channel.sent), created_at=datetime.datetime.now(datetime.timezone.utc))

        async def sleep(_client, seconds, **_kwargs):
            if seconds > 1800:
                long_waits.append(seconds)
                self.assertEqual(channel.sent, ['$tu', '$oh 1'])
                bot.is_paused = True
            return True

        async def play(*_args):
            clock[0] += 17  # Board play must not push back the 34-minute reset.
            return True

        channel.send = send
        with mock.patch.object(bot.sphere_runtime, 'play_sphere_game', side_effect=play), \
                mock.patch.object(mudae_bot, 'pause_interruptible_sleep', side_effect=sleep), \
                mock.patch.object(mudae_bot, 'time', fake_time):
            await bot._runtime_check_status(bot, channel, '$')

        self.assertTrue(long_waits)
        self.assertAlmostEqual(long_waits[0], 34 * 60 - 17, delta=1)
        self.assertEqual(bot.sphere_game_counts['oh'], 0)
        self.assertFalse(bot._deferred_independent_known_work)

    async def test_deferred_oh_stays_blocked_by_claim_or_owned_roll_during_wait(self):
        for blocker in ('claim', 'roll-owner'):
            bot = _build_runtime()
            channel = _Channel()
            bot._main_channel = channel
            bot.auto_oh_enabled = True
            bot._immediate_check_event = None
            bot.is_processing_cycle = True
            status = parse_sphere_game_status('1 $oh, 0 $oc\n3h 35 min before the refill')
            await bot.sphere_runtime.run_available_sphere_games(channel, status)
            self.assertTrue(bot._deferred_independent_known_work)
            if blocker == 'claim':
                bot.pending_claim = object()
            else:
                cycle = ('roll', 17, 1)
                bot.current_roll_cycle_id = cycle
                bot.normal_roll_action_owner.schedule(cycle_id=cycle, now_utc=datetime.datetime.now(datetime.timezone.utc))

            async def sleep(_client, seconds, **_kwargs):
                self.assertGreater(seconds, 1800)
                self.assertEqual(channel.sent, [])
                bot.is_paused = True
                return True

            wait = closure(bot._runtime_check_status, 'humanized_wait_and_proceed').cell_contents
            with mock.patch.object(mudae_bot, 'pause_interruptible_sleep', side_effect=sleep):
                await wait(bot, channel, 34, 'claim cooldown', hard_deadline=True)
            self.assertEqual(channel.sent, [], blocker)
            self.assertEqual(bot.sphere_game_counts['oh'], 1, blocker)
            self.assertTrue(bot._deferred_independent_known_work, blocker)

    def _bot_finishing_batch_with_queued_successor(self):
        bot = _build_runtime()
        channel = _Channel()
        bot._main_channel = bot.command_channel = channel
        bot.auto_oq_enabled = True
        bot.auto_oh_enabled = bot.auto_oc_enabled = bot.auto_ot_enabled = False
        bot.auto_p_enabled = bot.auto_dk_enabled = bot.auto_mk_enabled = False
        bot.command_pacer.minimum_delay = bot.command_pacer.maximum_delay = 0
        now = datetime.datetime.now(datetime.timezone.utc)
        cycle_a, cycle_b = ('roll', 17, 1), ('roll', 18, 1)
        owner = bot.normal_roll_action_owner
        owner.schedule(cycle_id=cycle_a, now_utc=now)
        self.assertTrue(owner.start(cycle_a))
        bot.current_roll_cycle_id = cycle_a
        owner.schedule(cycle_id=cycle_b, now_utc=now)
        self.assertEqual(owner.queued_cycle_id, cycle_b)
        bot.sphere_game_counts.update(oq=1)
        bot._deferred_independent_known_work = True

        async def send(content, **_kwargs):
            channel.sent.append(content)
            if content == '$oq 1':
                bot._sphere_game_response_future.set_result(SimpleNamespace(id=len(channel.sent)))
            return SimpleNamespace(id=len(channel.sent), created_at=now)

        channel.send = send
        return bot, channel, cycle_a, cycle_b

    async def test_deferred_boards_play_in_the_gap_before_a_queued_successor_batch(self):
        # A batch that outlasts the roll reset always ends with a successor
        # queued, so waiting for an idle roll lane starves the boards forever.
        bot, channel, cycle_a, cycle_b = self._bot_finishing_batch_with_queued_successor()
        schedule = bot._runtime_schedule_owned_normal_roll_action
        callback = closure(schedule, '_schedule_owned_normal_action_callback').cell_contents
        execute = closure(callback, 'execute_owned_normal_roll_action').cell_contents
        played = []

        async def play(*_args):
            # The successor's timer may fire mid-board; it must wait its turn.
            await execute(cycle_b)
            self.assertNotEqual(bot._roll_count_sync_cycle_id, cycle_b)
            played.append(bot.normal_roll_action_owner.state)
            return True

        with mock.patch.object(bot.sphere_runtime, 'play_sphere_game', side_effect=play):
            await bot._runtime_complete_owned_normal_roll_transaction(cycle_a, channel)

        self.assertEqual(channel.sent, ['$oq 1'])
        self.assertEqual(played, ['pending'])
        self.assertEqual(bot.sphere_game_counts['oq'], 0)
        self.assertFalse(bot._deferred_independent_known_work)
        self.assertEqual(bot.normal_roll_action_owner.cycle_id, cycle_b)

    async def test_gap_before_a_queued_batch_still_yields_to_a_pending_claim(self):
        bot, channel, cycle_a, _cycle_b = self._bot_finishing_batch_with_queued_successor()
        bot.pending_claim = object()

        await bot._runtime_complete_owned_normal_roll_transaction(cycle_a, channel)

        self.assertEqual(channel.sent, [])
        self.assertEqual(bot.sphere_game_counts['oq'], 1)
        self.assertTrue(bot._deferred_independent_known_work)

    async def test_queued_batch_blocks_boards_outside_the_gap(self):
        bot, channel, cycle_a, _cycle_b = self._bot_finishing_batch_with_queued_successor()
        await bot._runtime_complete_owned_normal_roll_transaction(cycle_a, channel)
        channel.sent.clear()
        bot.sphere_game_counts.update(oq=1)
        bot._sphere_game_retry_after['oq'] = 0.0

        await bot.sphere_runtime.run_available_sphere_games(channel)

        self.assertEqual(channel.sent, [])
        self.assertEqual(bot.sphere_game_counts['oq'], 1)
        self.assertTrue(bot._deferred_independent_known_work)

    def _bot_about_to_start_batch(self):
        bot = _build_runtime()
        channel = _Channel()
        bot._main_channel = bot.command_channel = channel
        bot.auto_oq_enabled = True
        bot.auto_oh_enabled = bot.auto_oc_enabled = bot.auto_ot_enabled = False
        bot.command_pacer.minimum_delay = bot.command_pacer.maximum_delay = 0
        now = datetime.datetime.now(datetime.timezone.utc)
        _anchor, cycle, _next_cycle, _state = _install_anchored_cycle(
            bot, now + datetime.timedelta(minutes=50), now, remaining=5,
        )
        bot.normal_roll_action_owner.schedule(cycle_id=cycle, now_utc=now)
        bot.sphere_game_counts.update(oq=1)
        bot._deferred_independent_known_work = True

        async def send(content, **_kwargs):
            channel.sent.append(content)
            if content == '$oq 1':
                bot._sphere_game_response_future.set_result(SimpleNamespace(id=len(channel.sent)))
            return SimpleNamespace(id=len(channel.sent), created_at=now)

        async def refreshed(*_args):
            return True

        async def start_rolls(_client, _channel, count, *_args):
            channel.sent.append(f'rolls:{count}')

        channel.send = send
        schedule = bot._runtime_schedule_owned_normal_roll_action
        callback = closure(schedule, '_schedule_owned_normal_action_callback').cell_contents
        execute = closure(callback, 'execute_owned_normal_roll_action').cell_contents
        closure(execute, 'refresh_status_before_rolls').cell_contents = refreshed
        closure(execute, 'start_roll_commands').cell_contents = start_rolls
        return bot, channel, cycle, execute

    async def test_deferred_boards_play_before_a_normal_batch_starts(self):
        bot, channel, cycle, execute = self._bot_about_to_start_batch()

        async def play(*_args):
            return True

        with mock.patch.object(bot.sphere_runtime, 'play_sphere_game', side_effect=play):
            await execute(cycle)
            self.assertEqual(channel.sent, ['$oq 1'])
            self.assertEqual(bot.normal_roll_action_owner.state, 'pending')
            self.assertEqual(bot._predicted_roll_action_cycle_id, cycle)
            await execute(cycle)

        self.assertEqual(channel.sent, ['$oq 1', 'rolls:5'])
        self.assertFalse(bot._independent_work_between_batches)

    async def test_failed_boards_do_not_block_the_batch(self):
        bot, channel, cycle, execute = self._bot_about_to_start_batch()

        with mock.patch.object(bot.sphere_runtime, 'play_sphere_game', side_effect=RuntimeError('board broke')):
            await execute(cycle)
            await execute(cycle)

        self.assertEqual(channel.sent, ['$oq 1', 'rolls:5'])
        self.assertFalse(bot._independent_work_between_batches)
        self.assertGreater(bot._sphere_game_retry_after['oq'], mudae_bot.time.monotonic())

    async def test_reset_timed_rolls_keep_boards_after_the_batch(self):
        for setting in ('lurker_mode', 'time_rolls_to_claim_reset'):
            bot, channel, cycle, execute = self._bot_about_to_start_batch()
            setattr(bot, setting, True)
            closure(execute, 'owned_roll_lurker_hold_seconds').cell_contents = lambda: 0

            async def play(*_args):
                return True

            with mock.patch.object(bot.sphere_runtime, 'play_sphere_game', side_effect=play):
                await execute(cycle)
            self.assertEqual(channel.sent, ['rolls:5', '$oq 1'], setting)

    async def test_boards_before_a_batch_still_yield_to_a_pending_claim(self):
        bot, channel, cycle, execute = self._bot_about_to_start_batch()
        bot.pending_claim = object()

        await execute(cycle)
        await execute(cycle)

        self.assertEqual(channel.sent, ['rolls:5'])
        self.assertEqual(bot.sphere_game_counts['oq'], 1)
        self.assertTrue(bot._deferred_independent_known_work)

    async def test_refill_cost_respects_separate_key_and_perk_filters(self):
        for mode, keys, perk, shop, power, refill in (
            ('all', True, True, False, 10, False),
            ('any', True, True, False, 10, True),
            ('any', False, True, True, 20, True),
            ('any', False, True, False, 16, False),
        ):
            bot = _build_runtime()
            bot.auto_dk_enabled = bot.dk_power_management = True
            bot.current_dk_power = power  # check_status commits authoritative power before invoking the handler.
            bot.kakera_filter_match_mode = mode
            bot.only_chaos, bot.perk_eight_only, bot.shop_perk_7_only = keys, perk, shop
            channel = _Channel()
            bot._main_channel = channel
            bot.command_pacer.minimum_delay = bot.command_pacer.maximum_delay = 0
            manage = closure(bot._runtime_check_status, 'handle_dk_power_management').cell_contents
            with mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)):
                await manage(bot, channel, '1 $dk available\nPower: **{}%**\nEach kakera button consumes 30%'.format(power))
            self.assertEqual(channel.sent, ['$dk'] if refill else [], (mode, keys, perk, shop))

    async def test_dk_refill_waits_for_roll_reset_regeneration(self):
        for rolls, minutes, refill in ((0, 30, False), (0, 5, True), (5, 30, True), (None, None, True)):
            with self.subTest(rolls=rolls, minutes=minutes):
                bot = _build_runtime()
                bot.auto_dk_enabled = bot.dk_power_management = True
                bot.auto_dk_min_power = 15
                bot.current_dk_power = 9
                channel = _Channel()
                bot._main_channel = channel
                bot.command_pacer.minimum_delay = bot.command_pacer.maximum_delay = 0
                manage = closure(bot._runtime_check_status, 'handle_dk_power_management').cell_contents
                content = '1 $dk available\nPower: **9%**\nEach kakera button consumes 30%'
                if rolls is not None:
                    content += '\nYou have **{}** rolls left. Next rolls reset in **{}** min.'.format(rolls, minutes)
                with mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)):
                    await manage(bot, channel, content)
                self.assertEqual(channel.sent, ['$dk'] if refill else [])

    async def test_cached_minigames_obey_batch_size_and_finish_before_next(self):
        for individual, expected in ((True, ['$oh 1'] * 13), (False, ['$oh 10', '$oh 3'])):
            bot = _build_runtime()
            channel = _Channel()
            bot._main_channel = channel
            bot.auto_oh_enabled = bot.auto_oc_enabled = True
            bot.oh_use_individually = individual
            bot.auto_p_enabled = bot.auto_mk_enabled = False
            bot.sphere_game_counts.update(oh=13, oc=2)
            bot.command_pacer.minimum_delay = bot.command_pacer.maximum_delay = 0
            work = closure(bot._runtime_check_status, 'run_independent_known_work').cell_contents
            board_active = False
            finished = []

            async def play(_channel, _message, kind):
                nonlocal board_active
                self.assertFalse(board_active)
                board_active = True
                await asyncio.sleep(0)
                finished.append(kind)
                board_active = False
                return True

            async def send(content, **_kwargs):
                self.assertFalse(board_active)
                self.assertEqual(len(channel.sent), len(finished))
                channel.sent.append(content)
                bot._sphere_game_response_future.set_result(SimpleNamespace(id=len(channel.sent)))
                return SimpleNamespace(id=len(channel.sent))

            channel.send = send
            with mock.patch.object(bot.sphere_runtime, 'play_sphere_game', play):
                with mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)):
                    await asyncio.gather(work(channel, None), work(channel, None))
            self.assertEqual(channel.sent, expected + ['$oc 2'])
            self.assertEqual(bot.sphere_game_counts['oc'], 0)

    async def test_unfinished_board_consumes_only_started_stock_and_blocks_next_game(self):
        bot = _build_runtime()
        channel = _Channel()
        bot._main_channel = channel
        bot.auto_oh_enabled = bot.auto_oc_enabled = bot.oh_use_individually = True
        bot.sphere_game_counts.update(oh=3, oc=2)
        bot.command_pacer.minimum_delay = bot.command_pacer.maximum_delay = 0
        async def send(content, **_kwargs):
            channel.sent.append(content)
            bot._sphere_game_response_future.set_result(SimpleNamespace(id=1))
            return SimpleNamespace(id=1)

        channel.send = send
        with mock.patch.object(bot.sphere_runtime, 'play_sphere_game', mock.AsyncMock(return_value=False)):
            await bot.sphere_runtime.run_available_sphere_games(channel)
            await bot.sphere_runtime.run_available_sphere_games(channel)
        self.assertEqual(channel.sent, ['$oh 1'])
        self.assertEqual(bot.sphere_game_counts['oh'], 2)
        self.assertEqual(bot.sphere_game_counts['oc'], 2)

    async def test_failed_owned_roll_action_releases_status_suppression(self):
        bot = _build_runtime()
        cycle = ('roll', 17, 1)
        bot.current_roll_cycle_id = cycle
        bot.normal_roll_action_owner.schedule(cycle_id=cycle, now_utc=datetime.datetime.now(datetime.timezone.utc))
        schedule = closure(bot._runtime_schedule_owned_normal_roll_action, '_schedule_owned_normal_action_callback').cell_contents

        async def fail(_cycle):
            bot.normal_roll_action_owner.start(cycle)
            bot._normal_roll_transaction_cycle_id = cycle
            bot.is_actively_rolling = True
            raise RuntimeError('simulated lost Discord response')

        closure(schedule, 'execute_owned_normal_roll_action').cell_contents = fail
        bot.loop.create_task = asyncio.create_task
        schedule(cycle, 0)
        bot.loop.handles[-1].fire()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertEqual(bot.normal_roll_action_owner.state, 'pending')
        self.assertIsNone(bot._normal_roll_transaction_cycle_id)
        self.assertFalse(bot.is_actively_rolling)
        self.assertIn('normal-action-failed', status_refresh_reasons(bot))
        self.assertTrue(bot._runtime_is_tu_still_required(bot)[0])

    def test_hourly_refresh_is_optional_and_expires_even_with_pending_rolls(self):
        bot = _build_runtime()
        refresh = closure(bot._runtime_check_status, 'request_hourly_status_refresh').cell_contents
        bot.last_tu_snapshot_complete = True
        bot.last_tu_query_utc = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
        bot.current_roll_cycle_id = ('roll', 17, 1)
        bot.normal_roll_action_owner.schedule(cycle_id=bot.current_roll_cycle_id, now_utc=datetime.datetime.now(datetime.timezone.utc))
        clear_status_dirty(bot)
        refresh()
        self.assertFalse(status_dirty_fields(bot))
        bot.hourly_tu_refresh = True
        refresh()
        self.assertIn('hourly-tu-refresh', status_refresh_reasons(bot))
        self.assertTrue(bot._runtime_is_tu_still_required(bot)[0])
        clear_status_dirty(bot)
        bot.last_tu_query_utc = datetime.datetime.now(datetime.timezone.utc)
        refresh()
        self.assertFalse(status_dirty_fields(bot))


class MobileStopTests(unittest.TestCase):
    def test_stop_retains_loop_after_discord_close_clears_it(self):
        loop = asyncio.new_event_loop()
        worker = threading.Thread(target=loop.run_forever)
        worker.start()
        closed = threading.Event()

        class Client:
            def is_closed(self):
                return closed.is_set()

            async def close(self):
                self.loop = None  # discord.py-self clears this before worker cleanup.
                closed.set()

        client = Client()
        client.loop = loop
        mudae_bot.reset_mobile_runtime()
        mudae_bot._active_clients.append(client)
        try:
            mudae_bot.shutdown_mobile_runtime(0.05)
            self.assertTrue(closed.wait(1))
            worker.join(1)
            self.assertFalse(worker.is_alive())
        finally:
            if worker.is_alive():
                loop.call_soon_threadsafe(loop.stop)
                worker.join(1)
            loop.close()
            mudae_bot.reset_mobile_runtime()


if __name__ == '__main__':
    unittest.main()
