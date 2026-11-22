import asyncio
import datetime
import unittest
from types import SimpleNamespace
from unittest import mock

import mudae_bot
from mudae_core.coordinator import GlobalIntervalCoordinator
from mudae_core.status import clear_status_dirty
from tests.test_kakera_feedback_recovery import _Channel, _create_test_client


SNAPSHOT = (
    "You can't claim for another **58** min.\n"
    "You have **21** rolls (+**2** $mk) left. Next rolls reset in **48** min.\n"
    "Next $rt in **12h 0** min.\n"
    "Power: **40%**\n"
    "Each kakera reaction consumes 40%\nNext $dk in **40** min.\n"
    "0 $oh, 0 $oc, 0 $oq, 0 $ot. 649 min before the refill."
)


class MkAfterInterruptedBatchTests(unittest.IsolatedAsyncioTestCase):
    """Reported: after a rejected claim cut a roll batch short, $tu went out every 5 s."""

    async def asyncSetUp(self):
        self.logs = []
        self.waiting = asyncio.Event()

        def log(message, _preset="MudaRemote", level="INFO", _client=None, **_kwargs):
            if level != "DEBUG":
                self.logs.append(message)
                if message.startswith("Waiting "):
                    self.waiting.set()

        patches = [
            mock.patch.object(mudae_bot.BotLogger, "log", side_effect=log),
            mock.patch.object(mudae_bot, "_tu_interval_coordinator", GlobalIntervalCoordinator()),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.bot, self.channel = _create_test_client(
            rolling_enabled=True, auto_mk_enabled=True, auto_us_enabled=False,
            auto_rolls_enabled=False, auto_dk_enabled=False, auto_p_enabled=False,
            humanization_enabled=False,
        )
        bot = self.bot
        clear_status_dirty(bot)
        bot.process_commands = mock.AsyncMock()
        bot._immediate_check_event = asyncio.Event()
        bot.claim_right_available = False
        bot.rt_available = False
        bot.current_dk_power = 40
        bot.dk_consumption = 40
        bot.mk_rolls_left = 2
        # The claim interrupt outlives the batch it stopped.
        bot.interrupt_rolling = True
        self.command_channel = _Channel(5678, lambda: bot)
        bot._fetched_channels[5678] = self.command_channel

        async def status_send(content, **_kwargs):
            self.command_channel.sent.append(content)
            bot._tu_response_future.set_result(SNAPSHOT)
            return SimpleNamespace(id=8500 + len(self.command_channel.sent),
                                   created_at=datetime.datetime.now(datetime.timezone.utc))

        self.command_channel.send = status_send

    def test_mk_is_not_pending_while_the_interrupt_is_set(self):
        self.assertFalse(self.bot._pending_roll_work()[2])
        self.bot.interrupt_rolling = False
        self.assertTrue(self.bot._pending_roll_work()[2])

    async def test_status_check_waits_for_the_next_deadline_instead_of_returning(self):
        task = asyncio.create_task(self.bot._runtime_check_status(self.bot, self.channel, "$"))
        try:
            await asyncio.wait_for(self.waiting.wait(), timeout=4)
            self.assertEqual(self.command_channel.sent, ["$tu"])
            self.assertFalse(task.done(), "check_status returned and the loop would send $tu again")
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    unittest.main()
