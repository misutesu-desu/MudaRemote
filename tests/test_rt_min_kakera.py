import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from mudae_core.bot_config import configure_client
from tests.test_kakera_snipe_ownership import _create_test_client, _build_roll_message


class RestoreMinimumValueTests(unittest.IsolatedAsyncioTestCase):
    """Minimum Value for $rt: a separate floor for spending $rt (issue #103)."""

    def setUp(self):
        self.bot, self.channel = _create_test_client()
        self.bot.claim_right_available = False
        self.bot.rt_available = True
        self.bot.min_kakera = 100
        self.bot.wishlist = []
        self.bot.rt_ignore_min_kakera_for_wishlist = False
        self.message, _ = _build_roll_message(self.channel, 98201, 8102, "other")
        claim_button = SimpleNamespace(
            emoji=SimpleNamespace(name="\U0001f496"), disabled=False, custom_id="claim")
        self.message.components = [SimpleNamespace(children=[claim_button])]
        self.channel.fetch_message = mock.AsyncMock(return_value=self.message)

    async def snipe_worth(self, value):
        self.message.embeds[0].description = "Re:Zero\n**%d**<:kakera:1>" % value
        try:
            await asyncio.wait_for(self.bot._runtime_claim_character(
                self.bot, self.channel, self.message, is_snipe=True), 1)
        except asyncio.TimeoutError:
            pass
        return [text for text in self.channel.sent if "$rt" in str(text)]

    async def test_zero_keeps_the_claim_minimum(self):
        self.bot.rt_min_kakera = 0
        self.assertNotEqual(await self.snipe_worth(150), [])

    async def test_a_card_under_the_rt_minimum_does_not_spend_rt(self):
        self.bot.rt_min_kakera = 200
        self.assertEqual(await self.snipe_worth(150), [])

    async def test_a_card_over_the_rt_minimum_spends_rt(self):
        self.bot.rt_min_kakera = 200
        self.assertNotEqual(await self.snipe_worth(250), [])

    def test_preset_value_is_read_and_defaults_to_zero(self):
        for preset, expected in (({}, 0), ({"rt_min_kakera": 200}, 200), ({"rt_min_kakera": -5}, 0)):
            with self.subTest(preset=preset):
                client = SimpleNamespace(hourly_tu_refresh=False)
                configure_client(client, "test", dict(preset, channel_id=1), bot_name="MudaRemote",
                                 claim_emojis=[], kakera_emojis=[], sphere_emojis=[], slash_available=True)
                self.assertEqual(client.rt_min_kakera, expected)


if __name__ == "__main__":
    unittest.main()
