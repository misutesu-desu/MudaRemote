"""Shared adaptive slash windows and their live roll dispatch."""

import ast
import asyncio
import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from mudae_core.bot_config import configure_client
from mudae_core.roll_mode import AdaptiveSlashLedger


def account(channel=123, target=" asuna ", limit=2, minutes=180, slash=True):
    return SimpleNamespace(
        target_channel_id=channel,
        slash_claim_target=target,
        slash_claim_limit=limit,
        slash_claim_window_minutes=minutes,
        use_slash_rolls=slash,
    )


class AdaptiveSlashLedgerTests(unittest.TestCase):
    def test_configuration_registers_only_enabled_targets(self):
        settings = {"channel_id": 123, "use_slash_rolls": True,
                    "slash_claim_target": " AsUnA ", "slash_claim_limit": 2}
        with mock.patch("mudae_core.roll_mode.adaptive_slash_ledger.register") as register:
            client = SimpleNamespace()
            configure_client(client, "test", settings, bot_name="MudaRemote",
                             claim_emojis=[], kakera_emojis=[], sphere_emojis=[], slash_available=True)
            self.assertEqual((client.slash_claim_target, client.slash_claim_limit,
                              client.slash_claim_window_minutes), ("asuna", 2, 180))
            register.assert_called_once_with(123, "asuna", 180)
            configure_client(SimpleNamespace(), "test", {**settings, "slash_claim_limit": 0},
                             bot_name="MudaRemote", claim_emojis=[], kakera_emojis=[],
                             sphere_emojis=[], slash_available=True)
            register.assert_called_once()

    def test_accounts_share_only_matching_verified_claims(self):
        ledger = AdaptiveSlashLedger()
        first = account()
        second = account(target="AsUnA")
        ledger.register(123, "Asuna", 180, now=10)
        self.assertTrue(ledger.should_use_slash(first, now=11))
        ledger.record(999, "Asuna", 1, now=12)
        ledger.record(123, "Other", 2, now=12)
        self.assertTrue(ledger.should_use_slash(second, now=13))
        ledger.record(123, " ASUNA ", 3, now=14)  # Another account need not enable adaptive rolls.
        ledger.record(123, "Asuna", 3, now=15)  # Duplicate verification of one roll.
        self.assertTrue(ledger.should_use_slash(first, now=16))
        ledger.record(123, "Asuna", 4, now=17)
        self.assertFalse(ledger.should_use_slash(first, now=18))
        self.assertFalse(ledger.should_use_slash(second, now=18))
        self.assertTrue(ledger.should_use_slash(account(channel=999), now=18))

    def test_fixed_boundary_resets_count_and_dedup(self):
        ledger = AdaptiveSlashLedger()
        client = account(limit=1, minutes=3)
        ledger.register(123, "asuna", 3, now=10)
        ledger.record(123, "asuna", 5, now=189.9)
        self.assertFalse(ledger.should_use_slash(client, now=189.9))
        self.assertTrue(ledger.should_use_slash(client, now=190))
        ledger.record(123, "asuna", 6, now=191)
        self.assertFalse(ledger.should_use_slash(client, now=192))
        # A late query keeps the original 10, 190, 370... group boundaries.
        self.assertTrue(ledger.should_use_slash(client, now=370))

    def test_disabled_settings_preserve_configured_mode(self):
        ledger = AdaptiveSlashLedger()
        self.assertFalse(ledger.should_use_slash(account(slash=False), now=0))
        self.assertTrue(ledger.should_use_slash(account(target=""), now=0))
        self.assertTrue(ledger.should_use_slash(account(limit=0), now=0))


class RollDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_switches_to_text_and_back_at_window_boundary(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "mudae_bot.py").read_text(encoding="utf-8"))
        send = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "send_roll_command")
        ledger = AdaptiveSlashLedger()
        ledger.register(123, "asuna", 3, now=10)
        client = account(limit=1, minutes=3)
        client.user = SimpleNamespace(id=1, name="test")
        client._sphere_game_lock = None
        client.is_paused = client.key_limit_hit = False
        client.roll_reset_at_utc = None
        client.roll_command_correlation = mock.Mock()
        client.roll_command_correlation.prearm.return_value = 1
        client.mudae_prefix = "$"
        channel = SimpleNamespace(id=123)
        slash = mock.AsyncMock(return_value=True)
        text = mock.AsyncMock(return_value=SimpleNamespace(id=8, created_at=None))
        clock = [11]
        scope = {
            "asyncio": asyncio,
            "datetime": datetime,
            "timezone": datetime.timezone,
            "client": client,
            "is_maintenance_active": lambda: False,
            "effective_slash_rolls": lambda: ledger.should_use_slash(client, now=clock[0]),
            "_slash_ready": lambda: True,
            "_trigger_mudae_slash": slash,
            "guarded_send": text,
        }
        exec(compile(ast.Module(body=[send], type_ignores=[]), "<roll dispatch>", "exec"), scope)
        await scope["send_roll_command"](channel, "wa")
        slash.assert_awaited_once()
        text.assert_not_awaited()
        ledger.record(123, "asuna", 7, now=12)
        await scope["send_roll_command"](channel, "wa")
        text.assert_awaited_once_with(channel, "$wa")
        self.assertEqual(slash.await_count, 1)
        clock[0] = 190
        await scope["send_roll_command"](channel, "wa")
        self.assertEqual(slash.await_count, 2)


if __name__ == "__main__":
    unittest.main()
