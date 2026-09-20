"""Runtime regressions for stale collection state and Chaos power receipts."""
import datetime
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from mudae_core.coordinator import GlobalIntervalCoordinator
from mudae_core.status import clear_status_dirty, status_dirty_fields
from tests.test_kakera_snipe_ownership import _create_test_client, _build_roll_message, _Channel


DISCOUNT = '50% kakera power discount when you clicked on this chaos kakera.'


class KakeraFeedbackRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        for patch in (
            mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)),
            mock.patch.object(mudae_bot.BotLogger, 'log'),
            mock.patch.object(mudae_bot, '_tu_interval_coordinator', GlobalIntervalCoordinator()),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.bot, self.channel = _create_test_client()
        clear_status_dirty(self.bot)
        self.bot.dk_consumption = 40
        self.command_channel = _Channel(5678, lambda: self.bot)
        self.bot._fetched_channels[5678] = self.command_channel

    def content(self, text, channel=None, message_id=9101):
        return SimpleNamespace(
            id=message_id, channel=channel or self.channel,
            author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID), content=text,
            created_at=datetime.datetime.now(datetime.timezone.utc),
            embeds=[], components=[], interaction=None,
        )

    async def status(self, reaction='You can react', quota='18/20', power=90, during_send=None):
        snapshot = (
            'You can claim now!\nNext claim reset in **60** min.\n'
            'You have **10** rolls left. Next rolls reset in **60** min.\n'
            '$rt is available!\nPower: **%s%%**\n'
            'Each kakera reaction consumes 40%%\n$dk is available!\n'
            '$daily is available!\n$p is available!\n%s buttons clicked.\n%s'
        ) % (power, quota, reaction)
        async def send(content, **kwargs):
            self.command_channel.sent.append(content)
            if content == '$tu':
                if during_send is not None:
                    await during_send()
                self.bot._tu_response_future.set_result(snapshot)
            return SimpleNamespace(id=len(self.command_channel.sent))
        self.command_channel.send = send
        self.bot.last_tu_snapshot_complete = False
        self.bot.last_tu_query_utc = None
        self.bot._tu_next_allowed_monotonic = 0
        await self.bot._runtime_check_status(self.bot, self.channel, '$', proceed_to_rolls=False)
        self.assertIn('$tu', self.command_channel.sent)

    async def chaos_result(self, suffix='', message_id=9200):
        self.bot.kakera_emojis = self.bot.chaos_emojis = ['kakeraC']
        msg, button = _build_roll_message(
            self.channel, message_id, self.bot.user.id, self.bot.user.name, 'kakeraC',
        )
        msg.embeds[0].description += '\n<:chaoskey:123> (**10**)'
        async def result():
            await self.bot.events['on_message'](self.content(
                '<:kakeraC:123> **snipe-bot +150** ($k)\n' + suffix,
                message_id=message_id + 1,
            ))
        button.click.side_effect = result
        await self.bot.events['on_message'](msg)
        button.click.assert_awaited_once()
        self.assertEqual(self.bot.current_dk_power, 80)

    async def test_unknown_reaction_uses_power_not_false_cooldown(self):
        self.bot.kakera_react_available = None
        self.bot.kakera_emojis = ['kakeraO', 'kakeraL']
        for index, (power, name, expected) in enumerate(((100, 'kakeraO', True), (20, 'kakeraL', False), (100, 'kakeraY', False))):
            self.bot.current_dk_power = power
            msg, button = _build_roll_message(self.channel, 9000 + index, self.bot.user.id, self.bot.user.name, name, client=self.bot)
            await self.bot.events['on_message'](msg)
            self.assertEqual(button.click.await_count, int(expected))
        self.bot.kakera_react_available = False
        self.bot.kakera_react_cooldown_until_utc = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
        msg, button = _build_roll_message(self.channel, 9005, self.bot.user.id, self.bot.user.name, 'kakeraO', client=self.bot)
        await self.bot.events['on_message'](msg)
        button.click.assert_not_awaited()

    async def test_plain_readiness_and_localized_rejections(self):
        for line, expected in (('You can react', True), ('You __can__ react', True), ('**Não pode reagir**', False), ('__No puedes reaccionar__', False)):
            with self.subTest(line=line):
                self.bot.kakera_react_available = None
                await self.status(reaction=line)
                self.assertEqual(self.bot.kakera_react_available, expected)

    async def test_provisional_sphere_cap_recovers_selected_double(self):
        bot = self.bot
        bot.sphere_click_targets = {'spg'}
        before = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)
        bot.sphere_button_budget.observe('19/20 buttons clicked', before)
        bot.sphere_button_budget.reserve('ambiguous-click', before)
        msg, button = _build_roll_message(self.channel, 9300, bot.user.id, bot.user.name, 'spG2')
        await bot.events['on_message'](msg)
        button.click.assert_not_awaited()
        self.assertIn('points', status_dirty_fields(bot))
        await self.status(quota='18/20')
        self.assertNotIn('points', status_dirty_fields(bot))
        msg, button = _build_roll_message(self.channel, 9302, bot.user.id, bot.user.name, 'spG2')
        await bot.events['on_message'](msg)
        await bot.events['on_message'](msg)
        button.click.assert_awaited_once()
        excluded, excluded_button = _build_roll_message(self.channel, 9301, bot.user.id, bot.user.name, 'spB2')
        await bot.events['on_message'](excluded)
        excluded_button.click.assert_not_awaited()

    async def test_confirmed_sphere_cap_waits_until_refill(self):
        bot = self.bot
        now = datetime.datetime.now(datetime.timezone.utc)
        bot.sphere_button_budget.observe('20/20 buttons clicked', now)
        bot.sphere_game_refill_at_utc = now + datetime.timedelta(hours=1)
        msg, button = _build_roll_message(self.channel, 9310, bot.user.id, bot.user.name, 'spG2')
        await bot.events['on_message'](msg)
        self.assertNotIn('points', status_dirty_fields(bot))
        bot.sphere_game_refill_at_utc = now - datetime.timedelta(seconds=1)
        msg, button = _build_roll_message(self.channel, 9311, bot.user.id, bot.user.name, 'spG2')
        await bot.events['on_message'](msg)
        button.click.assert_not_awaited()
        self.assertIn('points', status_dirty_fields(bot))
        await self.status(quota='0/20')
        msg, button = _build_roll_message(self.channel, 9312, bot.user.id, bot.user.name, 'spG2')
        await bot.events['on_message'](msg)
        button.click.assert_awaited_once()

    async def test_same_message_discount_reconciles_without_early_dk(self):
        bot = self.bot
        bot.auto_dk_enabled = bot.dk_power_management = True
        bot.auto_dk_min_power = 90
        bot.dk_stock_count = 1
        await self.chaos_result(DISCOUNT.replace('50%', '**50%**'))
        self.assertIn('power', status_dirty_fields(bot))
        self.assertNotIn('$dk', self.command_channel.sent)
        await self.status(power=90)
        self.assertEqual(bot.current_dk_power, 90)
        self.assertNotIn('power', status_dirty_fields(bot))
        # Duplicate receipt cannot re-arm the consumed context.
        await bot.events['on_message'](self.content(DISCOUNT))
        self.assertNotIn('power', status_dirty_fields(bot))

    async def test_followup_discount_survives_extra_roll_bonus(self):
        self.bot.rolling_enabled = True
        await self.chaos_result()
        self.assertNotIn('power', status_dirty_fields(self.bot))
        before = self.bot.rolls_left
        await self.bot.events['on_message'](self.content('+5 rolls this hour.'))
        self.assertEqual(self.bot.rolls_left, before + 5)
        await self.bot.events['on_message'](self.content(DISCOUNT))
        self.assertIn('power', status_dirty_fields(self.bot))

    async def test_foreign_channel_expired_and_unrelated_bonus_do_not_reconcile(self):
        await self.chaos_result()
        for message in (
            self.content(DISCOUNT, channel=self.command_channel),
            self.content('50% discount on another item'),
        ):
            await self.bot.events['on_message'](message)
            self.assertNotIn('power', status_dirty_fields(self.bot))
        with mock.patch.object(mudae_bot.time, 'monotonic', return_value=time.monotonic() + 11):
            await self.bot.events['on_message'](self.content(DISCOUNT))
        self.assertNotIn('power', status_dirty_fields(self.bot))
        self.assertEqual(self.bot.current_dk_power, 80)

    async def test_foreign_reward_breaks_anonymous_bonus_attribution(self):
        await self.chaos_result()
        await self.bot.events['on_message'](self.content(
            '<:kakeraC:123> **someone-else +150** ($k)\n' + DISCOUNT,
        ))
        await self.bot.events['on_message'](self.content(DISCOUNT))
        self.assertNotIn('power', status_dirty_fields(self.bot))
        self.assertEqual(self.bot.current_dk_power, 80)

    async def test_discount_during_status_send_invalidates_old_power(self):
        await self.chaos_result()
        async def discount_during_send():
            await self.bot.events['on_message'](self.content(DISCOUNT))
        await self.status(power=80, during_send=discount_during_send)
        self.assertIn('power', status_dirty_fields(self.bot))
        await self.status(power=90)
        self.assertEqual(self.bot.current_dk_power, 90)
        self.assertNotIn('power', status_dirty_fields(self.bot))


if __name__ == '__main__':
    unittest.main()
