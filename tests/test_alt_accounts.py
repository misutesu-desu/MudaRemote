"""A1: the alts are the extra entries of one profile's «Account Tokens» list.

The primary token is the main, every extra token is an alt of it. Settings
live once in the profile and act per account by role. All tokens, ids and
names below are made up.
"""

import ast
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mudae_core.account_roles import (
    NO_ALTS_HINT,
    IdleNote,
    account_label,
    account_label_for,
    account_role,
    account_role_for,
    alt_count,
    alt_number,
    labelled_message,
    perk10_enabled_for,
    profile_chip_text,
    roll_batch_blocker,
    side_kind_for,
)
from mudae_core.account_state import AccountStateStore
from mudae_core.bot_config import apply_live_config, configure_client
from mudae_core.coordinator import SideRollCoordinator
from mudae_core.harem_give import HaremGiver, HaremGiveSettings
from mudae_core.kakera_give import GiveSettings, KakeraGiver
from mudae_core.runtime import prepare_active_presets
from mudae_core.sphere_give import PERK10_OFF_REASON, SphereGiver, SphereGiveSettings

ROOT = Path(__file__).resolve().parents[1]
OPTIONS = {"bot_name": "MudaRemote", "claim_emojis": ["c"], "kakera_emojis": ["k"],
           "sphere_emojis": ["s"], "slash_available": True}
PROFILE = {"profile_id": "pfarm", "channel_id": 111, "token": "tok-main",
           "tokens": ["tok-main", "tok-alt-a", "tok-alt-b"], "account_role": "main",
           "auto_give_kakera": True, "give_kakera_threshold": 100, "auto_give_spheres": True,
           "auto_give_harem": True, "auto_perk10": True}


def clients_for(profile, name="Farm"):
    """What the runtime builds: one configured client per token of the profile."""
    clients = []
    for account_name, data in prepare_active_presets([name], {name: profile}):
        client = SimpleNamespace(command_prefix="!", hourly_tu_refresh=False, preset_name=account_name)
        configure_client(client, account_name, data, **OPTIONS)
        clients.append(client)
    return clients


class Handle:
    """The coordinator's view of a running account (the real one is mudae_bot._AccountLink)."""

    def __init__(self, client, key, user_id):
        self.client = client
        self.key = key
        self.name = client.preset_name
        self.user_id = user_id
        self.channel_id = 111
        self.main_account_id = getattr(client, "main_account_id", "")

    profile_id = property(lambda self: self.client.profile_id)
    account_index = property(lambda self: self.client.account_index)
    role = property(lambda self: account_role_for(self.client))
    side_kind = property(lambda self: side_kind_for(self.client))
    main_profile_id = property(lambda self: self.client.main_profile_id)
    side_order = property(lambda self: self.client.side_order)


def store():
    directory = tempfile.mkdtemp()
    return AccountStateStore(os.path.join(directory, "state.json"))


async def no_send(*_args, **_kwargs):
    raise AssertionError("nothing may be sent in these checks")


def giver(cls, **extra):
    return cls(key="k", store=store(), send=no_send, wait=no_send, log=lambda *_: None, **extra)


class RoleByPositionTests(unittest.TestCase):
    def test_first_token_is_the_main_and_extra_tokens_are_alts_in_order(self):
        main, alt_a, alt_b = clients_for(PROFILE)
        self.assertEqual([account_role_for(c) for c in (main, alt_a, alt_b)], ["main", "side", "side"])
        self.assertEqual([side_kind_for(c) for c in (main, alt_a, alt_b)], [None, "alt", "alt"])
        self.assertEqual([c.side_order for c in (alt_a, alt_b)], [1, 2])
        self.assertEqual([c.account_count for c in (main, alt_a, alt_b)], [3, 3, 3])
        self.assertEqual([account_label_for(c) for c in (main, alt_a, alt_b)], ["main", "alt 1", "alt 2"])
        self.assertEqual((alt_number(1), alt_number(3)), (0, 2))

    def test_the_stored_role_no_longer_decides_and_a_reload_keeps_the_position(self):
        # Exactly the owner's 6.0.0 profile: saved as «main», yet its extra tokens are alts.
        main, alt_a, _alt_b = clients_for(dict(PROFILE, account_role="main"))
        self.assertEqual(account_role_for(alt_a), "side")
        changed = apply_live_config(alt_a, {"channel_id": 111, "auto_give_kakera": False}, **OPTIONS)
        self.assertIn("auto_give_kakera", changed)
        self.assertEqual((account_role_for(alt_a), alt_a.account_index, alt_a.side_order), ("side", 2, 1))
        apply_live_config(main, {"channel_id": 111, "account_role": "side"}, **OPTIONS)
        self.assertEqual(account_role_for(main), "main")  # «side» without a main profile id is ignored

    def test_a_single_token_profile_is_a_plain_main_without_label(self):
        (only,) = clients_for({"profile_id": "psolo", "channel_id": 1, "token": "tok-solo"}, "Solo")
        self.assertEqual((account_role_for(only), account_label_for(only)), ("main", ""))
        self.assertEqual(account_role(1), "main")
        self.assertEqual(account_label(1, 1), "")

    def test_alt_count_reads_both_token_shapes_and_the_chip(self):
        self.assertEqual(alt_count("a", ["a", "b", "c"]), 2)  # desktop: [primary, alts…]
        self.assertEqual(alt_count("a", ["b", "c"]), 2)       # Android: extra tokens only
        self.assertEqual(alt_count("a", (), "b, c\nd"), 3)    # the editor's text field
        self.assertEqual(alt_count("a", ["a"]), 0)
        self.assertEqual((profile_chip_text(1), profile_chip_text(3), profile_chip_text(0)),
                         ("Main + 1 alt", "Main + 3 alts", ""))


class MainDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = SideRollCoordinator()
        main, alt_a, alt_b = clients_for(PROFILE)
        other_main, = clients_for({"profile_id": "pother", "channel_id": 111, "token": "tok-other"}, "Other")
        self.main = Handle(main, "farm#1", 5001)
        self.alt_a = Handle(alt_a, "farm#2", 5002)
        self.alt_b = Handle(alt_b, "farm#3", 5003)
        self.other = Handle(other_main, "other#1", 7001)
        for handle in (self.other, self.alt_b, self.alt_a, self.main):
            self.coordinator.register(handle)

    def test_an_alt_finds_the_primary_token_of_its_own_profile(self):
        self.assertIs(self.coordinator.resolve_main(self.alt_a), self.main)
        self.assertIs(self.coordinator.resolve_main(self.alt_b), self.main)
        self.assertIsNone(self.coordinator.resolve_main(self.main))
        self.assertIsNone(self.coordinator.resolve_main(self.other))
        self.assertEqual(self.coordinator.sides_for(self.main), [self.alt_a, self.alt_b])
        self.assertEqual(self.coordinator.sides_for(self.other), [])  # no alts: nothing to ask

    def test_the_main_id_is_taken_from_the_running_main_and_the_pasted_id_is_the_fallback(self):
        scope = self._receiver_scope(self.alt_a, pasted="")
        self.assertEqual(scope["give_receiver_id"](), "5001")
        scope = self._receiver_scope(self.alt_a, pasted="4242")
        self.assertEqual(scope["give_receiver_id"](), "5001")  # the running main wins…
        self.assertEqual(scope["logged"][0][1], "WARN")         # …and the mismatch is said once
        scope["give_receiver_id"]()
        self.assertEqual(len(scope["logged"]), 1)
        self.coordinator.unregister(self.main)
        self.assertEqual(self._receiver_scope(self.alt_a, pasted="4242")["give_receiver_id"](), "4242")
        self.assertEqual(self._receiver_scope(self.alt_a, pasted="")["give_receiver_id"](), "")

    def _receiver_scope(self, handle, pasted):
        source = (ROOT / "mudae_bot.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        wanted = [node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name in ("effective_main_account_id", "give_receiver_id")]
        logged = []
        client = handle.client
        client.main_account_id = pasted
        client._account_link = handle
        client.__dict__.pop("_main_id_mismatch_logged", None)
        scope = {"client": client, "_side_roll_coordinator": self.coordinator, "side_kind_for": side_kind_for,
                 "preset_name": "Farm #2", "logged": logged,
                 "BotLogger": SimpleNamespace(log=lambda message, name, level="INFO", *_: logged.append((message, level)))}
        exec(compile(ast.Module(body=wanted, type_ignores=[]), "<receiver>", "exec"), scope)
        return scope


class SameSettingsPerRoleTests(unittest.TestCase):
    """One profile's settings: the side features act on the alts, never on the main."""

    def setUp(self):
        self.main, self.alt, _ = clients_for(PROFILE)

    def test_kakera_give_runs_on_the_alt_only(self):
        settings = GiveSettings.from_preset(PROFILE)
        kakera = giver(KakeraGiver)
        self.assertIn("only a side account", kakera.blocker(
            settings, role=account_role_for(self.main), own_id="5001", main_id="5001", total=500))
        self.assertIsNone(kakera.blocker(
            settings, role=account_role_for(self.alt), own_id="5002", main_id="5001", total=500))

    def test_sphere_give_runs_on_the_alt_only(self):
        spheres = giver(SphereGiver)
        main_settings = SphereGiveSettings.from_preset(dict(PROFILE, auto_perk10=perk10_enabled_for(self.main)))
        alt_settings = SphereGiveSettings.from_preset(dict(PROFILE, auto_perk10=perk10_enabled_for(self.alt)))
        self.assertIn("only a side account", spheres.blocker(
            main_settings, role=account_role_for(self.main), own_id="5001", main_id="5001", stock=10))
        # auto_perk10 is on for the profile, but it is the MAIN's switch: the alt still gives.
        self.assertIsNone(spheres.blocker(
            alt_settings, role=account_role_for(self.alt), own_id="5002", main_id="5001", stock=10))

    def test_harem_give_runs_on_the_alt_only_and_needs_the_running_main(self):
        settings = HaremGiveSettings.from_preset(PROFILE)
        harem = giver(HaremGiver, click=no_send)
        partner = SimpleNamespace(user_id=5001, key="farm#1")
        self.assertIn("only a side account", harem.blocker(
            settings, role=account_role_for(self.main), own_id="5001", main_id="5001", partner=partner))
        self.assertIsNone(harem.blocker(
            settings, role=account_role_for(self.alt), own_id="5002", main_id="5001", partner=partner))
        self.assertIn("not running", harem.blocker(
            settings, role=account_role_for(self.alt), own_id="5002", main_id="5001", partner=None))


class SidePerk10Tests(unittest.TestCase):
    def test_perk10_is_the_mains_and_alts_join_only_with_side_perk10(self):
        main, alt, _ = clients_for(PROFILE)
        self.assertEqual((perk10_enabled_for(main), perk10_enabled_for(alt)), (True, False))
        main, alt, _ = clients_for(dict(PROFILE, side_perk10=True))
        self.assertEqual((perk10_enabled_for(main), perk10_enabled_for(alt)), (True, True))
        main, alt, _ = clients_for(dict(PROFILE, auto_perk10=False, side_perk10=True))
        self.assertEqual((perk10_enabled_for(main), perk10_enabled_for(alt)), (False, False))

    def test_an_alt_that_upgrades_keeps_its_spheres(self):
        _main, alt, _ = clients_for(dict(PROFILE, side_perk10=True))
        settings = SphereGiveSettings.from_preset(dict(PROFILE, auto_perk10=perk10_enabled_for(alt)))
        self.assertEqual(giver(SphereGiver).blocker(
            settings, role="side", own_id="5002", main_id="5001", stock=10), PERK10_OFF_REASON)


class LegacySeparateProfileTests(unittest.TestCase):
    def test_a_profile_saved_as_side_of_another_profile_still_works(self):
        coordinator = SideRollCoordinator()
        main, = clients_for({"profile_id": "pmain", "channel_id": 111, "token": "tok-m"}, "Main")
        side, = clients_for({"profile_id": "pside", "channel_id": 111, "token": "tok-s",
                             "account_role": "side", "main_profile_id": "pmain", "side_order": 4,
                             "auto_perk10": True}, "Side")
        self.assertEqual((account_role_for(side), side_kind_for(side), side.side_order), ("side", "legacy", 4))
        self.assertEqual(account_label_for(side), "")
        self.assertTrue(perk10_enabled_for(side))  # as in 6.0.0: its own switch
        main_handle, side_handle = Handle(main, "m#1", 1), Handle(side, "s#1", 2)
        coordinator.register(main_handle)
        coordinator.register(side_handle)
        self.assertIs(coordinator.resolve_main(side_handle), main_handle)


class IdleReasonTests(unittest.TestCase):
    def test_the_reason_is_said_once_per_change(self):
        note = IdleNote()
        self.assertEqual(note.update("paused"), "waiting — paused")
        self.assertIsNone(note.update("paused"))
        self.assertEqual(note.update("key limit reached (pausing 1h)"), "waiting — key limit reached (pausing 1h)")
        self.assertIsNone(note.update(None))
        self.assertEqual(note.update("paused"), "waiting — paused")
        self.assertEqual(labelled_message("main", "waiting — paused"), "main: waiting — paused")
        self.assertEqual(labelled_message("alt 1", "[CLAIM] got it"), "[CLAIM] alt 1: got it")
        self.assertEqual(labelled_message("", "plain"), "plain")

    def test_only_the_accounts_own_state_blocks_its_rolls(self):
        self.assertIsNone(roll_batch_blocker())
        self.assertEqual(roll_batch_blocker(giving_kakera=True), "a kakera give to the main is in progress")
        self.assertEqual(roll_batch_blocker(paused=True, giving_spheres=True), "paused")


class UiTextTests(unittest.TestCase):
    def test_the_disabling_rule_is_gone_and_the_hint_is_shared(self):
        kotlin = (ROOT / "android/app/src/main/java/com/mudaremote/android/MainActivity.kt").read_text(encoding="utf-8")
        editor = (ROOT / "mudae_preset_editor.py").read_text(encoding="utf-8")
        for text in (kotlin, editor):
            self.assertNotIn("this profile is a Main account, so", text)
        self.assertIn('const val NO_ALTS_HINT = "{}"'.format(NO_ALTS_HINT), kotlin)
        self.assertIn('"Main & alts"', kotlin)
        self.assertIn('"Alts give kakera to the main"', editor)
        self.assertIn('"side_perk10", "Let side accounts upgrade too (turns off their automatic sphere giving)"', editor)


if __name__ == "__main__":
    unittest.main()
