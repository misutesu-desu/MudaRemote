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


if __name__ == "__main__":
    unittest.main()
