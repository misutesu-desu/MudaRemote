import datetime
import unittest
from unittest import mock

import mudae_bot
from tests.test_private_roll_sync_delay import _attach_status_channel, _create_test_client


class LurkerPanicTimingTests(unittest.IsolatedAsyncioTestCase):
    async def _check_status(self, minutes_to_claim_reset):
        client = _create_test_client(
            server_reset_minute=None,
            last_tu_snapshot_complete=False,
            humanization_window_minutes=40,
        )
        channel = _attach_status_channel(client)
        client.tu_query_count = 1
        client.humanization_enabled = True
        client.lurker_mode = True
        client.claim_right_available = True
        client.panic_roll_minutes = 2
        client.rolls_left = 10
        client.roll_speed = 0.4
        client.delay_seconds = 0
        client.next_claim_reset_at_utc = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(minutes=minutes_to_claim_reset)
        )
        send = channel.send

        async def stop_after_status(content, *args, **kwargs):
            # Only the $tu decision matters; the scheduler waits after it.
            result = await send(content, *args, **kwargs)
            client._runtime_stopping = True
            return result

        channel.send = stop_after_status
        with mock.patch.object(mudae_bot.random, "uniform", side_effect=lambda low, high: high), \
                mock.patch.object(mudae_bot._tu_interval_coordinator, "reserve", return_value=0):
            await client._runtime_check_status(client, channel, "$")
        return channel

    async def test_panic_status_check_skips_the_random_wait(self):
        # Reported: the random wait pushed the $tu to the last second, so the
        # panic rolls found no safe window and were deferred past the reset.
        channel = await self._check_status(3)
        self.assertEqual(channel.sent[:1], ["$tu"])

    async def test_random_wait_still_applies_outside_the_panic_window(self):
        channel = await self._check_status(45)
        self.assertEqual(channel.sent, [])


if __name__ == "__main__":
    unittest.main()
