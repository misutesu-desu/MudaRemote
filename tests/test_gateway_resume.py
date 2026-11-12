import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

import mudae_bot
from tests.test_snipe_startup import _Bot, _Channel


class GatewayResumeTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, rolling=True):
        bot = _Bot()
        mudae_bot._mobile_runtime_stop_event.clear()
        with mock.patch.object(mudae_bot.commands, "Bot", return_value=bot):
            mudae_bot.run_bot("resume-test", {
                "token": "dummy", "channel_id": 1234, "prefix": "!",
                "mudae_prefix": "$", "rolling": rolling, "snipe_mode": True,
            }, log_function=lambda *_args, **_kwargs: None)
        bot._main_channel = _Channel(1234, lambda: bot)
        return bot

    async def test_resume_restarts_a_finished_main_loop(self):
        bot = self.make_client()
        bot._has_initialized = True
        bot._main_loop_task = SimpleNamespace(done=lambda: True)
        await bot.events["on_resumed"]()
        names = [task.cr_code.co_name for task in bot.loop.created_tasks]
        self.assertEqual(names, ["main_status_loop"])

    async def test_resume_restarts_the_snipe_only_loop(self):
        bot = self.make_client(rolling=False)
        bot._has_initialized = True
        bot._main_loop_task = None
        await bot.events["on_resumed"]()
        names = [task.cr_code.co_name for task in bot.loop.created_tasks]
        self.assertEqual(names, ["snipe_only_status_loop"])

    async def test_resume_wakes_a_running_loop_and_lifts_the_wait(self):
        bot = self.make_client()
        bot._has_initialized = True
        bot._main_loop_task = SimpleNamespace(done=lambda: False)
        bot._immediate_check_event = asyncio.Event()
        bot._status_cycle_not_before_monotonic = 10 ** 9
        await bot.events["on_resumed"]()
        self.assertTrue(bot._immediate_check_event.is_set())
        self.assertEqual(bot._status_cycle_not_before_monotonic, 0.0)
        self.assertEqual(bot.loop.created_tasks, [])

    async def test_resume_before_startup_does_nothing(self):
        bot = self.make_client()
        bot._main_loop_task = None
        await bot.events["on_resumed"]()
        self.assertEqual(bot.loop.created_tasks, [])


if __name__ == "__main__":
    unittest.main()
