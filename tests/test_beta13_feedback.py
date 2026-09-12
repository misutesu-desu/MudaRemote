import asyncio
import datetime
import inspect
from types import SimpleNamespace
import unittest

import mudae_bot
from mudae_core import (
    GlobalIntervalCoordinator, apply_authoritative_roll_remaining,
    calculate_kakera_power_cost, clear_status_dirty, get_normal_roll_cycle_state,
    has_perk_eight_buttons, has_perk_eight_discount,
)
from tests.test_roll_window_production import _build_runtime, _Channel
from tests.test_kakera_snipe_ownership import _create_test_client, _build_roll_message


class BetaFeedbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_own_roll_uses_perk_eight_colors_at_full_power_after_discount(self):
        client, channel = _create_test_client()
        client.kakera_emojis = []
        client.sphere_perk_emojis = ['kakeraY']
        client.dk_consumption = 36
        message, button = _build_roll_message(
            channel, 1013, client.user.id, client.user.name, client=client,
        )
        message.embeds[0].description += '\n46 <:sp:123> ✅'
        for offset in range(3):
            other, _ = _build_roll_message(
                channel, 2000 + offset, client.user.id, client.user.name, kakera_emoji='kakeraO',
            )
            message.components[0].children.extend(other.components[0].children)
        async def deliver_result():
            await client.events['on_message'](SimpleNamespace(
                id=3013, channel=channel, author=message.author,
                content='<:kakeraY:123> **snipe-bot +150** ($k)',
                created_at=message.created_at, embeds=[], components=[], interaction=None,
            ))
        button.click.side_effect = deliver_result
        await client.events['on_message'](message)
        button.click.assert_awaited_once()
        self.assertEqual(client.current_dk_power, 64)

    def test_post_discount_perk_eight_selection_does_not_discount_power(self):
        description = '46 <:sp:123> ✅'
        buttons = [SimpleNamespace(emoji=SimpleNamespace(name=name)) for name in
                   ('spO', 'kakeraO', 'kakeraY', 'kakeraY', 'kakeraY')]
        rows = [SimpleNamespace(children=buttons)]
        self.assertTrue(has_perk_eight_buttons(description, rows))
        self.assertFalse(has_perk_eight_discount(description))
        self.assertEqual(calculate_kakera_power_cost(30, has_chaos_discount=True), 15)
        self.assertEqual(calculate_kakera_power_cost(30), 30)
        self.assertFalse(has_perk_eight_buttons('46 spheres', rows))
        self.assertFalse(has_perk_eight_buttons(description, [SimpleNamespace(children=buttons[:3])]))
        buttons[-1].emoji.name = 'kakeraP'
        self.assertFalse(has_perk_eight_buttons(description, rows))

    def test_empty_snapshot_does_not_teach_zero_replenishment(self):
        client = _build_runtime()
        cycle = ('roll', 123, 1)
        state = get_normal_roll_cycle_state(client, cycle)
        state.proven_fresh = True
        apply_authoritative_roll_remaining(client, cycle, 0)
        self.assertEqual(state.remaining, 0)
        self.assertFalse(client.normal_roll_replenishment_capacity_confidence)
        apply_authoritative_roll_remaining(client, cycle, 13)
        apply_authoritative_roll_remaining(client, cycle, 0)
        self.assertEqual(client.normal_roll_replenishment_capacity, 13)

    def test_expired_idle_status_requires_refresh_even_with_future_resets(self):
        client = _build_runtime()
        now = datetime.datetime.now(datetime.timezone.utc)
        client.last_tu_snapshot_complete = True
        client.last_tu_query_utc = now - datetime.timedelta(hours=13)
        client.rolls_left = 0
        client.roll_reset_at_utc = now + datetime.timedelta(minutes=50)
        client.next_claim_reset_at_utc = now + datetime.timedelta(hours=2)
        clear_status_dirty(client)
        self.assertTrue(client._runtime_is_tu_still_required(client)[0])
        client.last_tu_query_utc = now
        self.assertFalse(client._runtime_is_tu_still_required(client)[0])

    def test_large_account_queue_does_not_add_fifteen_minutes(self):
        coordinator = GlobalIntervalCoordinator()
        waits = [coordinator.reserve(123, mudae_bot.TU_GLOBAL_INTERVAL_SECONDS, 100)
                 for _ in range(48)]
        self.assertLess(waits[-1], 120)
        self.assertTrue(all(b - a >= 2 for a, b in zip(waits, waits[1:])))

    async def test_bonus_roll_waits_for_live_board_and_pending_bonus_defers_next_game(self):
        client = _build_runtime()
        channel = _Channel()
        client.command_pacer.minimum_delay = 0
        client.command_pacer.maximum_delay = 0
        client._sphere_game_lock = asyncio.Lock()
        send_roll = inspect.getclosurevars(client._runtime_start_roll_commands).nonlocals['send_roll_command']
        run_game = inspect.getclosurevars(client._runtime_run_available_sphere_games).nonlocals['run_sphere_game']
        await client._sphere_game_lock.acquire()
        roll = asyncio.create_task(send_roll(channel, 'wa'))
        try:
            await asyncio.sleep(0)
            self.assertFalse(roll.done())
            self.assertEqual(channel.sent, [])
        finally:
            client._sphere_game_lock.release()
        await asyncio.wait_for(roll, 2)
        self.assertEqual(channel.sent, ['$wa'])
        self.assertFalse(await send_roll(
            channel, 'wa', expected_reset_boundary_utc=datetime.datetime.now(datetime.timezone.utc)
        ))
        self.assertEqual(channel.sent, ['$wa'])
        client._local_extra_rolls_pending = 5
        self.assertFalse(await run_game(channel, 'oh', 1))
        self.assertEqual(channel.sent, ['$wa'])
        self.assertTrue(client._deferred_independent_known_work)


if __name__ == '__main__':
    unittest.main()
