import asyncio
import datetime
import inspect
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from mudae_core.claiming import ClaimOutcome
from mudae_core.status import clear_status_dirty, mark_status_dirty, status_dirty_fields
from tests.test_kakera_snipe_ownership import _build_roll_message
from tests.test_roll_window_production import _build_runtime
from tests.test_private_roll_sync_delay import _create_test_client, _attach_status_channel


def closure(function, name):
    return inspect.getclosurevars(function).nonlocals[name]


class FeedbackRegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_claim_hour_uses_current_deadline_not_cached_round(self):
        client = _build_runtime()
        now = datetime.datetime.now(datetime.timezone.utc)
        client.auto_rolls_enabled = True
        client.auto_rolls_only_claim_hour = True
        client.claim_right_available = True
        client._dynamic_claim_round = 3
        client.next_claim_reset_at_utc = now + datetime.timedelta(minutes=95)
        client.roll_reset_at_utc = now + datetime.timedelta(minutes=35)
        evaluate = closure(client._runtime_start_roll_commands, 'evaluate_daily_rolls')
        self.assertEqual(evaluate(now), 'outside-claim-hour')
        client.next_claim_reset_at_utc = None
        self.assertEqual(evaluate(now), 'outside-claim-hour')
        client.next_claim_reset_at_utc = now + datetime.timedelta(minutes=25)
        self.assertEqual(evaluate(now), 'execute')
        # A corrected timer before the observed reset must revoke the latch.
        client.next_claim_reset_at_utc = now + datetime.timedelta(minutes=95)
        self.assertEqual(evaluate(now), 'outside-claim-hour')

    def test_observed_claim_reset_retains_eligibility_only_until_roll_reset(self):
        client = _build_runtime()
        now = datetime.datetime.now(datetime.timezone.utc)
        client.auto_rolls_enabled = True
        client.auto_rolls_only_claim_hour = True
        client.claim_right_available = False
        client.next_claim_reset_at_utc = now + datetime.timedelta(minutes=10)
        client.roll_reset_at_utc = now + datetime.timedelta(minutes=35)
        evaluate = closure(client._runtime_start_roll_commands, 'evaluate_daily_rolls')
        self.assertEqual(evaluate(now), 'wait-claim-reset')
        client.claim_right_available = True
        client.next_claim_reset_at_utc = now + datetime.timedelta(minutes=190)
        self.assertEqual(evaluate(now + datetime.timedelta(minutes=11)), 'execute')
        self.assertEqual(evaluate(now + datetime.timedelta(minutes=36)), 'outside-claim-hour')

    async def test_claim_recovery_bypasses_existing_randomized_status_delay(self):
        client = _create_test_client(server_reset_minute=None, rolling_enabled=False,
                                     last_tu_snapshot_complete=False)
        channel = _attach_status_channel(client)
        client.tu_query_count = 1
        client._tu_timing_deadline_utc = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=18)
        mark_status_dirty(client, {'claim'}, reason='claim-verification-inconclusive', urgent=True)
        with mock.patch.object(mudae_bot._tu_interval_coordinator, 'reserve', return_value=0), \
                mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)):
            await client._runtime_check_status(client, channel, '$', proceed_to_rolls=False)
        self.assertEqual(channel.sent, ['$tu'])

    async def test_cooldown_only_does_not_announce_success_or_spend_rt(self):
        client = _build_runtime()
        channel = SimpleNamespace(id=123)
        pending = dict(message_id=92001, character_name='Mimikyu', character_kakera=254,
                       character_series='Pokemon', consumes_claim=True, is_snipe_action=True,
                       claim_was_available=True, created_monotonic=time.monotonic(), channel=channel)
        client.pending_claim = pending
        client.auto_rt_after_claim = True
        client.rt_available = True
        client.next_claim_reset_at_utc = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=120)
        resolve = closure(client._runtime_check_status, 'resolve_pending_claim_from_status')
        with mock.patch.object(mudae_bot.BotLogger, 'log') as log:
            await resolve(False, channel)
        self.assertFalse(pending.get('finalized', False))
        self.assertIsNone(client.pending_claim)
        self.assertFalse(any('SUCCESS' in str(call) for call in log.call_args_list))

    async def test_guild_nickname_is_valid_claim_owner_evidence(self):
        client = _build_runtime()
        guild = SimpleNamespace(get_member=lambda user_id: SimpleNamespace(display_name='Guild Nick'))
        embed = SimpleNamespace(footer=SimpleNamespace(text='Belongs to Guild Nick'))
        message = SimpleNamespace(id=92002, guild=guild, embeds=[embed])
        channel = SimpleNamespace(id=123, guild=guild, fetch_message=mock.AsyncMock(return_value=message))
        pending = dict(message_id=message.id, character_name='Asmodeus', character_kakera=388,
                       character_series='Series', consumes_claim=True, is_snipe_action=True,
                       claim_was_available=True, created_monotonic=time.monotonic(), channel=channel)
        client.pending_claim = pending
        outcome = await client._runtime_verify_snipe_outcome(client, channel, message, pending)
        self.assertEqual(outcome, ClaimOutcome.SUCCESS)

    async def test_exact_batch_does_not_resurrect_reconciled_deferred_fields(self):
        client = _create_test_client(server_reset_minute=None, humanization_enabled=False)
        channel = _attach_status_channel(client)
        clear_status_dirty(client)
        client._roll_batch_deferred_status_fields = {'claim'}
        client.claim_right_available = False
        client.rt_available = False
        client.roll_reset_at_utc = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=35)
        with mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)):
            await client._runtime_start_roll_commands(client, channel, 0, False, True)
        self.assertNotIn('claim', status_dirty_fields(client))

    async def test_collected_claim_skips_stale_best_roll_for_live_candidate(self):
        client = _build_runtime()
        client.loop = asyncio.get_running_loop()
        client.command_pacer.minimum_delay = client.command_pacer.maximum_delay = 0
        client.claim_right_available = True
        client.rt_available = False
        client.claim_emojis = ['heart']
        channel = SimpleNamespace(id=123)
        stale, stale_button = _build_roll_message(channel, 93001, client.user.id, client.user.name, 'heart')
        live, live_button = _build_roll_message(channel, 93002, client.user.id, client.user.name, 'heart')
        stale.embeds[0].description = 'Series\n500<:kakera:123>'
        live.embeds[0].author.name = 'Live Candidate'
        fresh_stale, fresh_button = _build_roll_message(channel, 93001, client.user.id, client.user.name, 'heart')
        live.embeds[0].description = 'Series\n150<:kakera:123>'
        fresh_button.disabled = True
        fresh_stale.embeds[0].footer.text = 'Belongs to Someone Else'
        async def fetch(message_id):
            return fresh_stale if message_id == stale.id else live
        channel.fetch_message = fetch
        async def claim_live():
            pending = client.pending_claim
            client._runtime_record_claim_text_evidence(SimpleNamespace(
                id=pending['confirmation_min_id'] + 1, channel=channel,
                author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
                content='**AccountA** and **Live Candidate** are now married!',
            ))
        live_button.click.side_effect = claim_live
        # A stale interaction can ACK without claiming anything.
        handle = closure(client._runtime_start_roll_commands, 'handle_mudae_messages')
        result = await handle(client, channel, [stale, live], False, False)
        self.assertTrue(result)
        stale_button.click.assert_not_awaited()
        fresh_button.click.assert_not_awaited()
        live_button.click.assert_awaited_once()
        self.assertEqual(client.last_successfully_claimed_character, 'live candidate')
