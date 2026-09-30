"""Regressions for two user reports: Kakera clicks that stop until a restart, and a $dk that fails and is
not retried until the next scheduled $tu."""
import datetime
import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import mudae_bot
from mudae_core.coordinator import GlobalIntervalCoordinator
from mudae_core.status import clear_status_dirty
from tests.test_kakera_snipe_ownership import _Channel, _build_roll_message, _create_test_client


class DkKakeraRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sleeps = []

        async def sleep(_client, seconds, *args, **kwargs):
            self.sleeps.append(seconds)
            return True

        for patch in (
            mock.patch.object(mudae_bot, 'pause_interruptible_sleep', sleep),
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

    async def status(self, reaction='You can react', power=90):
        snapshot = (
            'You can claim now!\nNext claim reset in **60** min.\n'
            'You have **10** rolls left. Next rolls reset in **60** min.\n'
            '$rt is available!\nPower: **%s%%**\n'
            'Each kakera reaction consumes 40%%\n1 $dk available\n'
            '$daily is on cooldown.\n$p is unavailable.\n18/20 buttons clicked.\n%s'
        ) % (power, reaction)

        async def send(content, **kwargs):
            self.command_channel.sent.append(content)
            if content == '$tu':
                self.bot._tu_response_future.set_result(snapshot)
            return SimpleNamespace(id=len(self.command_channel.sent))

        self.command_channel.send = send
        self.bot.last_tu_snapshot_complete = False
        self.bot.last_tu_query_utc = None
        self.bot._tu_next_allowed_monotonic = 0
        await self.bot._runtime_check_status(self.bot, self.channel, '$', proceed_to_rolls=False)
        self.assertIn('$tu', self.command_channel.sent)

    # ---- Kakera clicks silently stopping ----------------------------------------------------
    async def test_a_reaction_block_without_a_readable_wait_expires(self):
        bot = self.bot
        await self.status(reaction="**Can't react to kakera right now**")      # no minutes to parse
        self.assertIs(bot.kakera_react_available, False)
        until = bot.kakera_react_cooldown_until_utc
        self.assertIsNotNone(until, "an unreadable wait must not block Kakera forever")
        now = datetime.datetime.now(datetime.timezone.utc)
        self.assertLessEqual(until - now, datetime.timedelta(minutes=mudae_bot.KAKERA_COOLDOWN_FALLBACK_MINUTES, seconds=5))

        msg, button = _build_roll_message(self.channel, 9000, bot.user.id, bot.user.name, 'kakeraO', client=bot)
        bot.kakera_emojis = ['kakeraO']
        bot.current_dk_power = 100
        await bot.events['on_message'](msg)
        button.click.assert_not_awaited()                                      # still inside the short block

        bot.kakera_react_cooldown_until_utc = now - datetime.timedelta(seconds=1)
        msg, button = _build_roll_message(self.channel, 9001, bot.user.id, bot.user.name, 'kakeraO', client=bot)
        await bot.events['on_message'](msg)
        button.click.assert_awaited_once()                                     # no restart needed
        self.assertIs(bot.kakera_react_available, True)

    async def test_a_readable_wait_is_still_used(self):
        await self.status(reaction="You can't react to kakera for **1h 20** min.")
        now = datetime.datetime.now(datetime.timezone.utc)
        wait = self.bot.kakera_react_cooldown_until_utc - now
        self.assertTrue(datetime.timedelta(minutes=79) < wait <= datetime.timedelta(minutes=80, seconds=5), wait)

    # ---- $dk ---------------------------------------------------------------------------------
    def refill_setup(self, power=10, stock=2):
        bot = self.bot
        bot.current_dk_power, bot.dk_consumption = power, 15
        bot.auto_dk_enabled = bot.dk_power_management = True
        bot.auto_dk_min_power, bot.dk_stock_count = 30, stock
        return bot

    def stop_sign(self, message_id, user_id=None):
        return SimpleNamespace(
            message_id=message_id, user_id=user_id or mudae_bot.TARGET_BOT_ID,
            emoji=SimpleNamespace(name='🛑'), channel_id=5678,
        )

    def command_channel_refusing(self, refusals):
        """$dk messages are refused (stop-sign reaction) for the first `refusals` sends."""
        bot, sent = self.bot, self.command_channel.sent

        async def send(content, **kwargs):
            sent.append(content)
            message = SimpleNamespace(id=8000 + len(sent), created_at=datetime.datetime.now(datetime.timezone.utc))
            if content == '$dk' and sent.count('$dk') <= refusals:
                asyncio.get_running_loop().call_later(
                    0.01, lambda: asyncio.ensure_future(bot.events['on_raw_reaction_add'](self.stop_sign(message.id))))
            return message

        self.command_channel.send = send

    async def refill(self, power=10, message_id=1006):
        """Trigger a refill the way a paid click does, without a click."""
        bot = self.refill_setup(power)
        message, button = _build_roll_message(self.channel, message_id, bot.user.id, bot.user.name)
        result = SimpleNamespace(
            id=message_id + 1, channel=self.channel, author=message.author,
            content='<:kakeraY:123> **snipe-bot +515** ($k)',
            created_at=message.created_at, embeds=[], components=[], interaction=None,
        )

        async def deliver_result():
            await bot.events['on_message'](result)

        button.click.side_effect = deliver_result
        await bot.events['on_message'](message)
        await bot.events['on_message'](message)
        return button

    async def test_dk_after_a_paid_click_waits_only_a_moment_for_mudae_to_settle(self):
        await self.refill(power=40)
        self.assertEqual(self.command_channel.sent.count('$dk'), 1)
        settle = [s for s in self.sleeps if s >= mudae_bot.DK_SETTLE_SECONDS]
        self.assertTrue(settle and max(settle) < 1.0, self.sleeps)

    async def test_a_dk_mudae_refuses_with_a_stop_sign_is_retried(self):
        self.command_channel_refusing(refusals=1)
        bot = self.refill_setup(power=40)
        await self.refill(power=40)
        self.assertEqual(self.command_channel.sent.count('$dk'), 2)
        self.assertEqual(bot.dk_stock_count, 1, 'only the accepted $dk uses up stock')
        self.assertEqual(bot.current_dk_power, bot.max_dk_power)

    async def test_a_dk_that_stays_refused_pauses_instead_of_waiting_for_a_tu(self):
        self.command_channel_refusing(refusals=99)
        bot = self.refill_setup(power=40)
        await self.refill(power=40)
        self.assertEqual(self.command_channel.sent.count('$dk'), len(mudae_bot.DK_RETRY_DELAYS) + 1)
        self.assertEqual(bot.dk_stock_count, 2, 'a refused $dk must not use up stock')
        self.assertLess(bot.current_dk_power, 100)
        self.assertGreater(bot._dk_refused_until, time.monotonic())
        bot._dk_refused_until = time.monotonic() - 1                           # the pause is over: it tries again
        self.command_channel_refusing(refusals=0)
        self.command_channel.sent.clear()
        await self.refill(power=10, message_id=2006)
        self.assertEqual(self.command_channel.sent.count('$dk'), 1)

    async def test_only_mudaes_stop_sign_on_the_dk_counts(self):
        self.command_channel_refusing(refusals=0)
        bot = self.refill_setup(power=40)
        original = self.command_channel.send

        async def send(content, **kwargs):
            message = await original(content, **kwargs)
            if content == '$dk':                                               # someone else reacting must not matter
                asyncio.get_running_loop().call_later(
                    0.01, lambda: asyncio.ensure_future(
                        bot.events['on_raw_reaction_add'](self.stop_sign(message.id, user_id=123))))
            return message

        self.command_channel.send = send
        await self.refill(power=40)
        self.assertEqual(self.command_channel.sent.count('$dk'), 1)
        self.assertEqual(bot.dk_stock_count, 1)


if __name__ == '__main__':
    unittest.main()
