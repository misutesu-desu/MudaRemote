"""Regressions for the reported sphere quota and pre-roll daily-reset failures."""
import asyncio
import datetime
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from mudae_core.coordinator import GlobalIntervalCoordinator
from mudae_core.runtime import is_tu_still_required
from mudae_core.spheres import SphereButtonBudget, parse_sphere_button_count
from mudae_core.status import clear_status_dirty
from tests.test_kakera_snipe_ownership import _create_test_client, _build_roll_message
from tests.test_roll_window_production import _build_runtime, _Channel
from tests.test_tu_retry import production_functions


class SphereBudgetTests(unittest.TestCase):
    def test_reported_quota_is_not_perk_eight_or_nine(self):
        text = ('0 $oh left for today, 0 $oc, 0 $og and 0 $ot.\n'
                '14h 52 min before the refill. **7/20** buttons clicked.\n'
                'Stock: 1,744\n(Perk 8) Clicked today: 0/40.\n'
                '(Perk 9) Rolled today: 121/121')
        self.assertEqual(parse_sphere_button_count(text), (7, 20))
        self.assertIsNone(parse_sphere_button_count('(Perk 8) Clicked today: 0/40.'))

    def test_reservations_stop_at_cap_and_fresh_reset_reopens_quota(self):
        budget = SphereButtonBudget()
        budget.observe('7/20 buttons clicked', 1)
        for key in range(13):
            self.assertTrue(budget.available)
            budget.reserve(key, 2)
        self.assertFalse(budget.available)
        self.assertEqual(budget.clicked, 7)  # Dispatch is not a credited reward.
        budget.observe('20/20 buttons clicked', 3)
        self.assertFalse(budget.available)
        budget.observe('0/20 buttons clicked', 4)
        self.assertTrue(budget.available)
        self.assertFalse(budget.pending)

    def test_snapshot_preserves_clicks_sent_while_query_was_in_flight(self):
        budget = SphereButtonBudget()
        budget.reserve('before', 1)
        budget.reserve('during', 3)
        budget.observe('19/20 buttons clicked', 2)
        self.assertEqual(budget.pending, {'during': 3})
        self.assertFalse(budget.available)


class SphereDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_sphere_does_not_wait_for_kakera_reward_or_retry(self):
        for emoji in ('spG', 'spD', 'spB2', 'sp'):
            with self.subTest(emoji=emoji):
                bot, channel = _create_test_client()
                bot.sphere_click_targets.add(mudae_bot.normalize_character_sphere_emoji(emoji).casefold())
                bot.sphere_button_budget.observe('7/20 buttons clicked', datetime.datetime.now(datetime.timezone.utc))
                message, button = _build_roll_message(channel, 5101, bot.user.id, bot.user.name, emoji)
                button.click.return_value = SimpleNamespace(successful=True)
                button.click.side_effect = None
                with mock.patch.object(mudae_bot.asyncio, 'wait_for', side_effect=AssertionError('sphere waited for kakera')):
                    await bot.events['on_message'](message)
                    await bot.events['on_message'](message)
                button.click.assert_awaited_once()
                self.assertFalse(bot._kakera_result_waiters)
                self.assertEqual(bot.sphere_button_budget.clicked, 7)
                self.assertEqual(len(bot.sphere_button_budget.pending), 1)

    async def test_full_quota_does_not_click(self):
        bot, channel = _create_test_client()
        bot.sphere_button_budget.observe('20/20 buttons clicked', datetime.datetime.now(datetime.timezone.utc))
        message, button = _build_roll_message(channel, 5201, bot.user.id, bot.user.name, 'spG')
        await bot.events['on_message'](message)
        button.click.assert_not_awaited()

    async def test_ambiguous_delivery_is_not_retried_and_rejection_releases_budget(self):
        for ambiguous in (True, False):
            bot, channel = _create_test_client()
            message, button = _build_roll_message(channel, 5301, bot.user.id, bot.user.name, 'spD')
            button.click.side_effect = mudae_bot.discord.InvalidData('Did not receive a response from Discord') if ambiguous else None
            button.click.return_value = SimpleNamespace(successful=False)
            await bot.events['on_message'](message)
            await bot.events['on_message'](message)
            button.click.assert_awaited_once()
            self.assertEqual(len(bot.sphere_button_budget.pending), int(ambiguous))


class PreRollStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_forced_status_runs_daily_commands_even_with_executing_owner(self):
        for owner_state in ('pending', 'executing'):
            for dk_status in ('$dk is ready!', '$dk is available!', '1 $dk available'):
                with self.subTest(owner=owner_state, dk=dk_status):
                    bot = _build_runtime()
                    channel = _Channel(bot.target_channel_id)
                    bot._main_channel = channel
                    bot.auto_dk_enabled = True
                    bot.dk_power_management = False
                    bot.auto_p_enabled = True
                    bot.normal_roll_action_owner.state = owner_state
                    bot.last_tu_snapshot_complete = True
                    bot.last_tu_query_utc = datetime.datetime.now(datetime.timezone.utc)
                    bot.rolls_left = 0
                    clear_status_dirty(bot)
                    bot._pre_roll_status_required = True
                    bot.command_pacer.minimum_delay = bot.command_pacer.maximum_delay = 0
                    snapshot = ('You can claim now!\nNext claim reset in **60** min.\n'
                                'You have **10** rolls left. Next rolls reset in **60** min.\n'
                                '$rt is available!\nPower: **100%**\n' + dk_status + '\n'
                                '$daily is available!\n$p is available!\n7/20 buttons clicked.\n'
                                '(Perk 8) Clicked today: 0/40.')

                    async def send(content, **kwargs):
                        channel.sent.append(content)
                        if content == '$tu':
                            bot._tu_response_future.set_result(snapshot)
                        return SimpleNamespace(id=len(channel.sent))

                    channel.send = send
                    with mock.patch.object(mudae_bot, '_tu_interval_coordinator', GlobalIntervalCoordinator()), \
                            mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)):
                        self.assertTrue(is_tu_still_required(bot)[0])
                        await bot._runtime_check_status(bot, channel, '$', proceed_to_rolls=False)
                    self.assertEqual(channel.sent, ['$tu', '$daily', '$dk', '$p'])
                    self.assertTrue(bot.last_tu_snapshot_complete)
                    self.assertEqual(bot.sphere_button_budget.clicked, 7)
                    self.assertEqual(bot._pre_roll_status_cycle_id, bot.current_roll_cycle_id)

    async def test_pre_roll_helper_refuses_partial_or_failed_status(self):
        bot = _build_runtime()
        bot.current_roll_cycle_id = ('roll', 1, 1)
        bot.last_tu_snapshot_complete = False
        check = mock.AsyncMock()
        scope = dict(client=bot, datetime=datetime, timezone=datetime.timezone.utc,
                     status_dirty_fields=mudae_bot.status_dirty_fields,
                     mark_status_dirty=mudae_bot.mark_status_dirty, check_status=check)
        exec(production_functions('refresh_status_before_rolls'), scope)
        self.assertFalse(await scope['refresh_status_before_rolls'](object(), bot.current_roll_cycle_id))
        check.assert_awaited_once()
        self.assertFalse(bot._pre_roll_status_required)

    async def test_new_cycle_cannot_reuse_recent_previous_cycle_status(self):
        bot = _build_runtime()
        bot.current_roll_cycle_id = ('roll', 2, 1)
        bot._pre_roll_status_cycle_id = ('roll', 1, 1)
        bot.last_tu_snapshot_complete = True
        bot.last_tu_query_utc = datetime.datetime.now(datetime.timezone.utc)
        clear_status_dirty(bot)
        check = mock.AsyncMock()
        scope = dict(client=bot, datetime=datetime, timezone=datetime.timezone.utc,
                     status_dirty_fields=mudae_bot.status_dirty_fields,
                     mark_status_dirty=mudae_bot.mark_status_dirty, check_status=check)
        exec(production_functions('refresh_status_before_rolls'), scope)
        self.assertFalse(await scope['refresh_status_before_rolls'](object(), bot.current_roll_cycle_id))
        check.assert_awaited_once()

    async def test_midnight_invalidates_an_otherwise_recent_snapshot(self):
        bot = _build_runtime()
        before_reset = datetime.datetime(2026, 9, 10, 23, 59, 59, tzinfo=datetime.timezone.utc)
        after_reset = before_reset + datetime.timedelta(seconds=2)
        bot.current_roll_cycle_id = bot._pre_roll_status_cycle_id = ('roll', 1, 1)
        bot._pre_roll_status_requested_at = before_reset
        bot.last_tu_snapshot_complete = True
        clear_status_dirty(bot)
        clock = mock.Mock()
        clock.datetime.now.return_value = after_reset
        check = mock.AsyncMock()
        scope = dict(client=bot, datetime=clock, timezone=datetime.timezone.utc,
                     status_dirty_fields=mudae_bot.status_dirty_fields,
                     mark_status_dirty=mudae_bot.mark_status_dirty, check_status=check)
        exec(production_functions('refresh_status_before_rolls'), scope)
        self.assertFalse(await scope['refresh_status_before_rolls'](object(), bot.current_roll_cycle_id))
        check.assert_awaited_once()

    async def test_recent_same_cycle_snapshot_does_not_send_duplicate_tu(self):
        bot = _build_runtime()
        bot.current_roll_cycle_id = bot._pre_roll_status_cycle_id = ('roll', 1, 1)
        bot._pre_roll_status_requested_at = datetime.datetime.now(datetime.timezone.utc)
        bot.last_tu_snapshot_complete = True
        clear_status_dirty(bot)
        check = mock.AsyncMock()
        scope = dict(client=bot, datetime=datetime, timezone=datetime.timezone.utc,
                     status_dirty_fields=mudae_bot.status_dirty_fields,
                     mark_status_dirty=mudae_bot.mark_status_dirty, check_status=check)
        exec(production_functions('refresh_status_before_rolls'), scope)
        self.assertTrue(await scope['refresh_status_before_rolls'](object(), bot.current_roll_cycle_id))
        check.assert_not_awaited()


class RollPatienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_channel_does_not_bypass_patience_after_tu_wait_cap(self):
        client = SimpleNamespace(is_paused=False, humanization_enabled=True,
                                 humanization_inactivity_seconds=120, humanization_window_minutes=0)
        now = datetime.datetime.now(datetime.timezone.utc)
        samples = [now, now, now - datetime.timedelta(seconds=121)]

        async def history(limit):
            yield SimpleNamespace(created_at=samples.pop(0))

        delay = mock.AsyncMock(return_value=True)
        scope = dict(client=client, datetime=datetime, timezone=datetime.timezone.utc,
                     is_maintenance_active=lambda: False, is_inactive_hour=lambda: False,
                     active_delay=delay, BotLogger=mock.Mock(), preset_name='test',
                     TU_INACTIVITY_MAX_TOTAL_WAIT_SECONDS=1, TARGET_BOT_ID=42)
        exec(production_functions('wait_for_tu_inactivity'), scope)
        ready, waited = await scope['wait_for_tu_inactivity'](SimpleNamespace(history=history), before_roll=True)
        self.assertTrue(ready and waited)
        self.assertEqual(delay.await_count, 2)


if __name__ == '__main__':
    unittest.main()
