import datetime
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from mudae_core.coordinator import GlobalIntervalCoordinator
from mudae_core.runtime import get_normal_roll_cycle_state
from mudae_core.status import clear_status_dirty, mark_status_dirty
from tests.test_roll_window_production import _build_runtime, _Channel


SNAPSHOT = (
    'You can claim now!\nNext claim reset in **60** min.\n'
    'You have **10** rolls left. Next rolls reset in **60** min.\n'
    '$rt is available!\nPower: **90%**\nEach kakera reaction consumes 100%\n'
    '2 $dk available\n$daily is on cooldown.\n$p is unavailable.\n7/20 buttons clicked.'
)


class ScheduledDkWakeTests(unittest.IsolatedAsyncioTestCase):
    """A scheduled $dk must go out at its minute even while rolls wait for their reset."""

    def waiting_bot(self, last_window=None):
        bot = _build_runtime()
        channel = _Channel(bot.target_channel_id)
        bot._main_channel = channel
        bot.rolling_enabled = True
        bot.auto_dk_enabled = True
        bot.dk_power_management = False
        bot.auto_p_enabled = False
        bot.dk_stock_count = 2
        bot.dk_schedule_time = '00:00'
        bot._last_scheduled_dk_window = last_window
        bot.current_roll_cycle_id = ('roll', 1, 1)
        bot.normal_roll_action_owner.state = 'pending'
        bot.normal_roll_action_owner.cycle_id = bot.current_roll_cycle_id
        # The rolls are counted and simply wait for their reset: the routine $tu is muted.
        state = get_normal_roll_cycle_state(bot, bot.current_roll_cycle_id)
        state.remaining = 0
        state.remaining_authoritative = True
        bot.last_tu_snapshot_complete = True
        bot.last_tu_query_utc = datetime.datetime.now(datetime.timezone.utc)
        bot._pre_roll_status_required = False
        bot.command_pacer.minimum_delay = bot.command_pacer.maximum_delay = 0
        clear_status_dirty(bot)
        mark_status_dirty(bot, {'dk'}, reason='dk-schedule', urgent=True)

        async def send(content, **kwargs):
            channel.sent.append(content)
            if content == '$tu':
                bot._tu_response_future.set_result(SNAPSHOT)
            return SimpleNamespace(id=len(channel.sent), created_at=datetime.datetime.now(datetime.timezone.utc))

        channel.send = send
        return bot, channel

    async def run_status(self, bot, channel):
        with mock.patch.object(mudae_bot, '_tu_interval_coordinator', GlobalIntervalCoordinator()), \
                mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)), \
                mock.patch.object(mudae_bot.BotLogger, 'log'):
            await bot._runtime_check_status(bot, channel, '$', proceed_to_rolls=False)

    async def test_due_schedule_sends_dk_while_a_roll_action_is_pending(self):
        # Reported: with two daily times the bot held the $dk past its minute and the
        # half-power reactions were missed, because the pending roll action muted the $tu.
        bot, channel = self.waiting_bot()
        await self.run_status(bot, channel)
        self.assertEqual(channel.sent[:2], ['$tu', '$dk'])
        self.assertIsNotNone(bot._last_scheduled_dk_window)

    async def test_used_schedule_window_keeps_the_routine_tu_muted(self):
        local_now = datetime.datetime.now().astimezone()
        used = mudae_bot.scheduled_dk_window_if_due('00:00', local_now)
        bot, channel = self.waiting_bot(last_window=used)
        await self.run_status(bot, channel)
        self.assertEqual(channel.sent, [])


if __name__ == '__main__':
    unittest.main()
