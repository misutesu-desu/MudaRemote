"""Exercise production response matching and delayed-reply retry suppression."""
import ast
import asyncio
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest import mock


def production_functions(*names):
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'mudae_bot.py').read_text(encoding='utf-8'))
    return compile(ast.Module(body=[
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ], type_ignores=[]), '<production tu>', 'exec')


class TuResponseIdentityTests(unittest.TestCase):
    def test_server_nickname_is_recognized_without_accepting_other_accounts(self):
        user = SimpleNamespace(id=7, name='deoprrr', display_name='Deoprrr')
        guild = SimpleNamespace(get_member=lambda uid: SimpleNamespace(display_name='𝕯𝖊𝖔𝖕𝖗𝖗') if uid == 7 else None)
        scope = dict(client=SimpleNamespace(user=user), re=re, TARGET_BOT_ID=42,
                     REGEX_PATTERNS={'USER_BOLD': r'^\*\*(.+?)\*\*'})
        exec(production_functions('claim_identities', 'is_tu_response_for_self'), scope)
        message = SimpleNamespace(author=SimpleNamespace(id=42), guild=guild,
                                  content='**𝕯𝖊𝖔𝖕𝖗𝖗**\nYou can claim now!\nYou have **10** rolls left.')
        self.assertTrue(scope['is_tu_response_for_self'](message))
        for name in ('deoprrr', 'Deoprrr'):
            message.content = '**' + name + '**\nYou have **10** rolls left.'
            self.assertTrue(scope['is_tu_response_for_self'](message))
        message.content = '**deoprrr-other**\nYou have **10** rolls left.'
        self.assertFalse(scope['is_tu_response_for_self'](message))
        message.content = '**𝕯𝖊𝖔𝖕𝖗𝖗**\nYou have **10** rolls left.'
        message.author.id = 99
        self.assertFalse(scope['is_tu_response_for_self'](message))


class TuDelayedReplyTests(unittest.IsolatedAsyncioTestCase):
    async def check_retry(self, arrival, slash):
        future = asyncio.get_running_loop().create_future()
        client = SimpleNamespace(is_paused=False, rolling_enabled=True, _tu_response_future=future, mudae_prefix='$')
        async def delay(_seconds):
            if arrival == 'pacing':
                future.set_result('status')
            return True
        async def inactivity(_channel):
            if arrival == 'inactivity' and not future.done():
                future.set_result('status')
            return True, False
        send = mock.AsyncMock(return_value=True)
        trigger = mock.AsyncMock(return_value=True)
        scope = dict(client=client, is_maintenance_active=lambda: False,
                     is_tu_still_required=lambda *a, **kw: (True, 'required'),
                     _tu_interval_coordinator=SimpleNamespace(reserve=lambda *a: 10),
                     TU_GLOBAL_INTERVAL_SECONDS=10, BotLogger=mock.Mock(), preset_name='test',
                     active_delay=delay, wait_for_tu_inactivity=inactivity,
                     _slash_ready=lambda: slash, _trigger_mudae_slash=trigger, guarded_send=send)
        exec(production_functions('send_tu_command'), scope)
        if arrival == 'before':
            future.set_result('status')
        self.assertFalse(await scope['send_tu_command'](SimpleNamespace(id=1)))
        self.assertEqual(future.result(), 'status')
        send.assert_not_awaited()
        trigger.assert_not_awaited()
        self.assertFalse(client._tu_in_flight)

    async def test_reply_cancels_text_and_slash_retry_at_each_wait(self):
        for slash in (False, True):
            for arrival in ('before', 'pacing', 'inactivity'):
                with self.subTest(slash=slash, arrival=arrival):
                    await self.check_retry(arrival, slash)
