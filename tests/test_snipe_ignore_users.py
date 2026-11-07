import unittest
from unittest import mock

from mudae_core.claiming import snipe_owner_allowed
from tests.test_edited_wish import closure
from tests.test_kakera_snipe_ownership import _create_test_client, _build_roll_message


class SnipeOwnerAllowedTests(unittest.TestCase):
    def test_empty_lists_allow_everyone(self):
        self.assertTrue(snipe_owner_allowed(5555, "someone", set(), set()))

    def test_ignored_id_or_name_is_refused(self):
        self.assertFalse(snipe_owner_allowed(5555, "someone", set(), {"5555"}))
        self.assertFalse(snipe_owner_allowed(5555, "SomeOne", set(), {"someone"}))

    def test_ignore_list_wins_over_target_list(self):
        self.assertFalse(snipe_owner_allowed(5555, "someone", {"5555"}, {"someone"}))

    def test_target_list_still_limits_who_is_sniped(self):
        self.assertTrue(snipe_owner_allowed(5555, "someone", {"5555"}, {"9999"}))
        self.assertFalse(snipe_owner_allowed(4444, "other", {"5555"}, {"9999"}))

    def test_unknown_owner_passes_an_ignore_list(self):
        self.assertTrue(snipe_owner_allowed(None, None, set(), {"9999"}))


class SnipeIgnoreUsersFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_kakera_on_ignored_players_roll_is_not_clicked(self):
        bot, channel = _create_test_client(
            kakera_reaction_snipe_mode_preset=True, snipe_ignore_users=["5555"])
        message, btn = _build_roll_message(channel, 99101, 5555, "ignored-player", client=bot)
        await bot.events["on_message"](message)
        self.assertFalse(btn.click.called)

    async def test_kakera_on_other_players_roll_is_still_clicked(self):
        bot, channel = _create_test_client(
            kakera_reaction_snipe_mode_preset=True, snipe_ignore_users=["5555"])
        message, btn = _build_roll_message(channel, 99102, 6666, "free-player", client=bot)
        await bot.events["on_message"](message)
        self.assertTrue(btn.click.called)

    async def _edited_wish(self, ignore):
        bot, channel = _create_test_client(snipe_ignore_users=ignore)
        bot.claim_right_available = True
        message, _ = _build_roll_message(channel, 99103, 8002, "other")
        message.content = "Wished by <@7001>"
        message.mentions = [bot.user]
        message.components = []
        channel.fetch_message = mock.AsyncMock(return_value=message)
        handler = closure(bot.events["on_message_edit"], "process_edited_wish")
        claim = mock.AsyncMock(return_value=True)
        cells = dict(zip(handler.__code__.co_freevars, handler.__closure__))
        cells["claim_character"].cell_contents = claim
        await handler(message)
        return claim

    async def test_wish_rolled_by_ignored_player_is_not_sniped(self):
        (await self._edited_wish(["8002"])).assert_not_awaited()
        (await self._edited_wish(["Other"])).assert_not_awaited()

    async def test_wish_rolled_by_other_player_is_still_sniped(self):
        (await self._edited_wish(["9999"])).assert_awaited_once()

    async def _wishlist_roll(self, ignore):
        bot, channel = _create_test_client(wishlist=["rem"], snipe_ignore_users=ignore)
        bot.claim_right_available = True
        message, _ = _build_roll_message(channel, 99104, 8002, "other")
        message.components = []
        claim = mock.AsyncMock(return_value=True)
        cells = dict(zip(bot.events["on_message"].__code__.co_freevars,
                         bot.events["on_message"].__closure__))
        cells["claim_character"].cell_contents = claim
        await bot.events["on_message"](message)
        return claim

    async def test_wishlist_roll_by_ignored_player_is_not_sniped(self):
        (await self._wishlist_roll(["8002"])).assert_not_awaited()

    async def test_wishlist_roll_by_other_player_is_still_sniped(self):
        (await self._wishlist_roll(["9999"])).assert_awaited()

    def test_preset_list_is_normalised(self):
        bot, _ = _create_test_client(snipe_ignore_users=[" Someone ", "5555", ""])
        self.assertEqual(bot.snipe_ignore_users, {"someone", "5555"})


if __name__ == "__main__":
    unittest.main()
