import hashlib
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

# Ensure android python directory is in path for testing
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANDROID_PYTHON_DIR = os.path.join(PROJECT_ROOT, "android", "app", "src", "main", "python")
if ANDROID_PYTHON_DIR not in sys.path:
    sys.path.insert(0, ANDROID_PYTHON_DIR)

if os.path.isfile(os.path.join(ANDROID_PYTHON_DIR, "android_bridge.py")):
    import android_bridge
else:
    android_bridge = None
import mudae_bot
from mudae_core.updater import REQUIRED_SOURCE_PATHS


class _MockResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error {}".format(self.status_code))

    def json(self):
        return json.loads(self.content.decode("utf-8"))


@unittest.skipIf(android_bridge is None, "unreleased Android bridge is not included in this checkout")
class AndroidUpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="android-test-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_installed_version_defaults_to_bundled(self):
        info_json = android_bridge.get_runtime_info(self.temp_dir)
        info = json.loads(info_json)
        self.assertIn("current_version", info)
        self.assertIn("bundled_version", info)
        self.assertFalse(info["is_updated"])

    def test_check_and_apply_update_downloads_verifies_and_activates(self):
        dummy_files = {
            path: "# module content for {}\n".format(path).encode("utf-8")
            for path in sorted(REQUIRED_SOURCE_PATHS)
        }
        manifest = {
            "version": "9.9.9",
            "changelog": {"Improvements": ["Android self-updater test"]},
            "source_files": [
                {
                    "path": path,
                    "url": "https://example.com/" + path,
                    "sha256": hashlib.sha256(dummy_files[path]).hexdigest(),
                }
                for path in sorted(REQUIRED_SOURCE_PATHS)
            ],
        }

        def mock_download_manifest(timeout_seconds=8.0):
            return manifest

        def mock_download_file(url, timeout_seconds=15.0):
            path = url.replace("https://example.com/", "")
            return dummy_files[path]

        with mock.patch("android_bridge._download_manifest", side_effect=mock_download_manifest), \
             mock.patch("android_bridge._download_file", side_effect=mock_download_file):
            result_json = android_bridge.check_and_apply_update(self.temp_dir, force=True)
            result = json.loads(result_json)

        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["version"], "9.9.9")

        # Verify files were staged and written
        code_dir = os.path.join(self.temp_dir, "python_code")
        self.assertTrue(os.path.isfile(os.path.join(code_dir, "mudae_bot.py")))
        self.assertTrue(os.path.isfile(os.path.join(code_dir, ".version")))
        with open(os.path.join(code_dir, ".version"), "r", encoding="utf-8") as vh:
            self.assertEqual(vh.read().strip(), "9.9.9")

        # Verify runtime info now reports is_updated = True
        info = json.loads(android_bridge.get_runtime_info(self.temp_dir))
        self.assertTrue(info["is_updated"])
        self.assertEqual(info["current_version"], "9.9.9")

    def test_check_and_apply_update_rejects_checksum_mismatch(self):
        manifest = {
            "version": "9.9.9",
            "source_files": [
                {
                    "path": "mudae_bot.py",
                    "url": "https://example.com/mudae_bot.py",
                    "sha256": "0" * 64,  # Intentionally invalid hash
                }
            ],
        }

        with mock.patch("android_bridge._download_manifest", return_value=manifest), \
             mock.patch("android_bridge._download_file", return_value=b"corrupted content"):
            result_json = android_bridge.check_and_apply_update(self.temp_dir, force=True)
            result = json.loads(result_json)

        self.assertEqual(result["status"], "error")
        self.assertIn("Checksum mismatch", result["error"])

    def test_reset_to_bundled_code_removes_updates(self):
        code_dir = os.path.join(self.temp_dir, "python_code")
        os.makedirs(code_dir, exist_ok=True)
        with open(os.path.join(code_dir, ".version"), "w") as f:
            f.write("8.8.8")
        with open(os.path.join(code_dir, "mudae_bot.py"), "w") as f:
            f.write("# custom")

        res_json = android_bridge.reset_to_bundled_code(self.temp_dir)
        res = json.loads(res_json)
        self.assertEqual(res["status"], "reset")
        self.assertFalse(os.path.exists(code_dir))

    def test_mudae_bot_mobile_hooks_and_run_cli(self):
        self.assertTrue(hasattr(mudae_bot, "shutdown_mobile_runtime"))
        self.assertTrue(hasattr(mudae_bot, "reset_mobile_runtime"))
        self.assertTrue(hasattr(mudae_bot, "run_cli"))
        mudae_bot.reset_mobile_runtime()
        mudae_bot.shutdown_mobile_runtime()
        mudae_bot.reset_mobile_runtime()


@unittest.skipIf(android_bridge is None, "unreleased Android bridge is not included in this checkout")
class AndroidRuntimeLifecycleTests(unittest.TestCase):
    class FakeRuntime:
        def __init__(self):
            self.presets = {}
            self.release_workers = threading.Event()
            self.stop_requested = threading.Event()
            self.hold_shutdown = False
            self.workers = []
            self.start_indexes = []

        def reset_mobile_runtime(self):
            self.release_workers.clear()
            self.stop_requested.clear()

        def shutdown_mobile_runtime(self, _timeout_seconds=0):
            self.stop_requested.set()
            if not self.hold_shutdown:
                self.release_workers.set()

        def prepare_active_presets(self, names, presets, start_index=0):
            self.start_indexes.append(start_index)
            prepared = []
            for name in names:
                data = dict(presets.get(name, {}))
                for index, token in enumerate(data.get("tokens") or [data.get("token")], 1):
                    if token:
                        account = dict(data)
                        account["token"] = token
                        prepared.append((name if index == 1 else "{} #{}".format(name, index), account))
            return prepared

        def start_preset_thread(self, _name, _data):
            worker = threading.Thread(target=self.release_workers.wait, daemon=True)
            worker.start()
            self.workers.append(worker)
            return worker

    def setUp(self):
        self.original_cwd = os.getcwd()
        self.original_environ = dict(os.environ)
        self.temp_dir = tempfile.mkdtemp(prefix="android-runtime-test-")
        self.runtime = self.FakeRuntime()

    def tearDown(self):
        import shutil
        self.runtime.release_workers.set()
        try:
            android_bridge.stop(0.5)
        except Exception:
            pass
        mudae_bot.reset_mobile_runtime()
        android_bridge._close_log_handle()
        os.chdir(self.original_cwd)
        os.environ.clear()
        os.environ.update(self.original_environ)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _inject_fake_presets(self, runtime, _files_dir, token_overrides=None):
        runtime.presets.clear()
        for name, source in android_bridge._active_profiles.items():
            data = dict(source)
            values = android_bridge._decode_token_value((token_overrides or {}).get(name, ""))
            data["tokens"] = values
            data["token"] = values[0] if values else ""
            runtime.presets[name] = data

    def test_repeated_start_adds_new_profiles_without_duplicate_workers(self):
        patches = (
            mock.patch("android_bridge.check_and_apply_update", return_value='{"status":"up-to-date"}'),
            mock.patch("android_bridge._load_mudae_bot", return_value=self.runtime),
            mock.patch("android_bridge._inject_runtime_presets", side_effect=self._inject_fake_presets),
        )
        with patches[0], patches[1], patches[2]:
            first = json.loads(android_bridge.start(
                '{"A":{"channel_id":"1"}}',
                '{"A":"[\\"token-a1\\",\\"token-a2\\"]"}',
                self.temp_dir,
            ))
            second = json.loads(android_bridge.start(
                '{"B":{"channel_id":"2"}}',
                '{"B":"[\\"token-b\\"]"}',
                self.temp_dir,
            ))
            duplicate = json.loads(android_bridge.start(
                '{"A":{"channel_id":"1"}}',
                '{"A":"[\\"token-a\\"]"}',
                self.temp_dir,
            ))

        self.assertEqual(first["status"], "started")
        self.assertEqual(first["active_profiles"], ["A"])
        self.assertEqual(second["status"], "added")
        self.assertEqual(second["active_profiles"], ["A", "B"])
        self.assertEqual(first["account_count"], 2)
        self.assertEqual(second["account_count"], 3)
        self.assertEqual(duplicate["status"], "already-active")
        self.assertEqual(duplicate["account_count"], 3)
        self.assertEqual(len(self.runtime.workers), 3)
        self.assertEqual(self.runtime.start_indexes, [0, 2])

        stopped = json.loads(android_bridge.stop(2.0))
        self.assertEqual(stopped["status"], "stopped")
        self.assertFalse(android_bridge.is_running())
        self.assertTrue(all(not worker.is_alive() for worker in self.runtime.workers))

    def test_stop_timeout_blocks_start_until_supervisor_cleanup_then_restarts(self):
        self.runtime.hold_shutdown = True
        patches = (
            mock.patch("android_bridge.check_and_apply_update", return_value='{"status":"up-to-date"}'),
            mock.patch("android_bridge._load_mudae_bot", return_value=self.runtime),
            mock.patch("android_bridge._inject_runtime_presets", side_effect=self._inject_fake_presets),
        )
        with patches[0], patches[1], patches[2]:
            started = json.loads(android_bridge.start(
                '{"A":{"channel_id":"1"}}', '{"A":"token-a"}', self.temp_dir
            ))
            stopping = json.loads(android_bridge.stop(0.01))
            blocked = json.loads(android_bridge.start(
                '{"B":{"channel_id":"2"}}', '{"B":"token-b"}', self.temp_dir
            ))

            self.assertEqual(started["status"], "started")
            self.assertEqual(stopping["status"], "stopping")
            self.assertEqual(blocked["status"], "stopping")
            self.assertTrue(android_bridge.is_running())

            self.runtime.release_workers.set()
            deadline = time.monotonic() + 2.0
            while android_bridge.is_running() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertFalse(android_bridge.is_running())

            self.runtime.hold_shutdown = False
            restarted = json.loads(android_bridge.start(
                '{"B":{"channel_id":"2"}}', '{"B":"token-b"}', self.temp_dir
            ))
            self.assertEqual(restarted["status"], "started")
            self.assertEqual(restarted["active_profiles"], ["B"])

    def test_mobile_stop_watcher_closes_a_loop_published_after_stop(self):
        class FakeClient:
            loop = None

            def __init__(self):
                self.closed = threading.Event()

            def is_closed(self):
                return self.closed.is_set()

            async def close(self):
                self.closed.set()

        client = FakeClient()
        mudae_bot.reset_mobile_runtime()
        with mudae_bot._active_clients_lock:
            mudae_bot._active_clients.append(client)
        watcher = threading.Thread(target=mudae_bot._close_client_on_mobile_stop, args=(client,))
        watcher.start()
        mudae_bot._mobile_runtime_stop_event.set()

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever)
        loop_thread.start()
        client.loop = loop
        self.assertTrue(client.closed.wait(2.0))
        watcher.join(2.0)
        self.assertFalse(watcher.is_alive())

        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(2.0)
        loop.close()
        with mudae_bot._active_clients_lock:
            if client in mudae_bot._active_clients:
                mudae_bot._active_clients.remove(client)

        orphan = FakeClient()
        mudae_bot.reset_mobile_runtime()
        with mudae_bot._active_clients_lock:
            mudae_bot._active_clients.append(orphan)
        orphan_watcher = threading.Thread(target=mudae_bot._close_client_on_mobile_stop, args=(orphan,))
        orphan_watcher.start()
        with mudae_bot._active_clients_lock:
            mudae_bot._active_clients.remove(orphan)
        orphan_watcher.join(1.0)
        self.assertFalse(orphan_watcher.is_alive())

    def test_runtime_info_removes_legacy_plaintext_staging_file(self):
        staged_path = os.path.join(self.temp_dir, "presets.json")
        with open(staged_path, "w", encoding="utf-8") as handle:
            json.dump({"A": {"token": "legacy", "tokens": ["legacy"]}}, handle)
        android_bridge.get_runtime_info(self.temp_dir)
        self.assertFalse(os.path.exists(staged_path))

    def test_mobile_stop_signal_prevents_lifecycle_retry(self):
        mudae_bot.reset_mobile_runtime()

        def request_stop(*_args, **_kwargs):
            mudae_bot.shutdown_mobile_runtime(timeout_seconds=0)

        with mock.patch.object(mudae_bot, "validate_preset", return_value=[]), \
             mock.patch.object(mudae_bot, "run_bot", side_effect=request_stop) as run_bot:
            mudae_bot.bot_lifecycle_wrapper("A", {"token": "test-token", "channel_id": "1"})

        self.assertEqual(run_bot.call_count, 1)
        mudae_bot.reset_mobile_runtime()


if __name__ == "__main__":
    unittest.main()
