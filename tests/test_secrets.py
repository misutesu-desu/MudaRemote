import os
import tempfile
import unittest
from unittest import mock

from mudae_core.config import load_json
from mudae_core.secrets import SecretStore


class SecretStoreTests(unittest.TestCase):
    def test_environment_override_uses_sanitized_preset_name(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SecretStore(directory)
            with mock.patch.dict(os.environ, {"MUDAREMOTE_TOKEN_MAIN_ACCOUNT": "from-env"}, clear=False):
                self.assertEqual(store.get_token("Main Account", "legacy"), "from-env")

    def test_termux_store_persists_outside_the_project_without_keyring(self):
        with tempfile.TemporaryDirectory() as project_directory, tempfile.TemporaryDirectory() as termux_home:
            environment = {
                "HOME": termux_home,
                "PREFIX": "/data/data/com.termux/files/usr",
                "TERMUX_VERSION": "0.118.3",
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                store = SecretStore(project_directory)
                store.set_token("MAIN", "termux-token")

                self.assertEqual(store.get_token("MAIN"), "termux-token")
                self.assertTrue(store.termux_path.startswith(termux_home))
                self.assertFalse(store.termux_path.startswith(project_directory))
                self.assertEqual(load_json(store.termux_path), {"MAIN": "termux-token"})

    def test_termux_store_locks_directory_and_file_permissions(self):
        with tempfile.TemporaryDirectory() as project_directory, tempfile.TemporaryDirectory() as termux_home:
            environment = {
                "HOME": termux_home,
                "PREFIX": "/data/data/com.termux/files/usr",
                "TERMUX_VERSION": "0.118.3",
            }
            with mock.patch.dict(os.environ, environment, clear=False), mock.patch("mudae_core.secrets.os.chmod") as chmod:
                store = SecretStore(project_directory)
                store.set_token("MAIN", "termux-token")

                chmod.assert_any_call(os.path.dirname(store.termux_path), 0o700)
                chmod.assert_any_call(store.termux_path, 0o600)

    def test_termux_store_preserves_other_presets_and_removes_empty_file(self):
        with tempfile.TemporaryDirectory() as project_directory, tempfile.TemporaryDirectory() as termux_home:
            environment = {
                "HOME": termux_home,
                "PREFIX": "/data/data/com.termux/files/usr",
                "TERMUX_VERSION": "0.118.3",
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                store = SecretStore(project_directory)
                store.set_token("MAIN", "main-token")
                store.set_token("ALT", "alt-token")
                store.delete_token("MAIN")

                self.assertEqual(store.get_token("MAIN"), "")
                self.assertEqual(store.get_token("ALT"), "alt-token")
                self.assertEqual(load_json(store.termux_path), {"ALT": "alt-token"})

                store.delete_token("ALT")
                self.assertFalse(os.path.exists(store.termux_path))

    def test_termux_store_round_trips_multiple_tokens_and_legacy_single_token(self):
        with tempfile.TemporaryDirectory() as project_directory, tempfile.TemporaryDirectory() as termux_home:
            environment = {
                "HOME": termux_home,
                "PREFIX": "/data/data/com.termux/files/usr",
                "TERMUX_VERSION": "0.118.3",
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                store = SecretStore(project_directory)
                store.set_tokens("MULTI", ["first", "second", "first"])
                store.set_token("LEGACY", "single")

                self.assertEqual(store.get_tokens("MULTI"), ["first", "second"])
                self.assertEqual(store.get_token("MULTI"), "first")
                self.assertEqual(store.get_tokens("LEGACY"), ["single"])


if __name__ == "__main__":
    unittest.main()
