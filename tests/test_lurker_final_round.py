import os
import unittest

from mudae_core.runtime import lurker_window_state


class LurkerWindowStateTests(unittest.TestCase):
    def state(self, minutes, *, final_round_only=False, claim_available=True, lurker=True):
        return lurker_window_state(
            lurker_mode=lurker,
            final_round_only=final_round_only,
            claim_available=claim_available,
            claim_reset_minutes=minutes,
            panic_roll_minutes=5,
            round_minutes=60,
        )

    def test_default_lurker_waits_through_every_round(self):
        self.assertEqual(self.state(170), (False, True))
        self.assertEqual(self.state(90), (False, True))
        self.assertEqual(self.state(30), (False, True))
        self.assertEqual(self.state(4), (True, False))

    def test_final_round_only_rolls_normally_before_the_last_round(self):
        self.assertEqual(self.state(170, final_round_only=True), (False, False))
        self.assertEqual(self.state(61, final_round_only=True), (False, False))

    def test_final_round_only_lurks_then_panics_in_the_last_round(self):
        self.assertEqual(self.state(60, final_round_only=True), (False, True))
        self.assertEqual(self.state(30, final_round_only=True), (False, True))
        self.assertEqual(self.state(5, final_round_only=True), (True, False))

    def test_inactive_without_lurker_claim_or_known_reset(self):
        self.assertEqual(self.state(30, lurker=False, final_round_only=True), (False, False))
        self.assertEqual(self.state(30, claim_available=False), (False, False))
        self.assertEqual(self.state(None), (False, False))


class LurkerFinalRoundConfigTests(unittest.TestCase):
    def test_option_is_loaded_and_live_updatable(self):
        from types import SimpleNamespace
        from mudae_core.bot_config import LIVE_CONFIG_ATTRIBUTES, configure_client

        options = {
            "bot_name": "MudaRemote", "claim_emojis": [], "kakera_emojis": [],
            "sphere_emojis": [], "slash_available": True,
        }
        client = SimpleNamespace(hourly_tu_refresh=False)
        configure_client(client, "test", {"channel_id": 1, "lurker_final_round_only": True}, **options)
        self.assertTrue(client.lurker_final_round_only)
        client = SimpleNamespace(hourly_tu_refresh=False)
        configure_client(client, "test", {"channel_id": 1}, **options)
        self.assertFalse(client.lurker_final_round_only)
        self.assertIn("lurker_final_round_only", LIVE_CONFIG_ATTRIBUTES)

    def test_editor_exposes_the_option(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "mudae_preset_editor.py"), encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn('"lurker_final_round_only": False', source)
        self.assertIn('self.add_checkbox(lurker_sub, "lurker_final_round_only"', source)


if __name__ == "__main__":
    unittest.main()
