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
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
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
        for p in list(sys.path):
            if "android-test-" in p:
                sys.path.remove(p)
        for m in list(sys.modules.keys()):
            if m == "mudae_bot" or m.startswith("mudae_core"):
                sys.modules.pop(m, None)
        import mudae_core.updater
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

        def mock_download_manifest(*args, **kwargs):
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
        code_dir = android_bridge._get_python_code_dir(self.temp_dir)
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


    def test_check_and_apply_update_includes_apk_update_metadata(self):
        dummy_files = {
            path: "# module content for {}\n".format(path).encode("utf-8")
            for path in sorted(REQUIRED_SOURCE_PATHS)
        }
        manifest = {
            "version": "9.9.9",
            "apk_version": "1.3.0",
            "apk_url": "https://github.com/misutesu-desu/MudaRemote/releases/download/v1.3.0/Mudaremote.apk",
            "apk_version_code": 15,
            "source_files": [
                {
                    "path": path,
                    "url": "https://example.com/" + path,
                    "sha256": hashlib.sha256(dummy_files[path]).hexdigest(),
                }
                for path in sorted(REQUIRED_SOURCE_PATHS)
            ],
        }
        with mock.patch("android_bridge._download_manifest", return_value=manifest), \
             mock.patch("android_bridge._download_file", side_effect=lambda url, **kw: dummy_files[url.replace("https://example.com/", "")]):
            result = json.loads(android_bridge.check_and_apply_update(self.temp_dir, force=True))
        self.assertEqual(result["status"], "updated")
        self.assertIsNotNone(result.get("apk_update"))
        self.assertEqual(result["apk_update"]["version"], "1.3.0")
        self.assertEqual(result["apk_update"]["version_code"], 15)

    def test_check_and_apply_update_rejects_missing_required_files(self):
        manifest = {
            "version": "9.9.9",
            "source_files": [
                {
                    "path": "mudae_bot.py",
                    "url": "https://example.com/mudae_bot.py",
                    "sha256": hashlib.sha256(b"content").hexdigest(),
                }
            ],
        }
        with mock.patch("android_bridge._download_manifest", return_value=manifest), \
             mock.patch("android_bridge._download_file", return_value=b"content"):
            result = json.loads(android_bridge.check_and_apply_update(self.temp_dir, force=True))
        self.assertEqual(result["status"], "error")
        self.assertIn("incomplete", result["error"].lower())
    def test_get_and_set_update_channel(self):
        # Default channel
        ch = android_bridge.get_update_channel(self.temp_dir)
        self.assertIn(ch, {"beta", "main"})

        # Toggle to main/stable
        res = json.loads(android_bridge.set_update_channel(self.temp_dir, "main"))
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["channel"], "main")
        self.assertEqual(android_bridge.get_update_channel(self.temp_dir), "main")

        # Toggle back to beta
        res = json.loads(android_bridge.set_update_channel(self.temp_dir, "beta"))
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["channel"], "beta")
        self.assertEqual(android_bridge.get_update_channel(self.temp_dir), "beta")

    def test_fetch_available_versions_reports_channel_and_honest_errors(self):
        fake_releases = [
            {
                "version": "4.9.0", "tag": "v4.9.0", "name": "v4.9.0",
                "prerelease": False, "is_apk": False, "apk_url": None,
            },
        ]
        with mock.patch("mudae_core.versioning.fetch_available_releases", return_value=fake_releases) as fetch:
            envelope = json.loads(android_bridge.fetch_available_versions("android", "main"))
        self.assertEqual(envelope["status"], "ok")
        self.assertEqual(envelope["releases"], fake_releases)
        self.assertEqual(fetch.call_args.kwargs["platform"], "android")
        self.assertEqual(fetch.call_args.kwargs["channel"], "main")

        with mock.patch("mudae_core.versioning.fetch_available_releases", side_effect=OSError("network down")):
            failed = json.loads(android_bridge.fetch_available_versions("android", "beta"))
        self.assertEqual(failed["status"], "error")
        self.assertIn("network down", failed["error"])
        self.assertNotIn("releases", failed)


        dummy_manifest = {
            "version": "4.8.10",
            "source_files": [
                {
                    "path": path,
                    "url": "https://example.com/" + path,
                    "sha256": hashlib.sha256("# test\n".encode("utf-8")).hexdigest(),
                }
                for path in sorted(REQUIRED_SOURCE_PATHS)
            ],
        }
        with mock.patch("mudae_core.versioning.fetch_manifest_for_version", return_value=dummy_manifest), \
             mock.patch("android_bridge._download_file", return_value="# test\n".encode("utf-8")):
            res_json = android_bridge.install_specific_version(self.temp_dir, "v4.8.10")
            res = json.loads(res_json)
            self.assertEqual(res["status"], "updated")
            self.assertEqual(res["version"], "4.8.10")

        apk_route = json.loads(android_bridge.install_specific_version(self.temp_dir, "android-pre9"))
        self.assertEqual(apk_route["status"], "error")
        self.assertIn("APK", apk_route["error"])
    def test_reset_to_bundled_code_blocks_when_running(self):
        with mock.patch("android_bridge._running", True):
            result = json.loads(android_bridge.reset_to_bundled_code(self.temp_dir))
            self.assertEqual(result["status"], "error")
            self.assertIn("Cannot reset", result["error"])

    def test_load_mudae_bot_reloads_when_installed_version_differs(self):
        code_dir = os.path.join(self.temp_dir, "python_code")
        os.makedirs(code_dir, exist_ok=True)
        bot_file = os.path.join(code_dir, "mudae_bot.py")
        with open(bot_file, "w") as f:
            f.write("CURRENT_VERSION = '2.0.0'\n")
        with open(os.path.join(code_dir, ".version"), "w") as f:
            f.write("2.0.0")

        fake_old_mod = mock.MagicMock()
        fake_old_mod.__file__ = bot_file
        fake_old_mod.CURRENT_VERSION = "1.0.0"  # Stale loaded module version

        with mock.patch.dict("sys.modules", {"mudae_bot": fake_old_mod}):
            with mock.patch("android_bridge._evict_mudae_modules") as mock_evict:
                # Should detect version difference and call evict
                android_bridge._load_mudae_bot(self.temp_dir)
                mock_evict.assert_called_once()

    def test_apk_update_included_when_python_is_current(self):
        manifest = {
            "version": "1.0.0",  # older or equal
            "apk_version": "1.4.0",
            "apk_url": "https://github.com/misutesu-desu/MudaRemote/releases/download/v1.4.0/Mudaremote.apk",
            "apk_version_code": 16,
        }
        with mock.patch("android_bridge._download_manifest", return_value=manifest):
            result = json.loads(android_bridge.check_and_apply_update(self.temp_dir, force=False))
        self.assertEqual(result["status"], "current")
        self.assertIsNotNone(result.get("apk_update"))
        self.assertEqual(result["apk_update"]["version"], "1.4.0")

    def test_load_mudae_bot_cleans_poisoned_version_on_import_failure(self):
        gen_dir = os.path.join(self.temp_dir, "python_code", "generations", "bad_gen")
        os.makedirs(gen_dir, exist_ok=True)
        # Corrupted mudae_bot that cannot be imported
        with open(os.path.join(gen_dir, "mudae_bot.py"), "w") as f:
            f.write("raise RuntimeError('Fatal syntax/import error in updated code')\n")
        android_bridge._write_selection(self.temp_dir, "bad_gen", "9.9.9")

        # When loaded, it should catch the failure, remove selection, and fall back to bundled
        android_bridge._load_mudae_bot(self.temp_dir)
        self.assertIsNone(android_bridge._read_selection(self.temp_dir))
        info = json.loads(android_bridge.get_runtime_info(self.temp_dir))
        self.assertFalse(info["is_updated"])
        self.assertEqual(info["installed_version"], android_bridge.get_bundled_version())

    def test_generation_isolation_during_active_runtime(self):
        dummy_files = {
            path: "# module content for {}\n".format(path).encode("utf-8")
            for path in sorted(REQUIRED_SOURCE_PATHS)
        }
        manifest = {
            "version": "10.0.0",
            "source_files": [
                {
                    "path": path,
                    "url": "https://example.com/" + path,
                    "sha256": hashlib.sha256(dummy_files[path]).hexdigest(),
                }
                for path in sorted(REQUIRED_SOURCE_PATHS)
            ],
        }
        # Pin active generation
        android_bridge._active_generation_dir = os.path.join(self.temp_dir, "python_code", "generations", "pinned_gen")
        os.makedirs(android_bridge._active_generation_dir, exist_ok=True)
        with open(os.path.join(android_bridge._active_generation_dir, "mudae_bot.py"), "w") as f:
            f.write("# pinned generation\n")

        with mock.patch("android_bridge._running", True), \
             mock.patch("android_bridge._download_manifest", return_value=manifest), \
             mock.patch("android_bridge._download_file", side_effect=lambda url, **kw: dummy_files[url.replace("https://example.com/", "")]):
            res = json.loads(android_bridge.check_and_apply_update(self.temp_dir, force=True))

        self.assertEqual(res["status"], "staged")
        # Active generation must NOT have been overwritten
        with open(os.path.join(android_bridge._active_generation_dir, "mudae_bot.py"), "r") as f:
            self.assertEqual(f.read(), "# pinned generation\n")
        # Selection points to the new generation
        sel = android_bridge._read_selection(self.temp_dir)
        self.assertIsNotNone(sel)
        self.assertEqual(sel["version"], "10.0.0")
        self.assertNotEqual(sel["selected_generation"], "pinned_gen")
        android_bridge._active_generation_dir = None

    def test_download_manifest_raises_on_discovery_error(self):
        with mock.patch("mudae_core.updater.discover_update_manifest", return_value={"status": "error", "error": "Simulated primary outage"}):
            with self.assertRaisesRegex(RuntimeError, "Simulated primary outage"):
                android_bridge._download_manifest()
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

    def test_mobile_shutdown_force_stops_an_unresponsive_client_loop(self):
        class UnresponsiveClient:
            def __init__(self, loop):
                self.loop = loop
                self.close_started = threading.Event()

            def is_closed(self):
                return False

            async def close(self):
                self.close_started.set()
                await asyncio.Event().wait()

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever)
        loop_thread.start()
        client = UnresponsiveClient(loop)
        mudae_bot.reset_mobile_runtime()
        with mudae_bot._active_clients_lock:
            mudae_bot._active_clients.append(client)

        mudae_bot.shutdown_mobile_runtime(timeout_seconds=0.05)

        self.assertTrue(client.close_started.wait(1.0))
        loop_thread.join(1.0)
        self.assertFalse(loop_thread.is_alive())

        with mudae_bot._active_clients_lock:
            if client in mudae_bot._active_clients:
                mudae_bot._active_clients.remove(client)
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

    def test_component_ack_timeout_is_treated_as_ambiguous(self):
        error = mudae_bot.discord.InvalidData("Did not receive a response from Discord")
        self.assertTrue(mudae_bot.is_ambiguous_component_interaction_error(error))
        self.assertFalse(mudae_bot.is_ambiguous_component_interaction_error(RuntimeError(str(error))))

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
