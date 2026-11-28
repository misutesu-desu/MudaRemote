import json
import os
import subprocess
import sys
import tempfile
import unittest

from mudae_core.kakera_give import GiveSettings, amount_mode_from_preset, validate_give_settings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class AmountModeTests(unittest.TestCase):
    def test_default_is_everything(self):
        self.assertEqual(amount_mode_from_preset({}), "everything")
        self.assertTrue(GiveSettings.from_preset({}).give_extra)

    def test_choice_wins_over_the_old_switch(self):
        self.assertEqual(amount_mode_from_preset({"give_kakera_amount_mode": "amount", "give_kakera_extra": True}), "amount")
        self.assertFalse(GiveSettings.from_preset({"give_kakera_amount_mode": "amount", "give_kakera_extra": True}).give_extra)
        self.assertTrue(GiveSettings.from_preset({"give_kakera_amount_mode": "everything", "give_kakera_extra": False}).give_extra)

    def test_stored_profile_without_the_choice_keeps_its_switch(self):
        self.assertEqual(amount_mode_from_preset({"give_kakera_extra": False}), "amount")
        self.assertEqual(amount_mode_from_preset({"give_kakera_extra": True}), "everything")
        self.assertEqual(amount_mode_from_preset({"give_kakera_amount_mode": "nonsense", "give_kakera_extra": False}), "amount")

    def test_validation(self):
        self.assertEqual(validate_give_settings({"give_kakera_amount_mode": "amount"}), [])
        self.assertEqual(len(validate_give_settings({"give_kakera_amount_mode": "weird"})), 1)


class SchemaAndUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        subprocess.run([sys.executable, "-I", os.path.join(ROOT, "android", "generate_schema.py"), ROOT, cls.tmp.name],
                       check=True, capture_output=True)
        with open(os.path.join(cls.tmp.name, "android_schema.json"), encoding="utf-8") as handle:
            cls.fields = json.load(handle)["fields"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_amount_choice_replaces_the_switch(self):
        self.assertNotIn("give_kakera_extra", self.fields)
        field = self.fields["give_kakera_amount_mode"]
        self.assertEqual(field["default"], "everything")
        self.assertEqual(set(field["choices"]), {"everything", "amount"})
        self.assertEqual(field["section"], "Main & alts")

    def test_now_actions_are_the_last_rows_of_the_group(self):
        group = {key: f for key, f in self.fields.items() if f.get("section") == "Main & alts"}
        last = sorted(group, key=lambda key: group[key].get("order", 100))[-3:]
        self.assertEqual(last, ["give_kakera_now_round", "give_spheres_now_round", "perk10_now_round"])
        labels = [group[key]["label"] for key in last]
        self.assertEqual(labels, ["Give kakera now", "Give spheres now", "Upgrade perk 10 now"])
        for key in last:
            self.assertEqual(group[key]["widget"], "request_now")

    def test_perk_amount_field(self):
        field = self.fields["perk10_amount"]
        self.assertEqual(field["default"], 0)
        self.assertIn("0 = as many as the spheres allow", field["label"])

    def test_profiles_card_has_no_give_button(self):
        kotlin = read("android", "app", "src", "main", "java", "com", "mudaremote", "android", "MainActivity.kt")
        self.assertNotIn("giveKakeraQuickBtn", kotlin)
        self.assertIn('"perk10_now_round" -> requestUpgradePerk10()', kotlin)
        self.assertIn('it != "give_kakera_extra"', kotlin)  # a stored key is never dropped on save

    def test_switch_rows_let_titles_wrap(self):
        kotlin = read("android", "app", "src", "main", "java", "com", "mudaremote", "android", "MainActivity.kt")
        start = kotlin.index('tag = "switch_row"')
        block = kotlin[start:start + 2600]
        self.assertIn("maxLines = Int.MAX_VALUE", block)
        self.assertIn("LinearLayout.LayoutParams(0, -2, 1f))", block)
        self.assertNotIn("topMargin = UiTheme.dp(this@MainActivity, 10)", block)
        self.assertIn("headerDescription.maxLines = if (open) Int.MAX_VALUE else 2", kotlin)

    def test_screens_walk_covers_expanded_groups_at_two_font_scales(self):
        script = read("android", "scripts", "screens.sh")
        self.assertIn('walk_expanded fs130-open', script)
        self.assertIn('walk_expanded fs150-open', script)
        self.assertIn('font_scale 1.5', script)
        self.assertIn('tap_text "The first token is the main*"', script)

    def test_desktop_editor_wording(self):
        editor = read("mudae_preset_editor.py")
        for text in ("Give kakera now", "Give spheres now", "Upgrade perk 10 now", "When kakera reaches the amount",
                     "Characters to upgrade each time (0 = as many as the spheres allow)"):
            self.assertIn(text, editor)
        self.assertNotIn('"Give all kakera now"', editor)


if __name__ == "__main__":
    unittest.main()
