import hashlib
import os
import tempfile
import unittest
from unittest import mock

from mudae_core.updater import UpdateError, apply_update, format_update_changelog


class _Response:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self, files):
        self.files = files
        self.timeouts = []

    def get(self, url, timeout=None):
        self.timeouts.append(timeout)
        return _Response(self.files[url])


def _entry(path, url, content, checksum=None):
    return {
        "path": path,
        "url": url,
        "sha256": checksum or hashlib.sha256(content).hexdigest(),
    }


class UpdaterTests(unittest.TestCase):
    def test_structured_changelog_is_formatted_for_confirmation(self):
        changelog = format_update_changelog({
            "changelog": {
                "Improvements": ["First change", "Second change"],
                "Safety": ["Presets stay untouched"],
            },
        })
        self.assertIn("Improvements\n- First change\n- Second change", changelog)
        self.assertIn("Safety\n- Presets stay untouched", changelog)

    def test_frozen_download_uses_bounded_startup_timeouts(self):
        content = b"fake executable"
        session = _Session({"exe": content})
        manifest = {
            "version": "5.0.0",
            "exe_download_url": "exe",
            "exe_sha256": hashlib.sha256(content).hexdigest(),
        }
        with tempfile.TemporaryDirectory() as directory:
            executable = os.path.join(directory, "MudaRemote.exe")
            with mock.patch("mudae_core.updater.subprocess.Popen"):
                result = apply_update(
                    session, manifest, "4.0.0", directory,
                    frozen=True, executable=executable,
                )
        self.assertEqual(result, "frozen")
        self.assertEqual(session.timeouts, [(5.0, 20.0)])

    def test_manifest_updates_all_modules_as_one_verified_set(self):
        files = {
            "bot": b"VALUE = 'new'\n",
            "editor": b"VALUE = 'new'\n",
            "core": b"VALUE = 'new'\n",
        }
        manifest = {
            "version": "4.10.0",
            "source_files": [
                _entry("mudae_bot.py", "bot", files["bot"]),
                _entry("mudae_preset_editor.py", "editor", files["editor"]),
                _entry("mudae_core/__init__.py", "core", files["core"]),
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            result = apply_update(_Session(files), manifest, "4.9.9", directory)
            self.assertEqual(result, "source")
            with open(os.path.join(directory, "mudae_core", "__init__.py"), "rb") as handle:
                self.assertEqual(handle.read(), files["core"])

    def test_bad_checksum_does_not_replace_existing_files(self):
        files = {"bot": b"VALUE = 'new'\n", "editor": b"X=1\n", "core": b"X=1\n"}
        manifest = {
            "version": "5.0.0",
            "source_files": [
                _entry("mudae_bot.py", "bot", files["bot"], checksum="0" * 64),
                _entry("mudae_preset_editor.py", "editor", files["editor"]),
                _entry("mudae_core/__init__.py", "core", files["core"]),
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            bot_path = os.path.join(directory, "mudae_bot.py")
            with open(bot_path, "wb") as handle:
                handle.write(b"VALUE = 'old'\n")
            with self.assertRaises(UpdateError):
                apply_update(_Session(files), manifest, "4.0.0", directory)
            with open(bot_path, "rb") as handle:
                self.assertEqual(handle.read(), b"VALUE = 'old'\n")

    def test_manifest_cannot_replace_user_presets(self):
        files = {
            "bot": b"VALUE = 'new'\n",
            "editor": b"VALUE = 'new'\n",
            "core": b"VALUE = 'new'\n",
            "presets": b"{}\n",
        }
        manifest = {
            "version": "5.0.0",
            "source_files": [
                _entry("mudae_bot.py", "bot", files["bot"]),
                _entry("mudae_preset_editor.py", "editor", files["editor"]),
                _entry("mudae_core/__init__.py", "core", files["core"]),
                _entry("presets.json", "presets", files["presets"]),
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            presets_path = os.path.join(directory, "presets.json")
            with open(presets_path, "wb") as handle:
                handle.write(b'{"Saved": {"rolling": true}}\n')
            with self.assertRaises(UpdateError):
                apply_update(_Session(files), manifest, "4.0.0", directory)
            with open(presets_path, "rb") as handle:
                self.assertEqual(handle.read(), b'{"Saved": {"rolling": true}}\n')


if __name__ == "__main__":
    unittest.main()
