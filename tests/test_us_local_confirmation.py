"""Mudae answers `$us N` with a ✅ when it used exactly N stacked rolls, or with a text
("You don't have any/enough rolls stacked!") when it used none. A ✅ therefore settles the
count, and the confirmation $tu is only needed when no ✅ arrives."""
import unittest
from types import SimpleNamespace
from unittest import mock

from mudae_core.status import clear_status_dirty, status_dirty_fields, status_refresh_reasons
from tests.test_kakera_snipe_ownership import _create_test_client


def _closure(function):
    return dict(zip(function.__code__.co_freevars, function.__closure__))


def _send_auto_us(bot, acks):
    """Return (send_auto_us, sent_commands) with Discord and the ✅ wait replaced."""
    check_rolls = _closure(bot._runtime_check_status)['check_rolls_left_tu'].cell_contents
    cells = _closure(check_rolls)['send_auto_us'].cell_contents
    inner = _closure(cells)
    sent = []

    async def send(_channel, content):
        sent.append(content)
        return SimpleNamespace(id=1000 + len(sent))

    answers = iter(acks)
    inner['guarded_send'].cell_contents = send
    inner['await_mudae_command_ack'].cell_contents = mock.AsyncMock(side_effect=lambda *a, **k: next(answers))
    inner['active_delay'].cell_contents = mock.AsyncMock(return_value=True)
    return cells, sent


class UsLocalConfirmationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot, self.channel = _create_test_client()
        clear_status_dirty(self.bot)
        self.bot.rolling_enabled = True
        self.bot.rolls_left = 0
        self.bot.us_pulled_this_cycle = 0
        self.bot._local_extra_rolls_pending = 0

    async def test_acknowledged_us_is_counted_locally_without_a_tu(self):
        send_auto_us, sent = _send_auto_us(self.bot, [True])
        self.assertTrue(await send_auto_us(10, self.channel))
        bot = self.bot
        self.assertEqual(sent, [bot.mudae_prefix + 'us 10'])
        self.assertEqual((bot.rolls_left, bot._local_extra_rolls_pending, bot.us_pulled_this_cycle), (10, 10, 10))
        self.assertFalse(bot._us_in_flight)
        self.assertEqual(status_dirty_fields(bot), set(), status_refresh_reasons(bot))

    async def test_unacknowledged_us_still_asks_tu(self):
        send_auto_us, _ = _send_auto_us(self.bot, [False])
        self.assertTrue(await send_auto_us(10, self.channel))
        bot = self.bot
        self.assertEqual((bot.rolls_left, bot._local_extra_rolls_pending, bot.us_pulled_this_cycle), (0, 0, 0))
        self.assertTrue(bot._us_in_flight)
        self.assertEqual(bot._us_pending_amount, 10)
        self.assertIn('rolls', status_dirty_fields(bot))
        self.assertIn('auto-us-sent', status_refresh_reasons(bot))

    async def test_bulk_us_is_local_only_when_every_chunk_is_acknowledged(self):
        self.bot.bulk_us_enabled = True
        send_auto_us, sent = _send_auto_us(self.bot, [True, True, True])
        self.assertTrue(await send_auto_us(45, self.channel))
        self.assertEqual([c.rsplit(' ', 1)[1] for c in sent], ['20', '20', '5'])
        self.assertEqual((self.bot.rolls_left, self.bot.us_pulled_this_cycle), (45, 45))
        self.assertFalse(self.bot._us_in_flight)

    async def test_one_missing_acknowledgement_falls_back_to_the_tu_for_the_whole_request(self):
        self.bot.bulk_us_enabled = True
        send_auto_us, _ = _send_auto_us(self.bot, [True, False, True])
        self.assertTrue(await send_auto_us(45, self.channel))
        bot = self.bot
        self.assertEqual((bot.rolls_left, bot._local_extra_rolls_pending, bot.us_pulled_this_cycle), (0, 0, 0))
        self.assertTrue(bot._us_in_flight)
        self.assertEqual(bot._us_pending_amount, 45)
        self.assertIn('auto-us-sent', status_refresh_reasons(bot))


if __name__ == '__main__':
    unittest.main()


class UsLocalRollingTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmed_us_rolls_start_without_a_tu(self):
        import asyncio
        import mudae_bot
        from tests.test_roll_window_production import _build_runtime, _Channel

        bot = _build_runtime()
        channel = _Channel()
        bot._main_channel = channel
        bot.command_pacer.minimum_delay = bot.command_pacer.maximum_delay = 0
        bot.rolling_enabled = True
        bot.roll_speed = 0
        bot.rolls_left = 3
        bot._local_extra_rolls_pending = 3
        clear_status_dirty(bot)
        with mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)):
            await asyncio.wait_for(bot._runtime_check_status(bot, channel, '$', proceed_to_rolls=True), 20)
        self.assertNotIn('$tu', channel.sent)
        self.assertEqual(sum(1 for c in channel.sent if c.startswith('$wa')), 3, channel.sent)
        self.assertEqual(bot._local_extra_rolls_pending, 0)
