"""Regression coverage for the September 13 repeated-roll report."""
import asyncio
import datetime
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from mudae_core import GlobalIntervalCoordinator, clear_status_dirty
from mudae_core.runtime import get_normal_roll_cycle_state
from mudae_core.status import ResetAnchor, status_refresh_reasons
from tests.test_roll_window_production import _build_runtime, _Channel, _install_anchored_cycle


class RollExhaustionTests(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_private_status_does_not_replenish_again_at_late_local_boundary(self):
        for configured in (False, True):
            with self.subTest(configured=configured):
                bot = _build_runtime()
                channel = _Channel()
                bot._main_channel = channel
                now = datetime.datetime.now(datetime.timezone.utc)
                boundary = now + datetime.timedelta(seconds=60)
                anchor, old_cycle, _, _ = _install_anchored_cycle(bot, boundary, now, remaining=0)
                if configured:
                    anchor.authoritative_minute = boundary.minute
                bot.normal_roll_replenishment_capacity = 15
                bot.normal_roll_replenishment_capacity_confidence = True
                bot.command_pacer.minimum_delay = bot.command_pacer.maximum_delay = 0
                bot.auto_dk_enabled = bot.auto_p_enabled = bot.auto_daily_enabled = False
                bot._pre_roll_status_required = True
                snapshot = ('You can claim now!\nNext claim reset in **60** min.\n'
                            'You have **15** rolls left. Next rolls reset in **60** min.\n'
                            '$rt is available!\nPower: **100%**\n0 $dk available\n')

                async def send(content, **kwargs):
                    channel.sent.append(content)
                    if content == '$tu':
                        bot._tu_response_future.set_result(snapshot)
                    return SimpleNamespace(id=len(channel.sent))

                channel.send = send
                with mock.patch.object(mudae_bot, '_tu_interval_coordinator', GlobalIntervalCoordinator()), \
                        mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)):
                    await bot._runtime_check_status(bot, channel, '$', proceed_to_rolls=False)
                self.assertNotEqual(bot.current_roll_cycle_id, old_cycle)
                current = bot.current_roll_cycle_id
                self.assertEqual(bot.rolls_left, 15)
                # The 15 rolls from that snapshot have now been used.
                state = get_normal_roll_cycle_state(bot, current)
                state.remaining = bot.rolls_left = 0
                state.known_consumed = 15
                clear_status_dirty(bot)
                bot._runtime_advance_predicted_reset_cycles(boundary + datetime.timedelta(seconds=1))
                self.assertEqual(bot.current_roll_cycle_id, current)
                self.assertEqual(bot.rolls_left, 0)
                self.assertEqual(anchor.next_boundary_at_utc, boundary + datetime.timedelta(hours=1))

    async def test_own_limit_stops_batch_but_another_accounts_limit_does_not(self):
        for name, interaction_id, own in (
            ('AccountA', None, True), ('AccountB', None, False),
            ('AccountA', 2002, False), ('AccountB', 1001, True),
        ):
            with self.subTest(name=name, interaction_id=interaction_id):
                bot = _build_runtime()
                channel = _Channel()
                bot._main_channel = channel
                now = datetime.datetime.now(datetime.timezone.utc)
                _, cycle, _, _ = _install_anchored_cycle(bot, now + datetime.timedelta(minutes=30), now, remaining=3)
                bot.auto_mk_enabled = False
                bot.command_pacer.minimum_delay = bot.command_pacer.maximum_delay = 0
                bot._tu_response_future = asyncio.get_running_loop().create_future()

                async def send(content, **kwargs):
                    channel.sent.append(content)
                    bot._rolls_received += 1
                    message = SimpleNamespace(
                        id=9000 + len(channel.sent), channel=channel, guild=None,
                        author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
                        content='**{}**, the roulette is limited to 15 uses per hour. **59** min left.'.format(name),
                        embeds=[], components=[], interaction=None,
                        interaction_metadata=(SimpleNamespace(user=SimpleNamespace(id=interaction_id))
                                              if interaction_id is not None else None),
                    )
                    await bot.events['on_message'](message)
                    return SimpleNamespace(id=len(channel.sent), created_at=now)

                channel.send = send
                with mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)):
                    await bot._runtime_start_roll_commands(bot, channel, 3, False, False, cycle)
                self.assertEqual(len(channel.sent), 1 if own else 3)
                self.assertEqual(bot.rolls_left, 0)
                self.assertEqual('roll-limit-reached' in status_refresh_reasons(bot), own)
                self.assertFalse(bot._tu_response_future.done(), 'A limit rejection must not fulfill a $tu request')
                bot._tu_response_future.cancel()

    def test_peer_timer_alone_cannot_consume_configured_boundary(self):
        now = datetime.datetime(2026, 9, 13, 16, 34, 30, tzinfo=datetime.timezone.utc)
        anchor = ResetAnchor('roll', 60, authoritative_minute=35)
        anchor.advance_through(now)
        boundary = anchor.next_boundary_at_utc
        anchor.observe(now + datetime.timedelta(minutes=60), now)
        self.assertEqual(anchor.next_boundary_at_utc, boundary)
        self.assertEqual(len(anchor.advance_through(boundary)), 1)


if __name__ == '__main__':
    unittest.main()
