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

    async def test_a_refused_click_means_no_power_and_uses_a_dk_instead_of_clicking_on(self):
        bot = self.refill_setup(power=100)                    # the estimate says plenty, Mudae says none
        bot.dk_consumption, bot.auto_dk_min_power = 40, 0
        bot.kakera_emojis = ['kakeraO']
        self.command_channel_refusing(refusals=0)
        rejection = SimpleNamespace(
            id=9101, channel=self.channel, author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
            content="<@%s> You can't react to kakera for **40** min." % bot.user.id,
            created_at=datetime.datetime.now(datetime.timezone.utc), embeds=[], components=[], interaction=None,
        )
        msg, button = _build_roll_message(self.channel, 9100, bot.user.id, bot.user.name, 'kakeraO', client=bot)
        confirm = button.click.side_effect

        async def click():
            if button.click.await_count == 1:
                await bot.events['on_message'](rejection)     # first click is refused
            else:
                await confirm()                               # the click after the $dk works

        button.click.side_effect = click
        self.channel.fetch_message = mock.AsyncMock(return_value=msg)
        await bot.events['on_message'](msg)
        self.assertEqual(self.command_channel.sent.count('$dk'), 1)
        self.assertEqual(button.click.await_count, 2)
        self.assertIs(bot.kakera_react_available, True, '$dk lifts the refusal')
        self.assertEqual(bot.dk_stock_count, 1)

    # ---- Mudae answers $dk with a question ---------------------------------------------------
    PROMPT = ('You have enough power to react to kakera right now (%d%%). '
              'Do you really want to use $dk? (y/n/yes/no)\nSkip confirmation with $dky')
    BUSY = 'A command is already awaiting an answer! Type $exit to decline the other command.'

    def command_channel_answering(self, answers, snapshot=None):
        """Mudae posts answers[n] in the command channel after the n-th $dk."""
        bot, sent = self.bot, self.command_channel.sent

        async def send(content, **kwargs):
            sent.append(content)
            message = SimpleNamespace(id=8000 + len(sent), created_at=datetime.datetime.now(datetime.timezone.utc))
            if content == '$tu' and snapshot:
                bot._tu_response_future.set_result(snapshot)
            elif content == '$dk' and sent.count('$dk') <= len(answers):
                answer = SimpleNamespace(
                    id=9500 + len(sent), channel=self.command_channel,
                    author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
                    content=answers[sent.count('$dk') - 1],
                    created_at=message.created_at, embeds=[], components=[], interaction=None,
                )
                asyncio.get_running_loop().call_later(
                    0.01, lambda: asyncio.ensure_future(bot.events['on_message'](answer)))
            return message

        self.command_channel.send = send

    async def test_a_dk_mudae_questions_is_kept_when_the_real_power_is_enough(self):
        # Reported: the estimate was too low, Mudae asked for confirmation, nobody answered and
        # the bot believed the $dk was used.
        self.command_channel_answering([self.PROMPT % 60])
        bot = self.refill_setup(power=10)                      # trigger is 30, the click costs 15
        await self.refill(power=10)
        self.assertEqual(self.command_channel.sent, ['$dk', 'n'])
        self.assertEqual(bot.dk_stock_count, 2, 'a declined $dk must not use up stock')
        self.assertEqual(bot.current_dk_power, 45, "Mudae's number replaces the estimate")

    async def test_a_dk_mudae_questions_is_confirmed_when_power_is_under_the_trigger(self):
        self.command_channel_answering([self.PROMPT % 20])
        bot = self.refill_setup(power=20)                      # trigger is 30
        await self.refill(power=20)
        self.assertEqual(self.command_channel.sent, ['$dk', 'y'])
        self.assertEqual(bot.dk_stock_count, 1)
        self.assertEqual(bot.current_dk_power, bot.max_dk_power - 15)

    async def test_a_dk_lost_to_another_pending_command_is_retried(self):
        self.command_channel_answering([self.BUSY])
        bot = self.refill_setup(power=20)
        await self.refill(power=20)
        self.assertEqual(self.command_channel.sent.count('$dk'), 2)
        self.assertEqual(bot.dk_stock_count, 1, 'only the accepted $dk uses up stock')

    # ---- Auto $dk Daily Schedule -------------------------------------------------------------
    async def scheduled_status(self, answers, smart_refill, schedule='00:00'):
        """One $tu with plenty of power while the schedule is due and unused today."""
        bot = self.bot
        bot.rolling_enabled = True
        bot.auto_dk_enabled = True
        bot.dk_power_management = smart_refill
        bot.auto_dk_min_power = 0
        bot.auto_p_enabled = False
        bot.dk_schedule_time = schedule
        bot._last_scheduled_dk_window = None
        snapshot = (
            'You can claim now!\nNext claim reset in **60** min.\n'
            'You have **10** rolls left. Next rolls reset in **60** min.\n'
            '$rt is available!\nPower: **90%**\n'
            'Each kakera reaction consumes 40%\n'
            '1 $dk available\n$daily is on cooldown.\n$p is unavailable.\n18/20 buttons clicked.\nYou can react'
        )
        self.command_channel_answering(answers, snapshot)
        bot.last_tu_snapshot_complete = False
        bot.last_tu_query_utc = None
        bot._tu_next_allowed_monotonic = 0
        await bot._runtime_check_status(bot, self.channel, '$', proceed_to_rolls=False)
        return bot

    async def test_the_schedule_also_runs_with_smart_power_refill_on(self):
        # Reported: with both settings on the scheduled time was ignored and $dk only went out
        # when power ran low during rolls.
        bot = await self.scheduled_status([], smart_refill=True)
        self.assertEqual(self.command_channel.sent.count('$dk'), 1)
        self.assertEqual(bot.dk_stock_count, 0)
        self.assertIsNotNone(bot._last_scheduled_dk_window)

    async def test_smart_power_refill_without_a_schedule_keeps_dk_while_power_is_high(self):
        bot = await self.scheduled_status([], smart_refill=True, schedule='')
        self.assertNotIn('$dk', self.command_channel.sent)
        self.assertEqual(bot.dk_stock_count, 1)

    async def test_a_scheduled_dk_answers_mudaes_question(self):
        bot = await self.scheduled_status([self.PROMPT % 90], smart_refill=False)
        self.assertEqual([c for c in self.command_channel.sent if c != '$tu'], ['$dk', 'y'])
        self.assertEqual(bot.dk_stock_count, 0)
        self.assertIsNotNone(bot._last_scheduled_dk_window)

    async def test_a_refused_scheduled_dk_stays_due(self):
        bot = await self.scheduled_status([self.BUSY], smart_refill=False)
        self.assertEqual(bot.dk_stock_count, 1)
        self.assertIsNone(bot._last_scheduled_dk_window)


class PowerAboveConfiguredMaximumTests(unittest.TestCase):
    def test_regeneration_does_not_cut_reported_power_to_the_setting(self):
        # $tu reported 161% while Maximum DK Power was left at 100: the
        # estimate fell to 100 after three minutes and paid Kakera was skipped.
        bot, _channel = _create_test_client()
        bot.max_dk_power = 100
        bot.current_dk_power = 161
        bot.last_dk_power_update_utc = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
        )
        self.assertEqual(bot._runtime_get_current_dk_power(), 161)

    def test_regeneration_still_stops_at_the_setting(self):
        bot, _channel = _create_test_client()
        bot.max_dk_power = 100
        bot.current_dk_power = 95
        bot.last_dk_power_update_utc = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
        )
        self.assertEqual(bot._runtime_get_current_dk_power(), 100)


if __name__ == '__main__':
    unittest.main()
