import unittest
from unittest import mock

import mudae_bot
from tests.test_private_roll_sync_delay import _attach_status_channel, _create_test_client


class LurkerOwnedRollActionTests(unittest.IsolatedAsyncioTestCase):
    """A roll batch woken by its own timer must still obey the Lurker Strategy."""

    async def _fire_owned_roll_with_lurker(self, claim_reset_minutes, panic_roll_minutes=5):
        client = _create_test_client(
            server_reset_minute=None, last_tu_snapshot_complete=False,
            humanization_enabled=False,
        )
        channel = _attach_status_channel(client)
        channel.snapshot = channel.snapshot.replace(
            "Next claim reset in **60** min.",
            f"Next claim reset in **{claim_reset_minutes}** min.",
        )
        client.panic_roll_minutes = panic_roll_minutes
        with mock.patch.object(mudae_bot._tu_interval_coordinator, "reserve", return_value=0), \
                mock.patch.object(mudae_bot, "pause_interruptible_sleep", new=mock.AsyncMock(return_value=True)):
            # The batch was scheduled in an earlier round, before lurking applied.
            await client._runtime_check_status(client, channel, "$")
            handle = client._predicted_roll_action_handle
            client.lurker_mode = True
            client.lurker_final_round_only = True
            client.loop.close_created_tasks = False
            handle.fire()
            await client.loop.created_tasks.pop()
        return client, channel

    async def test_last_round_holds_owned_rolls_until_the_panic_window(self):
        client, channel = await self._fire_owned_roll_with_lurker(60)
        self.assertNotIn("$wa", channel.sent)
        self.assertTrue(client.normal_roll_action_owner.is_pending(client.current_roll_cycle_id))
        retry = client._predicted_roll_action_handle
        self.assertIsNotNone(retry)
        self.assertGreater(retry.delay, 50 * 60)
        self.assertLessEqual(retry.delay, 56 * 60)

    async def test_panic_window_releases_owned_rolls(self):
        client, channel = await self._fire_owned_roll_with_lurker(4)
        self.assertIn("$wa", channel.sent)
        self.assertEqual(client.current_min_kakera_for_roll_claim, 0)

    async def test_too_short_panic_window_opens_early_enough_for_the_dump(self):
        # Reported: a 1 minute panic window started the dump after the last
        # safe start, so the rolls were deferred past the reset and lost.
        client, channel = await self._fire_owned_roll_with_lurker(3, panic_roll_minutes=1)
        self.assertIn("$wa", channel.sent)
        self.assertEqual(client.current_min_kakera_for_roll_claim, 0)


if __name__ == "__main__":
    unittest.main()
