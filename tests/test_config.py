import json
import os
import tempfile
import unittest

from mudae_core.config import atomic_write_json, parse_inactive_hours, parse_scheduled_times, validate_preset


class ConfigTests(unittest.TestCase):
    def test_atomic_json_write_round_trips_unicode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "presets.json")
            atomic_write_json(path, {"Example": {"token": ""}})
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), {"Example": {"token": ""}})

    def test_schedule_and_inactive_hour_validation(self):
        values, errors = parse_scheduled_times("09:05, 23:59, 09:05")
        self.assertEqual(values, ["09:05", "23:59"])
        self.assertEqual(errors, [])
        _, errors = parse_scheduled_times("24:00")
        self.assertTrue(errors)

        values, errors = parse_inactive_hours("1-7, 23-6")
        self.assertEqual(values, [["01:00", "07:00"], ["23:00", "06:00"]])
        self.assertEqual(errors, [])
        values, errors = parse_inactive_hours("01:30-07:15")
        self.assertEqual(values, [["01:30", "07:15"]])
        self.assertEqual(errors, [])
        _, errors = parse_inactive_hours("7-7")
        self.assertTrue(errors)

    def test_preset_validation_reports_actionable_errors(self):
        preset = {
            "token": "", "prefix": "", "mudae_prefix": "$", "roll_command": "wa",
            "channel_id": "not-an-id", "claim_interval": 0, "roll_interval": 60,
            "max_dk_power": 100, "reactive_kakera_delay_range": [2, 1],
        }
        errors = validate_preset(preset)
        self.assertTrue(any("token" in error.lower() for error in errors))
        self.assertTrue(any("prefix" in error.lower() for error in errors))
        self.assertTrue(any("Channel ID" in error for error in errors))
        self.assertTrue(any("claim_interval" in error for error in errors))
        self.assertTrue(any("minimum" in error for error in errors))

    def test_editor_drafts_may_omit_runtime_credentials(self):
        draft = {
            "token": "", "prefix": "////////", "mudae_prefix": "$", "roll_command": "wa",
            "channel_id": "", "claim_interval": 180, "roll_interval": 60,
            "max_dk_power": 100, "reactive_kakera_delay_range": [0.3, 1.0],
        }
        self.assertEqual(validate_preset(draft, resolved_token=[], require_runtime=False), [])
        runtime_errors = validate_preset(draft, resolved_token=[], require_runtime=True)
        self.assertTrue(any("token" in error.lower() for error in runtime_errors))
        self.assertTrue(any("Channel ID" in error for error in runtime_errors))

        invalid_draft = dict(draft, webhook_url="http://example.com/hook")
        self.assertTrue(any(
            "Webhook URL" in error
            for error in validate_preset(invalid_draft, resolved_token=[], require_runtime=False)
        ))

    def test_webhook_and_expert_log_selectors_are_validated(self):
        preset = {
            "token": "secret", "prefix": "////////", "mudae_prefix": "$",
            "roll_command": "wa", "channel_id": "123", "claim_interval": 180,
            "roll_interval": 60, "max_dk_power": 100,
            "reactive_kakera_delay_range": [0.3, 1.0],
            "webhook_url": "https://discord.com/api/webhooks/123/secret",
            "webhook_log_types": ["ERROR", "KAKERA"],
            "debug_log_categories": ["claim", "sphere"],
        }
        self.assertEqual(validate_preset(preset), [])

        invalid = dict(
            preset,
            webhook_url="http://example.com/hook",
            webhook_log_types=["NOPE"],
            debug_log_categories=["unknown-category"],
        )
        errors = validate_preset(invalid)
        self.assertTrue(any("Webhook URL" in error for error in errors))
        self.assertTrue(any("log type" in error for error in errors))
        self.assertTrue(any("Expert Log" in error for error in errors))

    def test_farm_timing_requires_a_complete_farm_configuration(self):
        base = {
            "token": "secret", "prefix": "////////", "mudae_prefix": "$", "roll_command": "wa",
            "channel_id": "123", "claim_interval": 180, "roll_interval": 60,
            "max_dk_power": 100, "reactive_kakera_delay_range": [0.3, 1.0],
        }

        missing_character = dict(base, farm_character_enabled=True, farm_character="")
        self.assertTrue(any("Farm Character" in error for error in validate_preset(missing_character)))

        orphaned_timing = dict(base, farm_forcedivorce_after_claim=True)
        self.assertTrue(any("requires" in error for error in validate_preset(orphaned_timing)))

        orphaned_before_roll = dict(base, farm_forcedivorce_before_roll=True)
        self.assertTrue(any("Before Rolling requires" in error for error in validate_preset(orphaned_before_roll)))

        orphaned_other_claim = dict(base, farm_forcedivorce_after_other_claim=True)
        self.assertTrue(any("Another Account Claim requires" in error for error in validate_preset(orphaned_other_claim)))

        no_timing = dict(
            base,
            farm_character_enabled=True,
            farm_character="Rem",
            farm_forcedivorce_before_roll=False,
            farm_forcedivorce_after_claim=False,
            farm_forcedivorce_after_other_claim=False,
        )
        self.assertTrue(any("at least one" in error for error in validate_preset(no_timing)))

        legacy_pre_roll = dict(
            base,
            farm_character_enabled=True,
            farm_character="Rem",
        )
        self.assertEqual(validate_preset(legacy_pre_roll), [])

        shared_only = dict(
            base,
            farm_character_enabled=True,
            farm_character="Rem",
            farm_forcedivorce_before_roll=False,
            farm_forcedivorce_after_claim=False,
            farm_forcedivorce_after_other_claim=True,
        )
        self.assertEqual(validate_preset(shared_only), [])

        valid = dict(
            base,
            farm_character_enabled=True,
            farm_character="Rem",
            farm_forcedivorce_before_roll=True,
            farm_forcedivorce_after_claim=True,
            farm_forcedivorce_after_other_claim=True,
            forcedivorce_channel_id="456",
        )
        self.assertEqual(validate_preset(valid), [])

        invalid_forcedivorce_channel = dict(base, forcedivorce_channel_id="not-an-id")
        self.assertTrue(any(
            "Forcedivorce Channel ID" in error
            for error in validate_preset(invalid_forcedivorce_channel)
        ))

    def test_kakera_settings_reject_self_defeating_combinations(self):
        base = {
            "token": "secret", "prefix": "////////", "mudae_prefix": "$",
            "roll_command": "wa", "channel_id": "123", "claim_interval": 180,
            "roll_interval": 60, "max_dk_power": 100,
            "reactive_kakera_delay_range": [0.3, 1.0],
        }

        empty_chaos = dict(base, only_chaos=True, chaos_emojis=[])
        self.assertTrue(any("Chaos Emojis" in error for error in validate_preset(empty_chaos)))

        empty_general = dict(base, kakera_reaction_snipe_mode=True, kakera_emojis=[])
        self.assertTrue(any("Kakera Emojis" in error for error in validate_preset(empty_general)))


if __name__ == "__main__":
    unittest.main()
