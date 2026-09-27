"""Live preset updates keep process state while refreshing behavior."""

from types import SimpleNamespace
import unittest
from unittest import mock

from mudae_core.bot_config import apply_live_config, configure_client


OPTIONS = {
    "bot_name": "MudaRemote",
    "claim_emojis": ["old-claim"],
    "kakera_emojis": ["old-kakera"],
    "sphere_emojis": ["old-sphere"],
    "slash_available": True,
}


def fresh_client(preset=None):
    client = SimpleNamespace(command_prefix="old-prefix", hourly_tu_refresh=False)
    configure_client(client, "test", {"channel_id": 123, **(preset or {})}, **OPTIONS)
    return client


class LiveConfigTests(unittest.TestCase):
    def test_projection_updates_behavior_and_preserves_runtime_objects(self):
        client = fresh_client()
        client.min_kakera = 999
        client.max_claim_rank = 888
        client.max_like_rank = 777
        client.current_min_kakera_for_roll_claim = 666
        client.rolls_left = 3
        client.sphere_game_counts["oh"] = 2
        client._normal_roll_cycle_state["cycle"] = object()
        client._sphere_game_lock = object()
        client._immediate_check_event = object()
        client._last_scheduled_dk_window = object()
        client.rolling_enabled = False
        client.roll_interval = 45
        client.claim_interval = 120
        client.persistent_stagger_seconds = 7
        client.skip_initial_commands = True
        client.target_channel_id = 123
        client.main_account_id = "old-account"
        client.snipe_channels = {123}
        preserved = {
            name: getattr(client, name)
            for name in (
                "kakera_power_ledger", "kakera_interaction_ledger",
                "roll_reset_anchor", "claim_reset_anchor",
                "roll_command_correlation", "roll_action_timing",
                "normal_roll_action_owner", "sphere_button_budget",
                "_normal_roll_cycle_state", "_sphere_game_lock",
                "_immediate_check_event", "_last_scheduled_dk_window",
                "sphere_game_counts",
            )
        }
        preset = {
            "channel_id": 999, "main_account_id": "new-account",
            "snipe_channels": [999], "min_kakera": 250,
            "max_claim_rank": 100, "max_like_rank": 80,
            "claim_rounds_thresholds": [{"round": 1, "min_kakera": 300}],
            "rolling": True, "roll_interval": 90,
            "persistent_stagger_seconds": 1,
            "skip_initial_commands": False, "scheduled_roll_times": ["12:30"],
            "roll_speed": 2.5, "prefix": "!", "hourly_tu_refresh": True,
            "wishlist": ["AsUnA"], "farm_characters": [" A ", "a", "B"],
            "dk_schedule_time": "12:00", "webhook_url": " https://example.test/hook ",
        }
        changed = apply_live_config(client, preset, **OPTIONS)

        self.assertTrue({"base_min_kakera", "base_max_claim_rank", "base_max_like_rank",
                         "claim_rounds_thresholds", "slash_min_interval", "scheduled_roll_times",
                         "command_prefix", "hourly_tu_refresh"} <= changed)
        self.assertEqual((client.base_min_kakera, client.base_max_claim_rank,
                          client.base_max_like_rank), (250, 100, 80))
        self.assertEqual((client.min_kakera, client.max_claim_rank, client.max_like_rank,
                          client.current_min_kakera_for_roll_claim), (999, 888, 777, 666))
        self.assertEqual(client.slash_min_interval, 2.5)
        self.assertEqual(client.wishlist, {"asuna"})
        self.assertEqual(client.farm_characters, ["A", "B"])
        self.assertEqual(client.webhook_url, "https://example.test/hook")
        self.assertEqual((client.command_prefix, client.hourly_tu_refresh), ("!", True))
        self.assertEqual((client.target_channel_id, client.main_account_id,
                          client.snipe_channels), (123, "new-account", {999}))
        self.assertEqual(client.kakera_snipe_channels, {999})
        self.assertEqual((client.rolling_enabled, client.roll_interval,
                          client.claim_interval, client.persistent_stagger_seconds,
                          client.skip_initial_commands), (False, 45, 120, 7, True))
        self.assertEqual((client.rolls_left, client.sphere_game_counts["oh"]), (3, 2))
        for name, original in preserved.items():
            self.assertIs(getattr(client, name), original, name)

    def test_malformed_projection_changes_nothing_or_registers_nothing(self):
        client = fresh_client()
        before = vars(client).copy()
        preset = {
            "channel_id": 123, "use_slash_rolls": True,
            "slash_claim_target": "Asuna", "slash_claim_limit": 2,
            "roll_speed": 3.0, "max_claim_rank": "invalid",
        }
        with mock.patch("mudae_core.roll_mode.adaptive_slash_ledger.register") as register:
            with self.assertRaises(ValueError):
                apply_live_config(client, preset, **OPTIONS)
        self.assertEqual(vars(client), before)
        register.assert_not_called()

    def test_adaptive_registration_happens_once_after_projection(self):
        client = fresh_client()
        preset = {
            "channel_id": 999, "use_slash_rolls": True,
            "slash_claim_target": " AsUnA ", "slash_claim_limit": "2",
            "slash_claim_window_minutes": "30",
        }
        with mock.patch("mudae_core.roll_mode.adaptive_slash_ledger.register") as register:
            changed = apply_live_config(client, preset, **OPTIONS)
            register.assert_called_once_with(123, "asuna", 30)
        self.assertTrue({"use_slash_rolls", "slash_claim_target",
                         "slash_claim_limit", "slash_claim_window_minutes"} <= changed)

    def test_defaults_restore_missing_behavior_without_touching_overrides(self):
        client = fresh_client({"roll_speed": 4, "wishlist": ["Asuna"], "debug_mode": True})
        client.min_kakera = 900
        changed = apply_live_config(client, {"channel_id": 123}, **OPTIONS)
        self.assertEqual((client.roll_speed, client.slash_min_interval, client.wishlist,
                          client.debug_mode, client.base_min_kakera),
                         (0.4, 1.0, set(), False, 100))
        self.assertEqual(client.min_kakera, 900)
        self.assertTrue({"roll_speed", "slash_min_interval", "wishlist",
                         "debug_mode"} <= changed)


if __name__ == "__main__":
    unittest.main()
