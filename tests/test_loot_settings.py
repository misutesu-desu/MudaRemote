import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from android.generate_schema import main as generate_schema
from mudae_core.config import validate_preset
from mudae_preset_editor import PresetEditor, build_recommended_preset


ROOT = Path(__file__).resolve().parents[1]


class LootSettingsTests(unittest.TestCase):
    def test_defaults_and_android_schema(self):
        preset = build_recommended_preset()
        expected = {
            "loot_mode": "off", "kl_amount": 1000, "scrap_target_id": "",
            "scrap_amount": 500000000, "loot_min_cooldown": 30.0,
            "loot_max_cooldown": 40.0, "slash_claim_target": "",
            "slash_claim_limit": 0, "slash_claim_window_minutes": 180,
        }
        for key, value in expected.items():
            self.assertEqual(preset[key], value)
        with tempfile.TemporaryDirectory() as directory:
            generate_schema(str(ROOT), directory)
            fields = json.loads(Path(directory, "android_schema.json").read_text(encoding="utf-8"))["fields"]
        for key, value in expected.items():
            self.assertEqual(fields[key]["default"], value)
            self.assertEqual(fields[key]["section"], "Rolling" if key.startswith("slash_") else "Kakera Loot")
        self.assertEqual(set(fields["loot_mode"]["choices"]), {"off", "kl", "scrap"})
        self.assertEqual(fields["loot_mode"]["type"], "text")
        self.assertEqual(fields["kl_amount"]["type"], "number")
        self.assertIsInstance(fields["loot_min_cooldown"]["default"], float)
        self.assertEqual(fields["scrap_target_id"]["type"], "text")
        self.assertEqual(validate_preset(preset, require_runtime=False), [])

    def test_desktop_save_collects_fields(self):
        editor = mock.Mock(spec=PresetEditor)
        editor.current_preset = "example"
        values = {
            "loot_mode": "scrap", "kl_amount": "1001", "scrap_target_id": "123456789",
            "scrap_amount": "500000001", "loot_min_cooldown": "1.5",
            "loot_max_cooldown": "2.5", "slash_claim_target": "Rem",
            "slash_claim_limit": "2", "slash_claim_window_minutes": "180",
            "inactive_hours": "", "reactive_kakera_delay_min": "0.3",
            "reactive_kakera_delay_max": "1.0",
        }
        editor.widgets = {key: mock.Mock(get=lambda value=value: value) for key, value in values.items()}
        editor._persist_preset_data.return_value = True
        self.assertTrue(PresetEditor.save_current_preset(editor, show_success=False))
        saved = editor._persist_preset_data.call_args.args[0]
        self.assertEqual(saved["loot_mode"], "scrap")
        self.assertEqual(saved["scrap_target_id"], "123456789")
        self.assertEqual(saved["scrap_amount"], 500000001)
        self.assertEqual(saved["loot_min_cooldown"], 1.5)
        self.assertEqual(saved["slash_claim_target"], "Rem")
        self.assertEqual(saved["slash_claim_limit"], 2)

    def test_validation_is_mode_aware_and_rejects_invalid_numbers(self):
        base = build_recommended_preset()
        base.update(loot_mode="off", kl_amount="bad", scrap_amount="bad", loot_min_cooldown=float("nan"))
        self.assertEqual(validate_preset(base, require_runtime=False), [])
        for changes, fragment in (
            ({"loot_mode": "other"}, "Loot mode"),
            ({"loot_mode": "kl", "kl_amount": 0}, "kl_amount"),
            ({"loot_mode": "kl", "kl_amount": True}, "kl_amount"),
            ({"loot_mode": "kl", "kl_amount": 1.5}, "kl_amount"),
            ({"loot_mode": "kl", "kl_amount": 1, "loot_min_cooldown": float("nan")}, "loot_min_cooldown"),
            ({"loot_mode": "kl", "kl_amount": 1, "loot_min_cooldown": 2, "loot_max_cooldown": 1}, "Maximum loot cooldown"),
            ({"loot_mode": "scrap", "scrap_amount": 1, "scrap_target_id": ""}, "Scrap target"),
            ({"loot_mode": "scrap", "scrap_amount": float("inf"), "scrap_target_id": "123"}, "scrap_amount"),
            ({"slash_claim_limit": 2, "slash_claim_target": ""}, "character target"),
            ({"slash_claim_limit": -1}, "slash_claim_limit"),
            ({"slash_claim_window_minutes": False}, "slash_claim_window_minutes"),
        ):
            with self.subTest(changes=changes):
                data = dict(build_recommended_preset(), **changes)
                self.assertTrue(any(fragment in error for error in validate_preset(data, require_runtime=False)))
        valid = dict(build_recommended_preset(), loot_mode="scrap", scrap_target_id="123456789", slash_claim_limit=2, slash_claim_target="Rem", use_slash_rolls=False)
        self.assertEqual(validate_preset(valid, require_runtime=False), [])


if __name__ == "__main__":
    unittest.main()
