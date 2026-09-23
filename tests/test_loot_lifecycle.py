import datetime
import unittest
from types import SimpleNamespace
from unittest import mock

import mudae_bot
from tests.test_snipe_startup import _Bot, _Channel


class LootLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, mode="kl"):
        bot = _Bot()
        bot.process_commands = mock.AsyncMock()
        bot.run = mock.Mock()
        mudae_bot._mobile_runtime_stop_event.clear()
        with mock.patch.object(mudae_bot.commands, "Bot", return_value=bot):
            mudae_bot.run_bot("loot-test", {
                "token": "dummy", "channel_id": 1234, "prefix": "!",
                "mudae_prefix": "$", "loot_mode": mode,
                "rolling": True, "snipe_mode": True,
            })
        channel = _Channel(1234, lambda: bot)
        channel.guild.me = bot.user
        channel.permissions_for = lambda _member: SimpleNamespace(send_messages=True)
        bot._fetched_channels[1234] = channel
        return bot, channel

    async def test_start_and_reconnect_run_only_one_loot_task(self):
        bot, channel = self.make_client()
        with mock.patch.object(mudae_bot.discord, "TextChannel", _Channel), mock.patch.object(
            mudae_bot, "pause_interruptible_sleep", new=mock.AsyncMock(return_value=True)
        ):
            await bot.events["on_ready"]()
        self.assertEqual(channel.sent, [])
        names = [task.cr_code.co_name for task in bot.loop.created_tasks]
        self.assertEqual(names, ["health_monitor_task", "run"])
        bot._main_loop_task = SimpleNamespace(done=lambda: False)
        await bot.events["on_ready"]()
        self.assertEqual(len(bot.loop.created_tasks), 2)
        bot._main_loop_task = SimpleNamespace(done=lambda: True)
        await bot.events["on_ready"]()
        self.assertEqual(bot.loop.created_tasks[-1].cr_code.co_name, "run")

    async def test_loot_messages_and_edits_bypass_roll_and_snipe_handlers(self):
        bot, _channel = self.make_client()
        bot.loot_automation.on_message = mock.Mock()
        message = SimpleNamespace()
        await bot.events["on_message"](message)
        await bot.events["on_message_edit"](message, message)
        await bot.events["on_raw_message_edit"](message)
        await bot.events["on_raw_reaction_add"](message)
        self.assertEqual(bot.loot_automation.on_message.call_count, 2)
        bot.process_commands.assert_awaited_once_with(message)

    async def test_default_profiles_do_not_create_loot_runtime(self):
        bot, _channel = self.make_client("off")
        self.assertIsNone(bot.loot_automation)

    async def test_loot_send_obeys_inactive_hours(self):
        bot, channel = self.make_client()
        bot.inactive_hours = [("11:00", "13:00")]
        midday = datetime.datetime(2026, 9, 23, 12)
        with mock.patch.object(mudae_bot.datetime, "datetime") as clock:
            clock.now.return_value = midday
            self.assertFalse(await bot.loot_automation.send(channel, "$kl 1000"))
        self.assertEqual(channel.sent, [])


if __name__ == "__main__":
    unittest.main()
