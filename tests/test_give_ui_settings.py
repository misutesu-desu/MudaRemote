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

    # ---- choices as a collapsible list, and conditional fields («visible_when») ----

    @staticmethod
    def _conditions(field):
        raw = field.get("visible_when")
        if raw is None:
            return []
        return raw if isinstance(raw, list) else [raw]

    def test_every_choice_has_labelled_options_and_a_valid_default(self):
        choice_fields = {key: f for key, f in self.fields.items() if "choices" in f}
        self.assertIn("harem_give_trigger", choice_fields)
        for key, field in choice_fields.items():
            with self.subTest(key=key):
                self.assertIsInstance(field["choices"], dict)
                self.assertGreaterEqual(len(field["choices"]), 2)
                for value, label in field["choices"].items():
                    self.assertIsInstance(value, str)
                    self.assertTrue(isinstance(label, str) and label.strip())
                self.assertIn(field["default"], field["choices"])

    def test_visible_when_points_at_existing_fields_and_values(self):
        found = 0
        for key, field in self.fields.items():
            for condition in self._conditions(field):
                found += 1
                with self.subTest(key=key):
                    self.assertEqual(set(condition), {"field", "equals"})
                    controller = self.fields[condition["field"]]
                    self.assertNotEqual(condition["field"], key)
                    wanted = condition["equals"]
                    wanted = wanted if isinstance(wanted, list) else [wanted]
                    self.assertTrue(wanted)
                    for value in wanted:
                        if "choices" in controller:
                            self.assertIn(value, controller["choices"])
                        else:
                            self.assertEqual(controller["type"], "boolean")
                            self.assertIsInstance(value, bool)
        self.assertGreaterEqual(found, 20)

    def test_a_controlling_field_is_never_itself_conditional_on_its_dependents(self):
        for key, field in self.fields.items():
            for condition in self._conditions(field):
                back = {c["field"] for c in self._conditions(self.fields[condition["field"]])}
                self.assertNotIn(key, back)

    def test_harem_trigger_shows_only_the_number_of_the_chosen_kind(self):
        trigger = self.fields["harem_give_trigger"]
        self.assertEqual(trigger["label"], "Give when my harem reaches")
        self.assertEqual(trigger["choices"], {"pages": "Pages ($mm)", "characters": "Characters ($mmi)",
                                              "value": "Harem value ($mmrk)"})
        self.assertNotIn("Only the number of the chosen kind", trigger["description"])
        for key, kind, title in (("harem_give_pages", "pages", "Number of pages"),
                                 ("harem_give_characters", "characters", "Number of characters"),
                                 ("harem_give_value", "value", "Harem value")):
            with self.subTest(key=key):
                self.assertEqual(self.fields[key]["label"], title)
                self.assertIn({"field": "harem_give_trigger", "equals": kind}, self._conditions(self.fields[key]))
                self.assertIn({"field": "auto_give_harem", "equals": True}, self._conditions(self.fields[key]))

    def test_fields_that_a_manual_action_reads_stay_visible(self):
        for key in ("spheres_keep", "give_kakera_button_minimum", "perk10_max_characters", "perk10_amount",
                    "side_perk10", "give_kakera_now_round", "give_spheres_now_round", "perk10_now_round"):
            with self.subTest(key=key):
                self.assertNotIn("visible_when", self.fields[key])

    def test_the_app_draws_choices_as_a_collapsible_list_and_honours_visible_when(self):
        base = ("android", "app", "src", "main", "java", "com", "mudaremote", "android")
        kotlin = read(*base, "MainActivity.kt")
        view = read(*base, "ChoiceListView.kt")
        self.assertIn("ChoiceListView(this, labelText, options", kotlin)
        self.assertIn("is ChoiceListView -> view.selected ?: oldValue", kotlin)  # saved even when collapsed
        self.assertIn("conditionHolds(key)", kotlin)
        self.assertIn("VisibleWhen.isVisible", kotlin)
        self.assertIn("setOnCheckedChangeListener { _, _ -> onFieldChanged(key) }", kotlin)
        self.assertNotIn("choices.keys().asSequence().sorted()", kotlin)
        for needle in ("minimumHeight = UiTheme.dp(context, 48)", "setPaddingRelative", "\"▼\"", "\"▲\""):
            self.assertIn(needle, view)
        self.assertNotIn("RadioButton", view)
        self.assertNotIn("Spinner", view)

    def test_screens_script_captures_the_harem_choice(self):
        script = read("android", "scripts", "screens.sh")
        for needle in ("harem-1-collapsed", "harem-2-expanded", "harem-3-characters", "harem-4-value",
                       "harem-5-pages", "Give when my harem reaches", "Alts give harem pages to the main"):
            self.assertIn(needle, script)

    def test_desktop_editor_keeps_its_own_radio_labels(self):
        # The Android wording is set by generate_schema.py; the desktop editor is untouched.
        self.assertIn("Pages: when my harem reaches X pages ($mm)", read("mudae_preset_editor.py"))


if __name__ == "__main__":
    unittest.main()
