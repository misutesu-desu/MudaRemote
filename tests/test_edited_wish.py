import asyncio
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from tests.test_kakera_snipe_ownership import _create_test_client, _build_roll_message


def closure(function, name):
    return dict(zip(function.__code__.co_freevars, function.__closure__))[name].cell_contents


class EditedWishTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot, self.channel = _create_test_client()
        self.bot.claim_right_available = True
        self.message, _ = _build_roll_message(self.channel, 98001, 8002, "other")
        self.message.content = "Wished by <@7001>"
        self.message.mentions = [self.bot.user]
        self.message.components = []
        self.channel.fetch_message = mock.AsyncMock(return_value=self.message)
        self.handler = closure(self.bot.events["on_message_edit"], "process_edited_wish")
        self.claim = mock.AsyncMock(return_value=True)
        cells = dict(zip(self.handler.__code__.co_freevars, self.handler.__closure__))
        cells["claim_character"].cell_contents = self.claim

    async def test_cached_edit_detects_wish_without_counting_another_roll(self):
        self.bot._rolls_received = 4
        await self.bot.events["on_message_edit"](self.message, self.message)
        self.claim.assert_awaited_once()
        self.assertEqual(self.bot._rolls_received, 4)
        self.assertTrue(self.bot.snipe_happened)

    async def test_uncached_edit_fetches_full_message(self):
        await self.bot.events["on_raw_message_edit"](SimpleNamespace(
            message_id=self.message.id, channel_id=self.channel.id,
            data={"content": self.message.content}, cached_message=None))
        self.channel.fetch_message.assert_awaited_once_with(self.message.id)
        self.claim.assert_awaited_once()

    async def test_raw_cached_edit_is_not_processed_twice(self):
        await self.bot.events["on_raw_message_edit"](SimpleNamespace(
            message_id=self.message.id, channel_id=self.channel.id,
            data={"content": self.message.content}, cached_message=self.message))
        self.channel.fetch_message.assert_not_awaited()
        self.claim.assert_not_awaited()

    async def test_simultaneous_edits_attempt_only_one_claim(self):
        await asyncio.gather(self.handler(self.message), self.handler(self.message))
        self.claim.assert_awaited_once()

    async def test_edit_respects_filters_and_pause(self):
        for attribute, value in (("avoid_list", ["rem"]), ("character_snipe_targets", ["999"]),
                                 ("is_paused", True), ("snipe_mode", False)):
            original = getattr(self.bot, attribute)
            setattr(self.bot, attribute, value)
            await self.handler(self.message)
            setattr(self.bot, attribute, original)
        self.message.mentions = []
        await self.handler(self.message)
        self.claim.assert_not_awaited()

    async def test_pending_manual_restore_defers_even_when_auto_restore_is_restricted(self):
        self.bot.claim_right_available = False
        self.bot.rt_available = False
        self.bot.rt_only_self_rolls = True
        self.bot._rt_command_in_flight = {"source": "manual", "message_id": 123}
        result = await self.bot._runtime_claim_character(
            self.bot, self.channel, self.message, is_snipe=True)
        self.assertFalse(result)
        self.assertEqual(len(self.bot._manual_rt_pending_claims), 1)
        self.assertEqual(self.bot._manual_rt_pending_claims[0]["message_id"], self.message.id)
        self.assertEqual(self.channel.sent, [])

        await self.bot.events["on_raw_reaction_add"](SimpleNamespace(
            message_id=123, user_id=mudae_bot.TARGET_BOT_ID, emoji=SimpleNamespace(name="✅")))
        apply_ack = closure(self.bot.events["on_raw_reaction_add"], "apply_rt_acknowledgement")
        # The fixture records scheduled tasks; run the scheduled retry explicitly.
        await closure(apply_ack, "retry_manual_rt_pending_claims")()
        self.claim.assert_awaited_once()
        self.assertFalse(self.claim.call_args.kwargs["allow_rt"])
        self.assertEqual(self.bot._manual_rt_pending_claims, [])

    async def test_other_users_reaction_cannot_restore_claim(self):
        self.bot.claim_right_available = False
        self.bot._rt_command_in_flight = {"source": "manual", "message_id": 123}
        await self.bot.events["on_raw_reaction_add"](SimpleNamespace(
            message_id=123, user_id=8002, emoji=SimpleNamespace(name="✅")))
        self.assertFalse(self.bot.claim_right_available)
        self.assertIsNotNone(self.bot._rt_command_in_flight)

    async def test_ack_before_manual_command_is_reconciled(self):
        observer = closure(self.bot.events["on_message"], "observe_manual_rt_command")
        self.bot.claim_right_available = False
        self.bot.rt_available = True
        await self.bot.events["on_raw_reaction_add"](SimpleNamespace(
            message_id=123, user_id=mudae_bot.TARGET_BOT_ID, emoji=SimpleNamespace(name="✅")))
        observer(SimpleNamespace(id=123, author=self.bot.user, content="$rt"))
        self.assertTrue(self.bot.claim_right_available)
        self.assertFalse(self.bot.rt_available)
        self.assertIsNone(self.bot._rt_command_in_flight)


if __name__ == "__main__":
    unittest.main()
