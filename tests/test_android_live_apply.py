import json
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.test_android_updater import android_bridge


class AndroidLiveApplyTests(unittest.TestCase):
    def setUp(self):
        self.worker = mock.Mock()
        self.worker.is_alive.return_value = True
        self.engine = SimpleNamespace(apply_runtime_preset=mock.Mock(return_value={
            "status": "queued", "account_count": 1, "restart_required": ["channel_id"],
        }))
        patch = mock.patch.multiple(
            android_bridge, _running=True, _stopping=False,
            _runtime_module=self.engine, _profile_threads={"profile": [self.worker]},
            _active_profiles={"profile": {"min_kakera": 100}},
            _active_tokens={"profile": ["existing-secret"]}, _threads=[self.worker],
        )
        patch.start()
        self.addCleanup(patch.stop)

    def test_apply_uses_existing_workers_and_does_not_stage_or_replace_tokens(self):
        with mock.patch.object(android_bridge, "_start_profile_workers") as start, \
                mock.patch.object(android_bridge, "stop") as stop, \
                mock.patch.object(android_bridge, "_stage_runtime") as stage:
            response = json.loads(android_bridge.apply_profile("profile", json.dumps({
                "min_kakera": 300, "token": "new-secret", "tokens": ["new-secret"],
                "additional_tokens": "new-secret",
            })))
        self.assertEqual(response["status"], "queued")
        self.assertEqual(response["restart_required"], ["channel_id"])
        self.engine.apply_runtime_preset.assert_called_once_with("profile", {"min_kakera": 300})
        self.assertEqual(android_bridge._active_profiles["profile"], {"min_kakera": 300})
        self.assertEqual(android_bridge._active_tokens["profile"], ["existing-secret"])
        self.assertIs(android_bridge._profile_threads["profile"][0], self.worker)
        start.assert_not_called()
        stop.assert_not_called()
        stage.assert_not_called()

    def test_invalid_inactive_and_old_engines_keep_active_snapshot(self):
        for payload in ("{", "[]"):
            self.assertEqual(json.loads(android_bridge.apply_profile("profile", payload))["status"], "invalid")
        self.assertEqual(json.loads(android_bridge.apply_profile("missing", "{}"))["status"], "inactive")
        self.engine.apply_runtime_preset.assert_not_called()
        with mock.patch.object(android_bridge, "_runtime_module", SimpleNamespace()):
            response = json.loads(android_bridge.apply_profile("profile", "{}"))
        self.assertEqual(response["status"], "invalid")
        self.assertEqual(android_bridge._active_profiles["profile"], {"min_kakera": 100})

    def test_stopping_does_not_queue_settings(self):
        with mock.patch.object(android_bridge, "_stopping", True):
            response = json.loads(android_bridge.apply_profile("profile", "{}"))
        self.assertEqual(response["status"], "inactive")
        self.engine.apply_runtime_preset.assert_not_called()


if __name__ == "__main__":
    unittest.main()
