"""User reports replayed through the real status, roll and loot paths."""
import datetime
import unittest
from types import SimpleNamespace
from unittest import mock

import mudae_bot
from mudae_core.sphere_runtime import SphereRuntime
from mudae_core.status import clear_status_dirty
from tests.test_kakera_snipe_ownership import _create_test_client as _create_snipe_client
from tests.test_private_roll_sync_delay import _attach_status_channel, _create_test_client
from tests.test_us_local_confirmation import _closure, _send_auto_us


class PanicWindowReplay(unittest.IsolatedAsyncioTestCase):
    async def test_ten_panic_rolls_are_sent_before_the_reset(self):
        # Panic set to two minutes, 10 rolls, Timing Variation with a 40 minute
        # window: the rolls used to be deferred past the reset.
        client = _create_test_client(
            server_reset_minute=None, last_tu_snapshot_complete=False,
            humanization_window_minutes=40, trusted_capacity=10, trusted_confidence=True,
        )
        channel = _attach_status_channel(client)
        channel.snapshot = (
            "You can claim now!\nNext claim reset in **3** min.\n"
            "You have **10** rolls left. Next rolls reset in **3** min.\n"
            "$rt is available!\nPower: **100%**\n0 $dk available\n"
            "$daily is on cooldown.\n$p is unavailable."
        )
        client.tu_query_count = 1
        client.humanization_enabled = True
        client.humanization_inactivity_seconds = 0
        client.lurker_mode = True
        client.claim_right_available = True
        client.panic_roll_minutes = 2
        client.rolls_left = 10
        client.roll_speed = 0.4
        client.delay_seconds = 0
        now = datetime.datetime.now(datetime.timezone.utc)
        client.next_claim_reset_at_utc = now + datetime.timedelta(minutes=3)
        client.roll_reset_at_utc = now + datetime.timedelta(minutes=3)
        client.loop.close_created_tasks = False
        with mock.patch.object(mudae_bot.random, "uniform", side_effect=lambda low, high: high), \
                mock.patch.object(mudae_bot._tu_interval_coordinator, "reserve", return_value=0), \
                mock.patch.object(mudae_bot, "pause_interruptible_sleep", new=mock.AsyncMock(return_value=True)):
            await client._runtime_check_status(client, channel, "$")
            self.assertEqual(channel.sent[:1], ["$tu"])
            client._predicted_roll_action_handle.fire()
            await client.loop.created_tasks.pop()
        self.assertEqual(channel.sent.count("$wa"), 10)


class SavedRollReplay(unittest.IsolatedAsyncioTestCase):
    async def _pull(self, minutes_to_reset):
        bot, channel = _create_snipe_client()
        clear_status_dirty(bot)
        bot.rolling_enabled = True
        bot.rolls_left = 0
        bot.roll_speed = 5.0
        bot.auto_us_enabled = True
        bot.auto_us_limit = 100
        bot.auto_us_stop_on_claim = False
        bot.bulk_us_enabled = False
        bot.us_pulled_this_cycle = 0
        bot._us_in_flight = False
        bot._us_retry_after = 0.0
        bot.auto_rolls_enabled = False
        _, sent = _send_auto_us(bot, [True])
        check_rolls = _closure(bot._runtime_check_status)['check_rolls_left_tu'].cell_contents
        _closure(check_rolls)['humanized_wait_and_proceed'].cell_contents = mock.AsyncMock()
        tu = (f"You have **0** rolls left. Next rolls reset in **{minutes_to_reset}** min.\n"
              "Next claim reset in **30** min.")
        # Mudae's whole minutes snap to the clock, so the result needs a fixed second.
        now = datetime.datetime.now(datetime.timezone.utc).replace(second=0, microsecond=0)
        with mock.patch.object(mudae_bot.datetime, "datetime", wraps=datetime.datetime) as clock:
            clock.now.return_value = now
            await check_rolls(bot, channel, "$", None, "test", tu, False, False, bot.current_roll_cycle_id)
        return sent

    async def test_full_pull_with_time_to_finish(self):
        self.assertEqual(await self._pull(30), ["$us 20"])

    async def test_last_minute_pull_only_takes_what_it_can_finish(self):
        self.assertEqual(await self._pull(1), ["$us 9"])


class SphereStockReplay(unittest.IsolatedAsyncioTestCase):
    async def test_next_round_plays_stock_gained_after_the_first_run(self):
        client = SimpleNamespace(
            _sphere_games_running=False, sphere_game_counts={}, _sphere_game_retry_after={},
            oh_use_individually=False, is_processing_cycle=False, auto_oh_enabled=True,
            auto_oc_enabled=False, auto_oq_enabled=False, auto_ot_enabled=False,
            _deferred_independent_known_work=False, sphere_game_refill_at_utc=None, loop=mock.Mock(),
        )
        runtime = SphereRuntime(
            client, target_bot_id=1, log=mock.Mock(), send=mock.AsyncMock(), click=mock.AsyncMock(),
            wait=mock.AsyncMock(return_value=True), maintenance_active=lambda: False,
            claim_pending=lambda: False, resolve_channel=mock.AsyncMock(),
            wake_status=lambda: None, ambiguous_error=lambda error: False,
        )
        status = lambda stock: SimpleNamespace(
            available_for=lambda kind: stock if kind == "oh" else 0, refill_minutes=962,
        )
        with mock.patch.object(runtime, "run_sphere_game", mock.AsyncMock(return_value=True)) as run, \
                mock.patch("mudae_core.sphere_runtime.time.monotonic") as clock:
            clock.return_value = 1000.0
            await runtime.run_available_sphere_games("channel", status(10))
            clock.return_value = 1000.0 + 3600.0
            await runtime.run_available_sphere_games("channel", status(4))
        self.assertEqual([call.args for call in run.await_args_list],
                         [("channel", "oh", 10), ("channel", "oh", 4)])

    async def test_stock_reported_while_boards_run_is_played_in_the_same_round(self):
        # The daily refill gave $oh 4, but the $tu reporting it arrived while
        # the $oc boards were running, so $oh waited for the next hour.
        client = SimpleNamespace(
            _sphere_games_running=False, sphere_game_counts={}, _sphere_game_retry_after={},
            oh_use_individually=False, is_processing_cycle=False, auto_oh_enabled=True,
            auto_oc_enabled=True, auto_oq_enabled=True, auto_ot_enabled=False,
            _deferred_independent_known_work=False, sphere_game_refill_at_utc=None, loop=mock.Mock(),
        )
        runtime = SphereRuntime(
            client, target_bot_id=1, log=mock.Mock(), send=mock.AsyncMock(), click=mock.AsyncMock(),
            wait=mock.AsyncMock(return_value=True), maintenance_active=lambda: False,
            claim_pending=lambda: False, resolve_channel=mock.AsyncMock(),
            wake_status=lambda: None, ambiguous_error=lambda error: False,
        )
        status = lambda **stock: SimpleNamespace(
            available_for=lambda kind: stock.get(kind, 0), refill_minutes=1410,
        )
        played = []

        async def play(channel, kind, uses):
            played.append((kind, uses))
            if len(played) == 1:
                await runtime.run_available_sphere_games(channel, status(oh=4, oc=11, oq=2))
            return True

        with mock.patch.object(runtime, "run_sphere_game", side_effect=play):
            await runtime.run_available_sphere_games("channel", status(oc=20, oq=2))

        self.assertEqual(played, [("oc", 10), ("oc", 10), ("oq", 2), ("oh", 4)])


class SpacedNumberReplay(unittest.TestCase):
    # Mudae writes 7 210 instead of 7,210 for some users, with a normal,
    # no-break or narrow no-break space.
    def test_spaced_key_counts_still_give_the_ten_key_discount(self):
        for space in (" ", " ", " "):
            embed = SimpleNamespace(description=f"Fate/stay night\n<:chaoskey:1> (**7{space}210**) +5% kakera value")
            self.assertEqual(mudae_bot.count_chaos_keys(embed), 1, repr(space))

    def test_spaced_kakera_value_and_ranks_are_read_whole(self):
        desc = "Fate/stay night\n**13 380**<:kakera:1>\nClaims: #1 234\nLikes: #10 922"
        value = mudae_bot.re.search(mudae_bot.REGEX_PATTERNS["KAKERA_VALUE"], desc).group(1)
        self.assertEqual(int(mudae_bot.re.sub(r"[^\d]", "", value)), 13380)
        self.assertEqual(mudae_bot.parse_mudae_ranks(desc), (1234, 10922))

    def test_separate_numbers_are_not_joined(self):
        self.assertEqual(mudae_bot.parse_mudae_ranks("Claims: #18\nLikes: #24"), (18, 24))
        embed = SimpleNamespace(description="<:chaoskey:1> (**9**) 100 kakera")
        self.assertEqual(mudae_bot.count_chaos_keys(embed), 0)


if __name__ == "__main__":
    unittest.main()
