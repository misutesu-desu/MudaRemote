import datetime
import unittest
from unittest import mock

from tests.test_kakera_snipe_ownership import _create_test_client


class AutoRtAfterClaimTests(unittest.IsolatedAsyncioTestCase):
    async def finalize(self, interval, remaining, **settings):
        bot, channel = _create_test_client()
        bot.claim_interval = interval
        bot.next_claim_reset_at_utc = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=remaining)
        bot.auto_rt_after_claim = True
        bot.rt_available = True
        for name, value in settings.items():
            setattr(bot, name, value)
        verify = bot._runtime_verify_snipe_outcome
        cells = dict(zip(verify.__code__.co_freevars, verify.__closure__))
        finalize = cells['finalize_successful_claim'].cell_contents
        cells = dict(zip(finalize.__code__.co_freevars, finalize.__closure__))
        send = mock.AsyncMock(return_value=True)
        cells['send_rt_command'].cell_contents = send
        pending = dict(message_id=99001, character_name='Saber', character_kakera=1000,
                       character_series='Fate', consumes_claim=True, is_snipe_action=True)
        await finalize(pending, channel, 'character-owner')
        await finalize(pending, channel, 'character-owner')
        return send

    async def test_hourly_cycle_uses_rt_with_forty_minutes_remaining_once(self):
        send = await self.finalize(60, 40)
        send.assert_awaited_once()

    async def test_short_cycles_scale_saving_window(self):
        for interval, remaining, expected in ((60, 21, True), (60, 19, False),
                                               (30, 15, True), (30, 9, False),
                                               (120, 45, True), (120, 39, False)):
            with self.subTest(interval=interval, remaining=remaining):
                send = await self.finalize(interval, remaining)
                self.assertEqual(send.await_count, int(expected))

    async def test_default_and_long_cycles_keep_hour_saving_window(self):
        for interval in (180, 240):
            for remaining, expected in ((61, True), (59, False)):
                with self.subTest(interval=interval, remaining=remaining):
                    send = await self.finalize(interval, remaining)
                    self.assertEqual(send.await_count, int(expected))

    async def test_existing_post_claim_guards(self):
        for settings in (dict(is_paused=True), dict(rt_available=False),
                         dict(auto_rt_after_claim=False),
                         dict(rolling_enabled=True, is_actively_rolling=False)):
            with self.subTest(settings=settings):
                send = await self.finalize(60, 40, **settings)
                send.assert_not_awaited()

    async def test_active_rolling_can_restore_claim(self):
        send = await self.finalize(60, 40, rolling_enabled=True, is_actively_rolling=True)
        send.assert_awaited_once()
