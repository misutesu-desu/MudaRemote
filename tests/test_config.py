import json
import os
import tempfile
import unittest

from mudae_core.config import atomic_write_json, parse_inactive_hours, parse_scheduled_times, validate_preset


class ConfigTests(unittest.TestCase):
    def test_atomic_json_write_round_trips_unicode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "presets.json")
            atomic_write_json(path, {"Türkçe": {"token": ""}})
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), {"Türkçe": {"token": ""}})

    def test_schedule_and_inactive_hour_validation(self):
        values, errors = parse_scheduled_times("09:05, 23:59, 09:05")
        self.assertEqual(values, ["09:05", "23:59"])
        self.assertEqual(errors, [])
        _, errors = parse_scheduled_times("24:00")
        self.assertTrue(errors)

        values, errors = parse_inactive_hours("1-7, 23-6")
        self.assertEqual(values, [[1, 7], [23, 6]])
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
        )
        self.assertEqual(validate_preset(valid), [])


if __name__ == "__main__":
    unittest.main()
