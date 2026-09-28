import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from mudae_core.preset_reload import LivePresetReload, validate_live_preset
from mudae_core.runtime import prepare_active_presets


BASE = {"channel_id": "1234", "prefix": "!", "mudae_prefix": "$", "rolling": True}


class PresetReloadTests(unittest.IsolatedAsyncioTestCase):
    def make_reload(self, **kwargs):
        self.client = SimpleNamespace(_live_preset_ready=True)
        self.apply = mock.Mock(return_value={"wishlist"})
        self.log = mock.Mock()
        return LivePresetReload(self.client, BASE, self.apply, self.log, **kwargs)

    async def test_saved_file_applies_once_and_invalid_save_preserves_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "presets.json"
            reload = self.make_reload(path=path, name="profile")
            path.write_text(json.dumps({"profile": {**BASE, "wishlist": ["Rem"]}}))
            await reload.poll_once()
            await reload.poll_once()
            self.apply.assert_called_once()
            self.assertEqual(self.apply.call_args.args[0]["wishlist"], ["Rem"])
            path.write_text("{")
            await reload.poll_once()
            self.apply.assert_called_once()
            path.write_text(json.dumps({"profile": {**BASE, "roll_speed": -1}}))
            await reload.poll_once()
            self.apply.assert_called_once()
            path.write_text(json.dumps({"profile": {**BASE, "wishlist": ["Asuna"]}}))
            await reload.poll_once()
            self.assertEqual(self.apply.call_count, 2)

    async def test_transactions_defer_and_latest_save_wins(self):
        reload = self.make_reload()
        self.client.is_actively_rolling = True
        reload.offer({**BASE, "min_kakera": 200})
        await reload.poll_once()
        self.apply.assert_not_called()
        reload.offer({**BASE, "min_kakera": 300})
        self.client.is_actively_rolling = False
        self.client._sphere_game_lock = asyncio.Lock()
        await self.client._sphere_game_lock.acquire()
        await reload.poll_once()
        self.apply.assert_not_called()
        self.client._sphere_game_lock.release()
        self.client.loot_automation = SimpleNamespace(_queue=object())
        await reload.poll_once()
        self.apply.assert_not_called()
        self.client.loot_automation._queue = None
        await reload.poll_once()
        self.assertEqual(self.apply.call_args.args[0]["min_kakera"], 300)

    async def test_request_outcomes_keep_correlation_through_all_states(self):
        outcomes = []
        reload = self.make_reload(observer=outcomes.append)
        self.client.is_claiming = True
        reload.offer({**BASE, "min_kakera": 200}, 1)
        await reload.poll_once()
        await reload.poll_once()
        self.assertEqual([(item["request_id"], item["status"]) for item in outcomes], [(1, "deferred")])

        reload.offer({**BASE, "min_kakera": 300}, 2)
        self.client.is_claiming = False
        await reload.poll_once()
        self.assertEqual([(item["request_id"], item["status"]) for item in outcomes[-2:]],
                         [(1, "superseded"), (2, "applied")])

        reload.offer({**BASE, "min_kakera": 300, "channel_id": "5678"}, 3)
        await reload.poll_once()
        self.assertEqual((outcomes[-1]["request_id"], outcomes[-1]["status"]), (3, "restart_required"))

        reload.offer({**BASE, "roll_speed": -1}, 4)
        await reload.poll_once()
        self.assertEqual((outcomes[-1]["request_id"], outcomes[-1]["status"]), (4, "rejected"))

        self.client.is_claiming = True
        reload.offer({**BASE, "min_kakera": 400}, 5)
        reload.cancel_pending()
        self.assertEqual((outcomes[-1]["request_id"], outcomes[-1]["status"]), (5, "cancelled"))
        self.assertEqual(reload.desired_preset, reload.active_preset)

    async def test_identical_pending_request_and_desktop_poll_settle_original(self):
        outcomes = []
        reload = self.make_reload(observer=outcomes.append)
        self.client.is_claiming = True
        value = {**BASE, "min_kakera": 200}
        reload.offer(value, 11)
        await reload.poll_once()
        reload.offer(value, 12)
        self.assertIn((11, "superseded"), [(o["request_id"], o["status"]) for o in outcomes])
        reload.offer(value)  # Desktop file poll does not take ownership of a host request.
        self.assertEqual(reload.pending_request_id, 12)
        reload.cancel_pending()
        self.assertIn((12, "cancelled"), [(o["request_id"], o["status"]) for o in outcomes])
        self.assertEqual(reload.desired_preset, reload.active_preset)

    async def test_observer_exception_does_not_block_apply(self):
        reload = self.make_reload(observer=mock.Mock(side_effect=RuntimeError("observer failed")))
        reload.offer({**BASE, "min_kakera": 200}, 7)
        await reload.poll_once()
        self.apply.assert_called_once()
        self.assertTrue(any("observer error" in call.args[0] for call in self.log.call_args_list))

    async def test_restart_fields_retained_but_hot_settings_apply(self):
        reload = self.make_reload()
        reload.offer({**BASE, "channel_id": "5678", "rolling": False,
                      "roll_interval": 120, "wishlist": ["Rem"], "token": "secret"})
        await reload.poll_once()
        effective = self.apply.call_args.args[0]
        self.assertEqual(effective["channel_id"], "1234")
        self.assertTrue(effective["rolling"])
        self.assertEqual(effective["roll_interval"], 60)
        self.assertEqual(effective["wishlist"], ["Rem"])
        self.assertNotIn("token", effective)
        self.assertIn("channel_id, roll_interval, rolling", self.log.call_args.args[0])

    async def test_missing_deleted_or_other_profile_never_replaces_live_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "presets.json"
            reload = self.make_reload(path=path, name="profile")
            await reload.poll_once()
            path.write_text(json.dumps({"another": {**BASE, "wishlist": ["Rem"]}}))
            await reload.poll_once()
            self.apply.assert_not_called()

    def test_multi_account_preserves_source_name_including_suffix(self):
        prepared = prepare_active_presets(["profile #2"], {"profile #2": {**BASE, "tokens": ["a", "b"]}})
        self.assertEqual([name for name, _ in prepared], ["profile #2", "profile #2 #2"])
        self.assertEqual([data["_source_preset_name"] for _, data in prepared], ["profile #2"] * 2)

    def test_invalid_container_is_rejected(self):
        for data in (None, [], {**BASE, "wishlist": 42}):
            self.assertTrue(validate_live_preset(data))


class ProductionReloadTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self):
        import mudae_bot
        from tests.test_snipe_startup import _Bot
        client = _Bot()
        client.run = mock.Mock()
        mudae_bot._mobile_runtime_stop_event.clear()
        with mock.patch.object(mudae_bot.commands, "Bot", return_value=client):
            mudae_bot.run_bot("profile #2", {**BASE, "token": "dummy", "_source_preset_name": "profile"})
        client._preset_reload.path = None
        client._live_preset_ready = True
        client._mobile_owned_loop = asyncio.get_running_loop()
        return client

    async def test_engine_queues_on_matching_account_loop_and_keeps_runtime_state(self):
        import mudae_bot
        client = self.make_client()
        client.rolls_left = 8
        owner = client.normal_roll_action_owner
        ledger = client.kakera_power_ledger
        with mock.patch.object(mudae_bot, "_active_clients", [client]):
            result = mudae_bot.apply_runtime_preset("profile", {**BASE, "min_kakera": 350, "wishlist": ["REM"]})
        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["account_count"], 1)
        await asyncio.sleep(0)
        await client._preset_reload.poll_once()
        self.assertEqual(client.wishlist, {"rem"})
        self.assertEqual(client.min_kakera, 350)
        self.assertEqual(client.current_min_kakera_for_roll_claim, 350)
        self.assertEqual(client.rolls_left, 8)
        self.assertIs(client.normal_roll_action_owner, owner)
        self.assertIs(client.kakera_power_ledger, ledger)

    async def test_invalid_or_unrelated_update_never_queues(self):
        import mudae_bot
        client = self.make_client()
        with mock.patch.object(mudae_bot, "_active_clients", [client]):
            invalid = mudae_bot.apply_runtime_preset("profile", {**BASE, "roll_speed": -1})
            unrelated = mudae_bot.apply_runtime_preset("other", BASE)
        self.assertEqual(invalid["status"], "invalid")
        self.assertEqual(unrelated["status"], "inactive")
        self.assertIsNone(client._preset_reload.pending)


if __name__ == "__main__":
    unittest.main()
