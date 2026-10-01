import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.test_kakera_snipe_ownership import _create_test_client, _build_roll_message


class RestoreWishlistSettingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot, self.channel = _create_test_client()
        self.bot.claim_right_available = False
        self.bot.rt_available = True
        self.bot.min_kakera = 5000
        self.bot.wishlist = ["rem"]
        self.message, _ = _build_roll_message(self.channel, 98101, 8002, "other")
        self.message.embeds[0].description = "Re:Zero\n**100**<:kakera:1>"
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

    async def test_snipe_of_cheap_wishlist_card_does_not_spend_rt_when_setting_is_off(self):
        self.bot.rt_ignore_min_kakera_for_wishlist = False
        await self._snipe()
        self.assertEqual(self._sent_rt(), [])

    async def test_snipe_of_valuable_card_may_still_spend_rt_when_setting_is_off(self):
        self.bot.rt_ignore_min_kakera_for_wishlist = False
        self.message.embeds[0].description = "Re:Zero\n**9000**<:kakera:1>"
        await self._snipe()
        self.assertNotEqual(self._sent_rt(), [])

    async def test_snipe_of_cheap_wishlist_card_spends_rt_when_setting_is_on(self):
        self.bot.rt_ignore_min_kakera_for_wishlist = True
        await self._snipe()
        self.assertNotEqual(self._sent_rt(), [])


if __name__ == "__main__":
    unittest.main()
