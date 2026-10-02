"""A $tu that says "You can't react to kakera" is a status, not a refused click.

Treating it as a refusal zeroed the power estimate and bumped the power revision while the
$tu was still in flight, so every answer looked "changed during $tu" and the bot asked again
every few seconds for as long as the Kakera cooldown lasted.
"""
import asyncio
import datetime
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from mudae_core.coordinator import GlobalIntervalCoordinator
from mudae_core.status import clear_status_dirty, status_dirty_fields, status_refresh_reasons
from tests.test_kakera_snipe_ownership import _Channel, _create_test_client


class TuKakeraCooldownLoopTests(unittest.IsolatedAsyncioTestCase):
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
        self.bot.dk_consumption = 100
        self.command_channel = _Channel(5678, lambda: self.bot)
        self.bot._fetched_channels[5678] = self.command_channel

    def snapshot(self):
        return (
            '**%s**, you can claim right now! The next claim reset is in **2h 01** min.\n'
            'You have **0** rolls left. Next rolls reset in **40** min.\n'
            "You can't react to kakera for **3h 25** min.\n"
            'Power: **31%%**\nEach kakera button consumes 100%% of your reaction power.\n'
            'Stock: **234**\nNext $dk in 9h 10 min.\n'
        ) % self.bot.user.name

    async def check(self):
        async def send(content, **kwargs):
            self.command_channel.sent.append(content)
            if content == '$tu':
                text = self.snapshot()
                # The real answer reaches on_message as well as the waiting future.
                await self.bot.events['on_message'](SimpleNamespace(
                    id=9000 + len(self.command_channel.sent), channel=self.channel,
                    author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID), content=text,
                    created_at=datetime.datetime.now(datetime.timezone.utc),
                    embeds=[], components=[], interaction=None,
                ))
                if not self.bot._tu_response_future.done():
                    self.bot._tu_response_future.set_result(text)
            return SimpleNamespace(id=len(self.command_channel.sent))

        self.command_channel.send = send
        await asyncio.wait_for(
            self.bot._runtime_check_status(self.bot, self.channel, '$', proceed_to_rolls=False), 10,
        )

    async def test_tu_status_is_not_treated_as_a_refused_click(self):
        bot = self.bot
        bot.current_dk_power = 80
        revision = bot.dk_power_revision
        await self.check()
        self.assertEqual(self.command_channel.sent.count('$tu'), 1)
        self.assertEqual(bot.current_dk_power, 31, 'the $tu power is authoritative, not zero')
        self.assertNotIn('power', status_dirty_fields(bot), status_refresh_reasons(bot))
        self.assertNotIn('power-changed-during-tu', status_refresh_reasons(bot))
        self.assertIs(bot.kakera_react_available, False)
        wait = bot.kakera_react_cooldown_until_utc - datetime.datetime.now(datetime.timezone.utc)
        self.assertTrue(datetime.timedelta(hours=3, minutes=24) < wait <= datetime.timedelta(hours=3, minutes=26), wait)
        self.assertEqual(bot._kakera_rejection_revision if hasattr(bot, '_kakera_rejection_revision') else 0, 0)

    async def test_repeated_checks_do_not_ask_again(self):
        for _ in range(4):
            await self.check()
        self.assertEqual(self.command_channel.sent.count('$tu'), 1)

    async def test_a_real_refusal_still_zeroes_power(self):
        bot = self.bot
        bot.current_dk_power = 100
        await bot.events['on_message'](SimpleNamespace(
            id=9101, channel=self.channel, author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
            content="<@%s> You can't react to kakera for **40** min." % bot.user.id,
            created_at=datetime.datetime.now(datetime.timezone.utc), embeds=[], components=[], interaction=None,
        ))
        self.assertEqual(bot.current_dk_power, 0)
        self.assertIs(bot.kakera_react_available, False)


if __name__ == '__main__':
    unittest.main()
