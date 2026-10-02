"""A status flag re-armed by every answer must not become a $tu every few seconds."""
import asyncio
import datetime
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from mudae_core import GlobalIntervalCoordinator, mark_status_dirty, record_tu_success
from mudae_core.status import TU_STORM_QUERIES
from mudae_core.bot_runtime import _redact_credentials
from tests.test_roll_window_production import _build_runtime, _Channel

SNAPSHOT = (
    "karapisicik, you can claim right now! The next claim reset is in **2h 01** min.\n"
    "You have **0** rolls left. Next rolls reset in **40** min.\n"
    "Power: **31%**\nStock: **234**\nNext $dk in 9h 10 min.\n"
)


class TuSpacingTests(unittest.IsolatedAsyncioTestCase):
    def _runtime(self):
        bot = _build_runtime()
        channel = _Channel()
        bot._main_channel = channel
        bot.command_pacer.minimum_delay = bot.command_pacer.maximum_delay = 0

        async def send(content, **kwargs):
            channel.sent.append(content)
            if content == '$tu':
                bot._tu_response_future.set_result(SNAPSHOT)
            return SimpleNamespace(id=len(channel.sent))

        channel.send = send
        return bot, channel

    async def _check(self, bot, channel):
        with mock.patch.object(mudae_bot, '_tu_interval_coordinator', GlobalIntervalCoordinator()), \
                mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)):
            await asyncio.wait_for(bot._runtime_check_status(bot, channel, '$', proceed_to_rolls=False), 10)

    async def test_runaway_status_wakes_are_capped_per_minute(self):
        bot, channel = self._runtime()
        for _ in range(12):
            mark_status_dirty(bot, {'points'}, reason='test-wake')
            await self._check(bot, channel)
        self.assertEqual(channel.sent.count('$tu'), TU_STORM_QUERIES)

    async def test_urgent_evidence_cannot_break_through_a_runaway(self):
        bot, channel = self._runtime()
        for _ in range(12):
            mark_status_dirty(bot, {'claim'}, reason='test-urgent', urgent=True)
            await self._check(bot, channel)
        self.assertEqual(channel.sent.count('$tu'), TU_STORM_QUERIES)

    async def test_queries_resume_after_the_window(self):
        bot, channel = self._runtime()
        for _ in range(6):
            mark_status_dirty(bot, {'points'}, reason='test-wake')
            await self._check(bot, channel)
        bot._tu_next_allowed_monotonic = 0.0
        bot._tu_storm_until_monotonic = 0.0
        bot._tu_recent_successes = []
        mark_status_dirty(bot, {'points'}, reason='test-wake')
        await self._check(bot, channel)
        self.assertEqual(channel.sent.count('$tu'), TU_STORM_QUERIES + 1)

    async def test_normal_pace_is_untouched(self):
        bot, channel = self._runtime()
        now = 1000.0
        for _ in range(10):
            record_tu_success(bot, now_monotonic=now)
            now += 30.0
        self.assertEqual(bot._tu_next_allowed_monotonic, 0.0)
        self.assertEqual(bot._tu_storm_until_monotonic, 0.0)

    def test_event_log_keeps_sentences_but_still_hides_tokens(self):
        sentence = "Checking $tu... (reason: status-boundary) after the Mudae reset. Next."
        self.assertEqual(_redact_credentials(sentence), sentence)
        # Built from parts so secret scanners do not mistake this fixture for a real token.
        token = ".".join(("MTIzNDU2Nzg5MDEyMzQ1Njc4", "GabcDE", "abcdefghijklmnopqrstuvwxyz0123456789"))
        self.assertEqual(_redact_credentials(token), "[REDACTED_TOKEN]")


if __name__ == '__main__':
    unittest.main()
