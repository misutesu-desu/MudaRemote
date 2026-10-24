import datetime
import unittest
from types import SimpleNamespace
from unittest import mock

import mudae_bot
from tests.test_kakera_snipe_ownership import _create_test_client, _build_roll_message


class UsedClaimSkipLogTests(unittest.IsolatedAsyncioTestCase):
    async def _roll_wish_without_claim(self, reset_in_seconds):
        bot, channel = _create_test_client(rolling_enabled=True)
        bot.is_actively_rolling = True
        bot.wishlist = ["rem"]
        bot.claim_right_available = False
        bot.rt_available = False
        bot.is_timing_mode_active = False
        bot.next_claim_reset_at_utc = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=reset_in_seconds)
        )
        message, _ = _build_roll_message(channel, 99101, bot.user.id, bot.user.name, client=bot)
        message.components = []
        logs = []
        with mock.patch.object(mudae_bot.BotLogger, "log", side_effect=lambda text, *a, **k: logs.append(str(text))), \
                mock.patch.object(mudae_bot, "pause_interruptible_sleep", mock.AsyncMock(return_value=True)):
            await bot.events["on_message"](message)
        return logs

    async def test_wishlist_roll_with_used_claim_is_logged(self):
        logs = await self._roll_wish_without_claim(1800)
        self.assertTrue(
            any("Not claiming rem: claim is already used, it comes back in 30m." in line for line in logs),
            logs,
        )

    async def test_near_reset_wait_does_not_log_the_skip(self):
        logs = await self._roll_wish_without_claim(5)
        self.assertFalse(any("Not claiming rem" in line for line in logs), logs)
        self.assertTrue(any("Waiting for reset" in line for line in logs), logs)


class UnlistedClaimEmojiLogTests(unittest.IsolatedAsyncioTestCase):
    async def _roll(self, heart):
        bot, channel = _create_test_client(rolling_enabled=True)
        bot.is_actively_rolling = True
        bot.wishlist = ["rem"]
        bot.claim_right_available = True
        bot.enable_reactive_self_snipe = True
        bot.claim_emojis = ["\U0001f496"]
        message, _ = _build_roll_message(channel, 99201, bot.user.id, bot.user.name, client=bot)
        claim_button = SimpleNamespace(emoji=SimpleNamespace(name=heart), disabled=False, custom_id="claim")
        claim_button.click = mock.AsyncMock()
        message.components = [SimpleNamespace(children=[claim_button])]
        channel.fetch_message = mock.AsyncMock(return_value=message)
        logs = []
        with mock.patch.object(mudae_bot.BotLogger, "log", side_effect=lambda text, *a, **k: logs.append(str(text))), \
                mock.patch.object(mudae_bot, "pause_interruptible_sleep", mock.AsyncMock(return_value=True)):
            await bot.events["on_message"](message)
        return logs

    async def test_wish_with_a_heart_outside_claim_emojis_is_logged(self):
        logs = await self._roll("\U0001f49e")
        self.assertTrue(
            any("Not claiming rem: its claim button \U0001f49e is not in your Claim Emojis." in line for line in logs),
            logs,
        )

    async def test_listed_heart_does_not_log_the_warning(self):
        logs = await self._roll("\U0001f496")
        self.assertFalse(any("is not in your Claim Emojis" in line for line in logs), logs)


class ClaimEmojiSpellingTests(unittest.TestCase):
    def _configured(self, claim_emojis):
        bot, _ = _create_test_client()
        mudae_bot.configure_client(
            bot, "spelling", {"claim_emojis": claim_emojis},
            bot_name="test", claim_emojis=mudae_bot.CLAIM_EMOJIS,
            kakera_emojis=mudae_bot.KAKERA_EMOJIS, sphere_emojis=mudae_bot.SPHERE_EMOJIS,
            slash_available=False, register_adaptive=False,
        )
        return bot.claim_emojis

    def test_typed_heart_names_match_the_button_characters(self):
        # Reported: names typed from Discord (blue_heart) never matched.
        emojis = self._configured(["blue_heart", ":black_heart:", "bride_with_veil", "woman_with_veil"])
        for heart in ("\U0001f499", "\U0001f5a4", "\U0001f470", "\U0001f470‍♀️"):
            self.assertIn(heart, emojis)

    def test_variation_selector_spelling_does_not_matter(self):
        self.assertIn("❤", self._configured(["❤️"]))
        self.assertIn("❤️", self._configured(["❤"]))

    def test_explicitly_empty_list_stays_empty(self):
        self.assertEqual(self._configured([]), [])


if __name__ == "__main__":
    unittest.main()
