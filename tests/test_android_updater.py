import hashlib
import json
import os
import sys
import tempfile
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


if __name__ == "__main__":
    unittest.main()
