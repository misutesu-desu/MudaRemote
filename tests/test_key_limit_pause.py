"""«Pause on Key Limit»: per account, said clearly, and an optional «rolls only» scope.

Fakes only; no Discord. Names and ids are made up.
"""

import datetime
import unittest
from pathlib import Path
from types import SimpleNamespace

from mudae_core.account_roles import labelled_message, roll_batch_blocker
from mudae_core.bot_config import apply_live_config, configure_client
from mudae_core.config import validate_preset
from mudae_core.key_limit import (
    AREA_OTHER,
    AREA_ROLLS,
    end_key_limit_pause,
    key_limit_blocks,
    key_limit_pause_text,
    normalize_scope,
    start_key_limit_pause,
)
from mudae_core.runtime import prepare_active_presets

ROOT = Path(__file__).resolve().parents[1]
OPTIONS = {"bot_name": "MudaRemote", "claim_emojis": ["c"], "kakera_emojis": ["k"],
           "sphere_emojis": ["s"], "slash_available": True}
BASE = {"prefix": "!", "mudae_prefix": "$", "roll_command": "wa", "claim_interval": 180,
        "roll_interval": 60, "max_dk_power": 100, "channel_id": 111}
PROFILE = dict(BASE, profile_id="pkeys", token="tok-main", tokens=["tok-main", "tok-alt"],
               key_mode=True, auto_rolls_in_key_mode=True, pause_on_key_limit=True)
NOW = datetime.datetime(2026, 11, 28, 12, 0, tzinfo=datetime.timezone.utc)


def accounts(profile):
    result = []
    for name, data in prepare_active_presets(["Keys"], {"Keys": profile}):
        client = SimpleNamespace(command_prefix="!", hourly_tu_refresh=False, preset_name=name)
        configure_client(client, name, data, **OPTIONS)
        result.append(client)
    return result


class KeyLimitPauseTests(unittest.TestCase):
    def test_the_line_names_the_account_the_resume_time_and_the_switch(self):
        main, _alt = accounts(PROFILE)
        line = start_key_limit_pause(main, 3600, now=NOW)
        self.assertTrue(line.startswith("paused for about 1 h — the key limit was reached (resumes about "))
        self.assertIn('Turn off "Pause on Key Limit" to keep rolling.', line)
        self.assertEqual(main.key_limit_status, line)
        self.assertEqual(main.key_limit_resume_at, NOW + datetime.timedelta(hours=1))
        self.assertTrue(labelled_message("main", line).startswith("main: paused for about 1 h"))
        self.assertEqual(roll_batch_blocker(key_limit_hit=main.key_limit_hit), "key limit reached (pausing 1h)")
        self.assertEqual(end_key_limit_pause(main), "key-limit pause is over; rolling again.")
        self.assertEqual((main.key_limit_hit, main.key_limit_status, main.key_limit_resume_at), (False, None, None))

    def test_one_accounts_pause_never_stops_the_other(self):
        main, alt = accounts(PROFILE)
        start_key_limit_pause(main, 3600, now=NOW)
        self.assertTrue(key_limit_blocks(main, AREA_ROLLS))
        self.assertFalse(key_limit_blocks(alt, AREA_ROLLS))
        self.assertFalse(key_limit_blocks(alt, AREA_OTHER))
        start_key_limit_pause(alt, 3600, now=NOW)
        end_key_limit_pause(main)
        self.assertEqual((main.key_limit_hit, alt.key_limit_hit), (False, True))

    def test_everything_is_the_default_scope_and_rolls_only_keeps_the_rest_going(self):
        main, _ = accounts(PROFILE)
        self.assertEqual(main.key_limit_pause_scope, "everything")
        start_key_limit_pause(main, 3600, now=NOW)
        self.assertTrue(key_limit_blocks(main, AREA_ROLLS))
        self.assertTrue(key_limit_blocks(main, AREA_OTHER))
        main, _ = accounts(dict(PROFILE, key_limit_pause_scope="rolls only"))
        line = start_key_limit_pause(main, 3600, now=NOW)
        self.assertTrue(line.startswith("rolls paused for about 1 h"))
        self.assertTrue(key_limit_blocks(main, AREA_ROLLS))
        self.assertFalse(key_limit_blocks(main, AREA_OTHER))
        self.assertFalse(key_limit_blocks(SimpleNamespace(key_limit_hit=False), AREA_ROLLS))

    def test_the_scope_is_validated_normalized_and_live_reloadable(self):
        self.assertEqual(normalize_scope("rolls_only"), "rolls only")
        self.assertEqual(normalize_scope("bogus"), "everything")
        errors = validate_preset(dict(BASE, key_limit_pause_scope="sometimes"), resolved_token="t")
        self.assertTrue(any("key limit" in error for error in errors), errors)
        self.assertFalse(any("key limit" in error for error in validate_preset(
            dict(BASE, key_limit_pause_scope="rolls only"), resolved_token="t")))
        main, _ = accounts(PROFILE)
        changed = apply_live_config(main, dict(PROFILE, key_limit_pause_scope="rolls only"), **OPTIONS)
        self.assertIn("key_limit_pause_scope", changed)
        self.assertEqual(main.key_limit_pause_scope, "rolls only")
        self.assertEqual(key_limit_pause_text(None), 'paused for about 1 h — the key limit was reached. '
                                                     'Turn off "Pause on Key Limit" to keep rolling.')

    def test_the_bot_uses_these_helpers_and_logs_with_the_account(self):
        source = (ROOT / "mudae_bot.py").read_text(encoding="utf-8")
        self.assertNotIn('"Key Limit Hit. Pausing 1h."', source)
        self.assertIn('BotLogger.log(start_key_limit_pause(client, pause_seconds), preset_name, "ERROR", client)', source)
        self.assertIn('finish_key_limit_pause("«Pause on Key Limit» was turned off")', source)
        status = (ROOT / "mudae_core/bot_runtime.py").read_text(encoding="utf-8")
        self.assertIn('"pause_status"', status)


if __name__ == "__main__":
    unittest.main()
