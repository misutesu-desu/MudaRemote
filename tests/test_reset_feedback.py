"""Shared minute-rounded timers must not erase a pending account reset."""
import asyncio
import datetime
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from mudae_core.status import mark_status_dirty
from tests.test_private_roll_sync_delay import _create_test_client, _attach_status_channel


class ResetFeedbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime.datetime(2026, 9, 16, 15, 40, tzinfo=datetime.timezone.utc)
        self.clock = mock.Mock(wraps=datetime.datetime)
        self.clock.now.return_value = self.now
        self.patchers = [
            mock.patch.object(mudae_bot.datetime, "datetime", self.clock),
            mock.patch.object(mudae_bot._tu_interval_coordinator, "reserve", return_value=0),
            mock.patch.object(mudae_bot, "pause_interruptible_sleep", mock.AsyncMock(return_value=True)),
            mock.patch.object(mudae_bot.BotLogger, "log"),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = _create_test_client(
            server_reset_minute=None, humanization_enabled=False,
            last_tu_snapshot_complete=False,
        )
        self.channel = _attach_status_channel(self.client)
        self.client.loop.close_created_tasks = False
        self.addCleanup(self.close_tasks)

    def close_tasks(self):
        for coroutine in self.client.loop.created_tasks:
            coroutine.close()

    async def run_action(self):
        handle = self.client._predicted_roll_action_handle
        if handle is not None:
            handle.fire()
            await self.client.loop.created_tasks.pop()

    def observe_peer_next_hour(self, boundary):
        mudae_bot._apply_shared_reset_snapshot(self.client, SimpleNamespace(
            observed_at_utc=self.clock.now.return_value,
            roll_reset_at_utc=boundary + datetime.timedelta(minutes=60),
            observed_fields=frozenset({"rolls"}),
        ))

    async def test_deferred_saved_roll_batch_resumes_despite_early_peer_timer(self):
        self.channel.snapshot = self.channel.snapshot.replace(
            "You have **1** rolls left.", "You have **0** rolls (+**20** $us) left.",
        ).replace("Next rolls reset in **60**", "Next rolls reset in **1**")
        await self.client._runtime_check_status(self.client, self.channel, "$")
        boundary = self.client.roll_reset_anchor.next_boundary_at_utc
        self.clock.now.return_value = boundary - datetime.timedelta(seconds=10)
        self.client._runtime_schedule_owned_normal_roll_action(
            self.client.current_roll_cycle_id, self.clock.now.return_value,
            status_refreshed=True,
        )
        self.assertEqual(self.client.normal_roll_action_owner.state, "deferred_window")
        self.observe_peer_next_hour(boundary)
        self.clock.now.return_value = boundary + datetime.timedelta(seconds=1)
        self.client._status_cycle_not_before_monotonic = 0
        self.channel.snapshot = self.channel.snapshot.replace(
            "Next rolls reset in **1**", "Next rolls reset in **60**",
        )
        await self.client._runtime_check_status(self.client, self.channel, "$")
        sync = self.client._roll_count_sync_handle
        if sync is not None:
            sync.fire()
            await self.client._runtime_check_status(self.client, self.channel, "$")
        await self.run_action()
        self.assertEqual(self.channel.sent.count("$wa"), 20)
        self.assertEqual(self.channel.sent.count("$tu"), 2)

    async def test_peer_timer_cannot_rearm_unacknowledged_rolls_in_same_interval(self):
        async def ack_timeout(_awaitable, timeout):
            raise asyncio.TimeoutError

        self.client.auto_rolls_enabled = True
        status = self.client._runtime_check_status
        wait_cell = status.__closure__[status.__code__.co_freevars.index("humanized_wait_and_proceed")]
        wait_cell.cell_contents = mock.AsyncMock()
        self.channel.snapshot = self.channel.snapshot.replace(
            "Next rolls reset in **60**", "Next rolls reset in **4**",
        )
        await status(self.client, self.channel, "$")
        boundary = self.client.roll_reset_anchor.next_boundary_at_utc
        with mock.patch.object(mudae_bot.asyncio, "wait_for", new=ack_timeout):
            await self.run_action()
        self.channel.snapshot = self.channel.snapshot.replace("**1** rolls left", "**0** rolls left")
        await status(self.client, self.channel, "$")
        await self.run_action()
        self.assertEqual(self.channel.sent.count("$rolls"), 1)
        self.assertEqual(self.client.normal_roll_action_owner.state, "completed")

        self.clock.now.return_value = boundary - datetime.timedelta(seconds=120)
        self.observe_peer_next_hour(boundary)
        self.channel.snapshot = self.channel.snapshot.replace(
            "Next rolls reset in **4**", "Next rolls reset in **2**",
        )
        self.client._rolls_ack_retry_after = 0
        mark_status_dirty(self.client, {"rolls"}, reason="status-boundary")
        await status(self.client, self.channel, "$")
        with mock.patch.object(mudae_bot.asyncio, "wait_for", new=ack_timeout):
            await self.run_action()
        self.assertEqual(self.channel.sent.count("$rolls"), 1)

        # A real boundary must still enable the next interval's item.
        self.clock.now.return_value = boundary + datetime.timedelta(seconds=1)
        self.client._status_cycle_not_before_monotonic = 0
        self.client._advance_predicted_reset_cycles(self.clock.now.return_value)
        evaluate = status.__closure__[status.__code__.co_freevars.index("pending_roll_work")].cell_contents
        self.assertTrue(evaluate()[0])


if __name__ == "__main__":
    unittest.main()
