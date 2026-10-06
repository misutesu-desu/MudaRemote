import asyncio
import inspect
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from tests.test_kakera_snipe_ownership import _build_roll_message
from tests.test_roll_window_production import _build_runtime


def closure(function, name):
    return inspect.getclosurevars(function).nonlocals[name]


class ClaimFallbackTests(unittest.IsolatedAsyncioTestCase):
    """A batch claim that does not land moves on to the next best roll."""

    def _runtime(self):
        client = _build_runtime()
        client.loop = asyncio.get_running_loop()
        client.command_pacer.minimum_delay = client.command_pacer.maximum_delay = 0
        client.claim_right_available = True
        client.rt_available = False
        client.claim_emojis = ['heart']
        return client

    def _rolls(self, client, channel):
        best, best_button = _build_roll_message(channel, 94001, client.user.id, client.user.name, 'heart')
        best.embeds[0].author.name = 'Tighnari'
        best.embeds[0].description = 'Genshin\n160<:kakera:123>'
        second, second_button = _build_roll_message(channel, 94002, client.user.id, client.user.name, 'heart')
        second.embeds[0].author.name = 'Second Best'
        second.embeds[0].description = 'Series\n120<:kakera:123>'
        rolls = {best.id: best, second.id: second}

        async def fetch(message_id):
            return rolls[message_id]
        channel.fetch_message = fetch
        return best, best_button, second, second_button

    async def _drain(self):
        for _ in range(5):
            pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            if not pending:
                return
            await asyncio.gather(*pending, return_exceptions=True)

    def _helpers(self, client):
        handle = closure(client._runtime_start_roll_commands, 'handle_mudae_messages')
        remember = client._runtime_remember_claim_fallbacks
        schedule = client._runtime_schedule_claim_fallback
        return handle, remember, schedule

    async def test_batch_remembers_next_best_rolls(self):
        client = self._runtime()
        channel = SimpleNamespace(id=123)
        best, best_button, second, second_button = self._rolls(client, channel)
        handle, _, _ = self._helpers(client)

        async def married():
            pending = client.pending_claim
            client._runtime_record_claim_text_evidence(SimpleNamespace(
                id=pending['confirmation_min_id'] + 1, channel=channel,
                author=SimpleNamespace(id=mudae_bot.TARGET_BOT_ID),
                content='**AccountA** and **Tighnari** are now married!',
            ))
        best_button.click.side_effect = married
        with mock.patch.object(mudae_bot.BotLogger, 'log'):
            await handle(client, channel, [second, best], False, False)
        best_button.click.assert_awaited_once()
        second_button.click.assert_not_awaited()
        fallback = client._claim_fallback
        self.assertEqual(fallback['after'], best.id)
        self.assertEqual([c[1] for c in fallback['candidates']], ['second best'])

    async def test_failed_claim_with_ready_right_claims_next_best(self):
        client = self._runtime()
        channel = SimpleNamespace(id=123)
        best, best_button, second, second_button = self._rolls(client, channel)
        _, remember, _ = self._helpers(client)
        remember(best.id, channel, [(second, 'second best', 120, 'series')])
        client.claim_retry_counts[best.id] = 1
        client.pending_claim = dict(
            message_id=best.id, character_name='Tighnari', character_kakera=160,
            character_series='Genshin', consumes_claim=True, is_snipe_action=False,
            claim_was_available=True, created_monotonic=time.monotonic(), channel=channel,
        )
        resolve = closure(client._runtime_check_status, 'resolve_pending_claim_from_status')
        with mock.patch.object(mudae_bot.BotLogger, 'log') as log:
            await resolve(True, channel)
            await self._drain()
        second_button.click.assert_awaited()
        best_button.click.assert_not_awaited()
        self.assertTrue(any('Claim fallback: Tighnari did not land' in str(c) for c in log.call_args_list))

    async def test_no_fallback_once_the_claim_right_is_gone(self):
        client = self._runtime()
        channel = SimpleNamespace(id=123)
        best, _, second, second_button = self._rolls(client, channel)
        _, remember, schedule = self._helpers(client)
        remember(best.id, channel, [(second, 'second best', 120, 'series')])
        client.claim_right_available = False
        self.assertFalse(schedule(best.id, 'Tighnari'))
        await self._drain()
        second_button.click.assert_not_awaited()

    async def test_expired_fallback_is_dropped(self):
        client = self._runtime()
        channel = SimpleNamespace(id=123)
        best, _, second, second_button = self._rolls(client, channel)
        _, remember, schedule = self._helpers(client)
        remember(best.id, channel, [(second, 'second best', 120, 'series')])
        client._claim_fallback['expires_monotonic'] = time.monotonic() - 1
        self.assertFalse(schedule(best.id, 'Tighnari'))
        await self._drain()
        second_button.click.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
