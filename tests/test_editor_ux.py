import os
import re
from types import SimpleNamespace
import unittest

from mudae_preset_editor import PresetEditor, build_recommended_preset
from mudae_core.config import validate_preset


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class EditorUxContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(PROJECT_ROOT, "mudae_preset_editor.py"), "r", encoding="utf-8") as handle:
            cls.editor = handle.read()
        with open(os.path.join(PROJECT_ROOT, "README.md"), "r", encoding="utf-8") as handle:
            cls.readme = handle.read()

    def test_guided_setup_is_the_default_and_expert_mode_remains_available(self):
        self.assertIn('self.editor_mode = "quick"', self.editor)
        self.assertIn('self.show_editor_mode("quick")', self.editor)
        self.assertIn('"Quick Setup"', self.editor)
        self.assertIn('"Advanced Settings"', self.editor)

    def test_guided_setup_uses_user_facing_goals_not_free_claim_internal_setting(self):
        self.assertIn('"Claim matching characters"', self.editor)
        self.assertIn('"reactive_snipe_on_own_rolls"', self.editor)
        quick_block = self.editor[self.editor.index("def build_quick_setup"):self.editor.index("def show_editor_mode")]
        self.assertNotIn('"auto_free_claim", "Claim matching characters"', quick_block)

    def test_recommended_profile_covers_the_mainstream_flow(self):
        preset = build_recommended_preset()
        self.assertEqual(preset["roll_command"], "wa")
        self.assertEqual(preset["min_kakera"], 100)
        for key in (
            "rolling",
            "reactive_snipe_on_own_rolls",
            "use_slash_rolls",
            "auto_free_claim",
            "auto_mk_enabled",
            "auto_dk_enabled",
            "auto_p_enabled",
            "immediate_kakera_click",
            "collect_purple_kakera",
        ):
            self.assertTrue(preset[key], key)
        self.assertFalse(preset["snipe_mode"])
        self.assertFalse(preset["kakera_reaction_snipe_mode"])
        self.assertTrue(preset["series_snipe_only_self_rolls"])
        preset["channel_id"] = 123456789
        self.assertEqual(validate_preset(preset, resolved_token=["token"]), [])

    def test_recommended_profiles_do_not_share_mutable_values(self):
        first = build_recommended_preset()
        second = build_recommended_preset()
        first["wishlist"].append("Example")
        self.assertEqual(second["wishlist"], [])

    def test_auto_dk_trigger_power_is_editable_and_validated(self):
        preset = build_recommended_preset()
        self.assertEqual(preset["auto_dk_min_power"], 0)
        self.assertIn('"auto_dk_min_power"', self.editor)
        preset["channel_id"] = 123456789
        preset["auto_dk_min_power"] = preset["max_dk_power"] + 1
        self.assertIn(
            "auto_dk_min_power cannot exceed max_dk_power.",
            validate_preset(preset, resolved_token=["token"]),
        )

    def test_quick_setup_separates_own_rolls_from_external_actions(self):
        self.assertIn("Kakera on your own automated rolls is collected automatically.", self.editor)
        self.assertIn("Collect Kakera from other players", self.editor)
        self.assertIn("Claim wishlist matches from other players", self.editor)
        self.assertIn('data["series_snipe_only_self_rolls"] = not data["snipe_mode"]', self.editor)
        self.assertIn('data["auto_free_claim"] = data["reactive_snipe_on_own_rolls"]', self.editor)
        quick_block = self.editor[self.editor.index("def build_quick_setup"):self.editor.index("def show_editor_mode")]
        self.assertNotIn('_quick_entry(inner, "additional_tokens"', quick_block)

    def test_additional_tokens_have_a_visibility_toggle(self):
        self.assertIn('if key in {"token", "additional_tokens"}', self.editor)
        self.assertIn('"Additional Tokens (Optional, comma-separated; securely encrypted)"', self.editor)
        self.assertIn('"Show Token"', self.editor)

    def test_quick_setup_includes_every_supported_x_roll_pool(self):
        self.assertIn(
            '("wa", "ha", "ma", "wx", "hx", "mx", "wg", "hg", "mg")',
            self.editor,
        )

    def test_quick_setup_preserves_hidden_additional_tokens(self):
        class FakeSecretStore:
            def get_tokens(self, _name, _legacy):
                return ["old-primary", "second", "third"]

        editor = SimpleNamespace(
            current_preset="Profile",
            presets={"Profile": {"token": ""}},
            quick_widgets={},
            secret_store=FakeSecretStore(),
            _quick_value=lambda key: "new-primary" if key == "token" else "",
        )
        self.assertEqual(
            PresetEditor._quick_token_values(editor),
            ["new-primary", "second", "third"],
        )

    def test_save_and_start_uses_the_active_editor_mode(self):
        self.assertIn("def save_active_preset", self.editor)
        self.assertIn("self.save_active_preset(show_success=False, require_runtime=True)", self.editor)
        self.assertIn("def save_active_preset(self, show_success=True, require_runtime=False)", self.editor)
        self.assertIn('"▶ Save & Start Bot"', self.editor)

    def test_preset_list_keeps_its_selection_when_focus_moves(self):
        self.assertIn("exportselection=False", self.editor)
        self.assertIn("selectmode=tk.BROWSE", self.editor)

    def test_preset_loading_batches_chip_updates_and_reuses_emoji_cards(self):
        self.assertIn("def replace(self, value):", self.editor)
        self.assertIn("widget.replace(serialized)", self.editor)
        refresh_source = self.editor[
            self.editor.index("def refresh(self):"):
            self.editor.index("# --- Constants ---")
        ]
        self.assertIn("if set(self.cards) != set(display_options):", refresh_source)
        self.assertIn("card.pack_forget()", refresh_source)

    def test_gui_source_contains_no_turkish_user_interface_text(self):
        self.assertIsNone(re.search(r"[ğüşöçıİĞÜŞÖÇ]", self.editor))

    def test_documented_windows_flow_matches_the_new_primary_action(self):
        self.assertIn("Quick Setup", self.readme)
        self.assertIn("Save & Start Bot", self.readme)
        self.assertNotIn("hit **▶ Launch Bot**", self.readme)

    def test_quick_setup_uses_the_active_scroll_target_and_dark_combobox_style(self):
        self.assertIn('"Quick.TCombobox"', self.editor)
        self.assertIn('scroll_target = self.quick_canvas if self.editor_mode == "quick" else self.canvas', self.editor)
        self.assertIn('style="Quick.TCombobox"', self.editor)

    def test_mode_switch_updates_flat_button_hover_and_pressed_colours(self):
        self.assertIn("def set_flat_button_colors", self.editor)
        self.assertIn("activeforeground=fg_color", self.editor)
        self.assertIn("button._flat_normal_bg", self.editor)
        self.assertIn("self.set_flat_button_colors(self.quick_mode_btn", self.editor)
        self.assertIn("self.set_flat_button_colors(self.advanced_mode_btn", self.editor)

    def test_mode_switch_resolves_active_form_before_reloading_both_views(self):
        mode_source = self.editor[
            self.editor.index("def show_editor_mode"):
            self.editor.index("def _quick_value")
        ]
        self.assertIn("if not self.prompt_unsaved_changes():", mode_source)
        self.assertIn("self.select_preset(self.current_preset)", mode_source)

    def test_context_emoji_overrides_document_regular_selection_inheritance(self):
        self.assertIn("unchecked inherits Kakera Emojis", self.editor)
        self.assertIn('data.get("kakera_emojis", DEFAULT_KAKERA_EMOJIS)', self.editor)

    def test_oh_individual_use_mode_is_configurable(self):
        self.assertIn('"oh_use_individually": False', self.editor)
        self.assertIn('"oh_use_individually"', self.editor)
        self.assertIn("one board per use", self.editor)

    def test_sidebar_rebuild_preserves_the_current_visible_preset(self):
        class FakeListbox:
            def __init__(self):
                self.items = []
                self.selected = None

            def delete(self, _first, _last):
                self.items = []

            def insert(self, _where, name):
                self.items.append(name)

            def selection_set(self, index):
                self.selected = index

            def activate(self, _index):
                pass

            def see(self, _index):
                pass

        editor = SimpleNamespace(
            preset_listbox=FakeListbox(),
            loading_preset=False,
            current_preset="second",
        )
        PresetEditor._replace_preset_list(editor, ["first", "second", "third"])
        self.assertEqual(editor.preset_listbox.items, ["first", "second", "third"])
        self.assertEqual(editor.preset_listbox.selected, 1)
        self.assertFalse(editor.loading_preset)

    def test_preset_selection_commits_only_the_last_queued_choice(self):
        self.assertIn("self._preset_selection_generation = 0", self.editor)
        self.assertIn("self._pending_preset_selection = None", self.editor)
        self.assertIn("def _commit_preset_selection", self.editor)
        self.assertIn("generation != self._preset_selection_generation", self.editor)
        self.assertIn("self._preset_selection_in_progress = True", self.editor)
        selection_source = self.editor[
            self.editor.index("def on_preset_select"):
            self.editor.index("def select_preset")
        ]
        self.assertNotIn("after_idle", selection_source)
        self.assertIn("self._commit_preset_selection(preset_name, generation)", selection_source)

    def test_new_selection_during_unsaved_prompt_supersedes_the_old_target(self):
        class FakeListbox:
            selected = "second"

            def curselection(self):
                return (0,)

            def get(self, _index):
                return self.selected

        editor = object.__new__(PresetEditor)
        editor.preset_listbox = FakeListbox()
        editor.presets = {"first": {}, "second": {}, "third": {}}
        editor.loading_preset = False
        editor._preset_selection_generation = 0
        editor._preset_selection_in_progress = False
        editor._pending_preset_selection = None
        editor.current_preset = "first"
        loaded = []

        def select_preset(name):
            loaded.append(name)
            editor.current_preset = name

        prompt_count = [0]

        def prompt_unsaved_changes():
            prompt_count[0] += 1
            if prompt_count[0] == 1:
                editor.preset_listbox.selected = "third"
                editor.on_preset_select(None)
            return True

        editor.select_preset = select_preset
        editor.prompt_unsaved_changes = prompt_unsaved_changes
        editor.update_listbox_selection = lambda _name: None

        editor.on_preset_select(None)

        self.assertEqual(loaded, ["third"])
        self.assertEqual(editor.current_preset, "third")

    def test_clean_preset_selection_loads_synchronously(self):
        class FakeListbox:
            def curselection(self):
                return (0,)

            def get(self, _index):
                return "second"

        editor = object.__new__(PresetEditor)
        editor.preset_listbox = FakeListbox()
        editor.presets = {"first": {}, "second": {}}
        editor.loading_preset = False
        editor._preset_selection_generation = 0
        editor._preset_selection_in_progress = False
        editor._pending_preset_selection = None
        editor.current_preset = "first"
        editor.prompt_unsaved_changes = lambda: True
        editor.update_listbox_selection = lambda _name: None
        loaded = []
        editor.select_preset = lambda name: loaded.append(name)

        editor.on_preset_select(None)

        self.assertEqual(loaded, ["second"])


if __name__ == "__main__":
    unittest.main()
