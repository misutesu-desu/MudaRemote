import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.test_kakera_snipe_ownership import _create_test_client, _build_roll_message


class AutoRtSettingTests(unittest.IsolatedAsyncioTestCase):
    def _setup(self, **preset_options):
        self.bot, self.channel = _create_test_client(**preset_options)
        self.bot.claim_right_available = False
        self.bot.rt_available = True
        self.bot.min_kakera = 300
        self.message, _ = _build_roll_message(self.channel, 98201, 8002, "other")
        self.message.embeds[0].description = "Re:Zero\n**900**<:kakera:1>"
        claim_button = SimpleNamespace(
            emoji=SimpleNamespace(name="\U0001f496"), disabled=False, custom_id="claim")
        self.message.components = [SimpleNamespace(children=[claim_button])]
        self.channel.fetch_message = mock.AsyncMock(return_value=self.message)

    async def _snipe(self):
        try:
            return await asyncio.wait_for(self.bot._runtime_claim_character(
                self.bot, self.channel, self.message, is_snipe=True), 1)
        except asyncio.TimeoutError:
            return None

    def _sent_rt(self):
        return [text for text in self.channel.sent if "$rt" in str(text)]

    def test_presets_without_the_key_keep_automatic_rt(self):
        self._setup()
        self.assertTrue(self.bot.auto_rt_enabled)

    async def test_valuable_snipe_spends_rt_when_automatic_rt_is_on(self):
        self._setup(auto_rt_enabled=True)
        await self._snipe()
        self.assertNotEqual(self._sent_rt(), [])

    async def test_valuable_snipe_does_not_spend_rt_when_automatic_rt_is_off(self):
        self._setup(auto_rt_enabled=False)
        self.assertFalse(await self._snipe())
        self.assertEqual(self._sent_rt(), [])

    async def _own_roll(self, message_id):
        own_roll, _ = _build_roll_message(self.channel, message_id, 7001, "snipe-bot")
        own_roll.embeds[0].description = "Re:Zero\n**900**<:kakera:1>"
        own_roll.components = self.message.components
        self.channel.fetch_message = mock.AsyncMock(return_value=own_roll)
        try:
            await asyncio.wait_for(self.bot.events["on_message"](own_roll), 1)
        except asyncio.TimeoutError:
            pass  # A sent $rt waits for Mudae's acknowledgement.

    async def test_own_valuable_roll_does_not_spend_rt_when_automatic_rt_is_off(self):
        self._setup(auto_rt_enabled=False, enable_reactive_self_snipe_preset=True)
        await self._own_roll(98202)
        self.assertEqual(self._sent_rt(), [])

    async def test_own_valuable_roll_spends_rt_when_automatic_rt_is_on(self):
        self._setup(auto_rt_enabled=True, enable_reactive_self_snipe_preset=True)
        await self._own_roll(98203)
        self.assertNotEqual(self._sent_rt(), [])


if __name__ == "__main__":
    unittest.main()
