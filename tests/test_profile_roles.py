"""Profiles: stable ids, renames, Main/Side roles and their migration.

All ids, names and tokens are made up.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from android.generate_schema import main as generate_schema
from mudae_core.activity_events import ActivityClassifier
from mudae_core.bot_config import apply_live_config, configure_client
from mudae_core.config import (
    account_role_errors,
    ensure_profile_ids,
    profile_id_of,
    rename_profile,
    resolve_account_roles,
    side_profiles_for,
    validate_new_profile_name,
    validate_preset,
)
from mudae_core.runtime import prepare_active_presets
from mudae_core.secrets import SecretStore


ROOT = Path(__file__).resolve().parents[1]
OPTIONS = {
    "bot_name": "MudaRemote",
    "claim_emojis": ["c"],
    "kakera_emojis": ["k"],
    "sphere_emojis": ["s"],
    "slash_available": True,
}
BASE = {"prefix": "!", "mudae_prefix": "$", "roll_command": "wa",
        "claim_interval": 180, "roll_interval": 60, "max_dk_power": 100}


def termux_env(home):
    return {"HOME": home, "PREFIX": "/data/data/com.termux/files/usr", "TERMUX_VERSION": "0.118.3"}


class ProfileIdMigrationTests(unittest.TestCase):
    def test_old_configs_get_unique_ids_and_main_account_id_becomes_a_side(self):
        presets = {
            "Main": dict(BASE),
            "Alt": dict(BASE, main_account_id="123456789012345678"),
            "Copy": dict(BASE, profile_id="pdup"),
            "Copy 2": dict(BASE, profile_id="pdup"),
        }
        self.assertTrue(ensure_profile_ids(presets))
        ids = [profile_id_of(data) for data in presets.values()]
        self.assertTrue(all(ids))
        self.assertEqual(len(set(ids)), 4)
        self.assertEqual(presets["Copy"]["profile_id"], "pdup")
        self.assertEqual(presets["Main"]["account_role"], "main")
        self.assertEqual(presets["Alt"]["account_role"], "side")
        # The legacy id keeps working: the Alt is a Side of that Discord user.
        self.assertEqual(presets["Alt"]["main_account_id"], "123456789012345678")
        info = resolve_account_roles(presets)["Alt"]
        self.assertEqual((info["role"], info["main_account_id"]), ("side", "123456789012345678"))
        for key, default in (("side_rolls_for_main", False), ("side_rolls_max_per_reset", 1),
                             ("side_claim_leftovers", False), ("side_order", 1)):
            self.assertEqual(presets["Main"][key], default)
        # A second load changes nothing.
        snapshot = json.dumps(presets, sort_keys=True)
        self.assertFalse(ensure_profile_ids(presets))
        self.assertEqual(json.dumps(presets, sort_keys=True), snapshot)

    def test_an_explicit_role_is_never_overwritten_by_migration(self):
        presets = {"Main": dict(BASE, account_role="main", main_account_id="42")}
        ensure_profile_ids(presets)
        self.assertEqual(presets["Main"]["account_role"], "main")


class RoleValidationTests(unittest.TestCase):
    def setUp(self):
        self.presets = {
            "Main": dict(BASE, profile_id="pmain", account_role="main"),
            "Alt": dict(BASE, profile_id="palt", account_role="side", main_profile_id="pmain", side_order=2),
            "Alt 2": dict(BASE, profile_id="palt2", account_role="side", main_profile_id="pmain", side_order=1),
        }

    def test_valid_roles_and_side_order(self):
        roles = resolve_account_roles(self.presets)
        self.assertEqual(roles["Main"]["role"], "main")
        self.assertEqual((roles["Alt"]["role"], roles["Alt"]["main"]), ("side", "Main"))
        self.assertEqual(side_profiles_for(self.presets, "Main"), ["Alt 2", "Alt"])
        for name, data in self.presets.items():
            self.assertEqual(validate_preset(data, require_runtime=False), [], name)
            self.assertEqual(account_role_errors(self.presets, name), [], name)

    def test_side_cannot_point_at_itself_or_at_another_side(self):
        self.presets["Alt"]["main_profile_id"] = "palt"
        self.assertTrue(any("own main" in error for error in validate_preset(self.presets["Alt"], require_runtime=False)))
        self.assertEqual(resolve_account_roles(self.presets)["Alt"]["role"], "ordinary")
        self.assertTrue(account_role_errors(self.presets, "Alt"))

        self.presets["Alt"]["main_profile_id"] = "palt2"
        info = resolve_account_roles(self.presets)["Alt"]
        self.assertEqual(info["role"], "ordinary")
        self.assertIn("itself a side account", info["reason"])
        self.assertTrue(account_role_errors(self.presets, "Alt"))

    def test_missing_main_runs_as_ordinary_account_with_a_reason_but_saves(self):
        del self.presets["Main"]
        info = resolve_account_roles(self.presets)["Alt"]
        self.assertEqual(info["role"], "ordinary")
        self.assertIn("no longer exists", info["reason"])
        self.assertEqual(account_role_errors(self.presets, "Alt"), [])
        self.presets["Alt"]["main_profile_id"] = ""
        self.assertIn("No main profile", resolve_account_roles(self.presets)["Alt"]["reason"])

    def test_option_ranges(self):
        for changes, fragment in (
            ({"account_role": "boss"}, "Account role"),
            ({"side_rolls_max_per_reset": 0}, "Max side accounts"),
            ({"side_rolls_max_per_reset": 11}, "Max side accounts"),
            ({"side_rolls_max_per_reset": True}, "Max side accounts"),
            ({"side_order": 0}, "Side order"),
            ({"main_profile_id": "bad id!"}, "Main profile"),
        ):
            with self.subTest(changes=changes):
                errors = validate_preset(dict(BASE, **changes), require_runtime=False)
                self.assertTrue(any(fragment in error for error in errors), errors)
        self.assertEqual(validate_preset(dict(BASE, side_rolls_max_per_reset=10), require_runtime=False), [])


class RenameTests(unittest.TestCase):
    def setUp(self):
        self.presets = {
            "First": dict(BASE, profile_id="pfirst"),
            "Main": dict(BASE, profile_id="pmain", account_role="main", scheduled_roll_times=["12:00"]),
            "Alt": dict(BASE, profile_id="palt", account_role="side", main_profile_id="pmain"),
        }

    def test_rename_keeps_order_id_settings_and_references(self):
        main_data = self.presets["Main"]
        clean = rename_profile(self.presets, "Main", "  الحساب الرئيسي  ")
        self.assertEqual(clean, "الحساب الرئيسي")
        self.assertEqual(list(self.presets), ["First", "الحساب الرئيسي", "Alt"])
        self.assertIs(self.presets[clean], main_data)
        self.assertEqual(self.presets[clean]["profile_id"], "pmain")
        self.assertEqual(self.presets[clean]["scheduled_roll_times"], ["12:00"])
        # The Side still points at the same Main; only the label changed.
        self.assertEqual(resolve_account_roles(self.presets)["Alt"]["main"], clean)
        self.assertEqual(side_profiles_for(self.presets, clean), ["Alt"])

    def test_names_are_trimmed_unique_ignoring_case_and_1_to_40_characters(self):
        with self.assertRaises(ValueError):
            rename_profile(self.presets, "Main", "alt")
        with self.assertRaises(ValueError):
            rename_profile(self.presets, "Main", "   ")
        with self.assertRaises(ValueError):
            rename_profile(self.presets, "Main", "x" * 41)
        with self.assertRaises(KeyError):
            rename_profile(self.presets, "Nope", "Other")
        self.assertEqual(rename_profile(self.presets, "Main", "x" * 40), "x" * 40)
        # Changing only the case of its own name is allowed.
        self.assertEqual(rename_profile(self.presets, "Alt", "ALT"), "ALT")
        self.assertEqual(validate_new_profile_name(self.presets, "first")[1].split(" (")[0],
                         "A profile named 'First' already exists")

    def test_runtime_instance_ids_follow_the_stable_id_not_the_name(self):
        from mudae_core.bot_runtime import BotInstance, RuntimeManager

        manager = RuntimeManager()
        with mock.patch.object(BotInstance, "start"):
            before = manager.start_instances_from_preset("Main", self.presets["Main"], {"tokens": ["t1", "t2"]})
        self.assertEqual(before, ["pmain-1", "pmain-2"])
        self.assertEqual(manager._instances["pmain-2"].preset_data["_account_index"], 2)

    def test_prepared_accounts_carry_their_index(self):
        prepared = prepare_active_presets(["Main"], {"Main": dict(self.presets["Main"], tokens=["a", "b"])})
        self.assertEqual([data["_account_index"] for _, data in prepared], [1, 2])
        self.assertEqual([data["profile_id"] for _, data in prepared], ["pmain", "pmain"])


class StableTokenKeyTests(unittest.TestCase):
    def test_tokens_move_from_the_name_key_to_the_id_key_and_survive_a_rename(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as home:
            with mock.patch.dict(os.environ, termux_env(home), clear=False):
                store = SecretStore(project)
                store.set_tokens("Main", ["tok-1", "tok-2"])
                data = dict(BASE, profile_id="pmain")
                self.assertEqual(store.get_profile_tokens("Main", data), ["tok-1", "tok-2"])
                self.assertTrue(store.migrate_profile_tokens("Main", data))
                self.assertFalse(store.migrate_profile_tokens("Main", data))
                self.assertEqual(store.get_tokens("Main"), [])
                self.assertEqual(store.get_tokens("profile:pmain"), ["tok-1", "tok-2"])

                presets = {"Main": data}
                new_name = rename_profile(presets, "Main", "Renamed")
                self.assertEqual(store.get_profile_tokens(new_name, presets[new_name]), ["tok-1", "tok-2"])

                store.set_profile_tokens(new_name, presets[new_name], ["tok-3"])
                self.assertEqual(store.get_profile_tokens(new_name, presets[new_name]), ["tok-3"])
                store.delete_profile_tokens(new_name, presets[new_name])
                self.assertEqual(store.get_profile_tokens(new_name, presets[new_name]), [])

    def test_profiles_without_an_id_keep_the_old_name_key(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as home:
            with mock.patch.dict(os.environ, termux_env(home), clear=False):
                store = SecretStore(project)
                store.set_profile_tokens("Legacy", {}, ["old"])
                self.assertEqual(store.get_tokens("Legacy"), ["old"])
                self.assertEqual(SecretStore.profile_key("Legacy", {}), "Legacy")

    def test_environment_override_by_name_still_wins(self):
        with tempfile.TemporaryDirectory() as project:
            store = SecretStore(project)
            with mock.patch.dict(os.environ, {"MUDAREMOTE_TOKEN_MAIN": "from-env"}, clear=False):
                self.assertEqual(store.get_profile_tokens("Main", {"profile_id": "pmain"}), ["from-env"])


class ClientAndSchemaTests(unittest.TestCase):
    def test_client_gets_role_settings_clamped_and_live_reloadable(self):
        client = SimpleNamespace(command_prefix="old", hourly_tu_refresh=False)
        configure_client(client, "Alt", {
            "channel_id": 1, "profile_id": "palt", "account_role": "side", "main_profile_id": "pmain",
            "side_order": "3", "side_rolls_max_per_reset": 99, "_account_index": 2,
        }, **OPTIONS)
        self.assertEqual((client.profile_id, client.account_role, client.main_profile_id,
                          client.side_order, client.side_rolls_max_per_reset, client.account_index),
                         ("palt", "side", "pmain", 3, 10, 2))
        self.assertFalse(client.side_rolls_for_main)
        self.assertFalse(client.side_claim_leftovers)
        # A1: the reload drops the legacy «side of another profile» setting, but
        # this account is the profile's 2nd token, so it stays an alt (side) by
        # position; only the saved role and the option change.
        changed = apply_live_config(client, {"channel_id": 1, "account_role": "main",
                                             "side_rolls_for_main": True}, **OPTIONS)
        self.assertTrue({"stored_account_role", "side_rolls_for_main"} <= changed)
        self.assertEqual((client.account_role, client.stored_account_role, client.side_rolls_for_main, client.side_order),
                         ("side", "main", True, 1))
        # The primary token of such a profile does become a main again.
        first = SimpleNamespace(command_prefix="old", hourly_tu_refresh=False)
        configure_client(first, "Alt", {"channel_id": 1, "account_role": "side", "main_profile_id": "pmain",
                                        "_account_index": 1}, **OPTIONS)
        self.assertEqual(first.account_role, "side")
        changed = apply_live_config(first, {"channel_id": 1, "account_role": "main"}, **OPTIONS)
        self.assertIn("account_role", changed)
        self.assertEqual(first.account_role, "main")

    def test_android_schema_has_the_role_section_and_profile_picker(self):
        with tempfile.TemporaryDirectory() as directory:
            generate_schema(str(ROOT), directory)
            fields = json.loads(Path(directory, "android_schema.json").read_text(encoding="utf-8"))["fields"]
        expected = {
            "account_role": ("main", "text"), "main_profile_id": ("", "text"), "side_order": (1, "number"),
            "side_rolls_for_main": (False, "boolean"), "side_rolls_max_per_reset": (1, "number"),
            "side_claim_leftovers": (False, "boolean"), "main_account_id": ("", "text"),
        }
        for key, (default, kind) in expected.items():
            self.assertEqual((fields[key]["default"], fields[key]["type"]), (default, kind), key)
            self.assertEqual(fields[key]["section"], "Main & alts", key)  # A1: one «Main & alts» group
        self.assertEqual(set(fields["account_role"]["choices"]), {"main", "side"})
        self.assertEqual(fields["main_profile_id"]["picker"], "profile")
        self.assertEqual(fields["side_rolls_for_main"]["label"], "Alts roll for the main when it finds nothing")
        # The old separate-profile fields are kept but marked and ordered last.
        for key in ("account_role", "main_profile_id", "side_order"):
            self.assertTrue(fields[key]["label"].startswith("Advanced: separate profiles"), key)
            self.assertGreater(fields[key]["order"], fields["perk10_daily_cap"]["order"], key)
        self.assertNotIn("profile_id", fields)


class ActivityLineTests(unittest.TestCase):
    def test_handoff_lines_become_side_roll_events(self):
        classifier = ActivityClassifier()
        ask = classifier.classify("CLAIM", "Main found nothing — asking side ⁨حساب جانبي⁩ to roll")
        self.assertEqual(ask[0][0], "side_roll")
        self.assertEqual(ask[0][1]["side"], "حساب جانبي")
        claimed = classifier.classify("CLAIM", "Main claimed ⁨Rem⁩ from ⁨Alt⁩'s roll")
        self.assertEqual(claimed[0][1]["character"], "Rem")
        self.assertEqual(claimed[0][1]["side"], "Alt")

    def test_the_patterns_match_the_wording_in_the_code(self):
        coordinator = (ROOT / "mudae_core" / "coordinator.py").read_text(encoding="utf-8")
        bot = (ROOT / "mudae_bot.py").read_text(encoding="utf-8")
        self.assertIn('"Main found nothing — asking side {} to roll".format(_isolate(candidate.name))', coordinator)
        self.assertIn('f"Main claimed \\u2068{card}\\u2069 from \\u2068{handoff.side_name}\\u2069\'s roll"', bot)


if __name__ == "__main__":
    unittest.main()
