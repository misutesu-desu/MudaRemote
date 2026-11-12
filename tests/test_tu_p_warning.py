import unittest
from types import SimpleNamespace
from unittest import mock

import mudae_bot
from mudae_core.coordinator import GlobalIntervalCoordinator
from mudae_core.status import clear_status_dirty
from tests.test_kakera_snipe_ownership import _Channel, _create_test_client


class MissingPointsLineWarningTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        async def sleep(_client, _seconds, *args, **kwargs):
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
        self.command_channel = _Channel(5678, lambda: self.bot)
        self.bot._fetched_channels[5678] = self.command_channel

    async def status(self, auto_p, p_line):
        bot = self.bot
        bot.auto_p_enabled = auto_p
        snapshot = (
            'You can claim now!\nNext claim reset in **60** min.\n'
            'You have **10** rolls left. Next rolls reset in **60** min.\n'
            '$rt is available!\nPower: **90%**\n'
            'Each kakera reaction consumes 40%\n1 $dk available\n'
            '$daily is on cooldown.\n'
            + ('Next $p reset in **1h 20** min.\n' if p_line else '')
            + 'You can react'
        )

        async def send(content, **kwargs):
            self.command_channel.sent.append(content)
            if content == '$tu':
                bot._tu_response_future.set_result(snapshot)
            return SimpleNamespace(id=len(self.command_channel.sent))

        self.command_channel.send = send
        bot.last_tu_snapshot_complete = False
        bot.last_tu_query_utc = None
        bot._tu_next_allowed_monotonic = 0
        await bot._runtime_check_status(bot, self.channel, '$', proceed_to_rolls=False)

    def p_warnings(self):
        return [call.args[0] for call in mudae_bot.BotLogger.log.call_args_list
                if call.args and 'no $p line' in call.args[0]]

    async def test_auto_p_without_the_p_line_warns_once(self):
        await self.status(auto_p=True, p_line=False)
        await self.status(auto_p=True, p_line=False)
        warnings = self.p_warnings()
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn('$tuarrange', warnings[0])
        self.assertNotIn('$p', self.command_channel.sent)

    async def test_no_warning_when_the_p_line_is_there(self):
        await self.status(auto_p=True, p_line=True)
        self.assertEqual(self.p_warnings(), [])

    async def test_no_warning_when_auto_p_is_off(self):
        await self.status(auto_p=False, p_line=False)
        self.assertEqual(self.p_warnings(), [])

    async def test_warns_again_after_the_line_came_back_and_went_missing(self):
        await self.status(auto_p=True, p_line=False)
        await self.status(auto_p=True, p_line=True)
        await self.status(auto_p=True, p_line=False)
        self.assertEqual(len(self.p_warnings()), 2)


if __name__ == '__main__':
    unittest.main()
