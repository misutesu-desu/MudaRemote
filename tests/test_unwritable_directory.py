"""A folder the user cannot write to (an install in Program Files) must fail fast, never hang."""

import os
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from mudae_core import config
from mudae_core.secrets import SecretStore, SecretStoreError


class UnwritableDirectoryTest(unittest.TestCase):
    def test_a_denied_write_fails_on_the_first_attempt(self):
        # tempfile.mkstemp retries a refused file creation thousands of times on Windows.
        calls = []

        def refuse(*args, **kwargs):
            calls.append(args)
            raise PermissionError(13, "Permission denied")

        with tempfile.TemporaryDirectory() as folder, mock.patch.object(config.os, "open", side_effect=refuse):
            with self.assertRaises(PermissionError):
                config.atomic_write_json(os.path.join(folder, "presets.json"), {"a": 1})
        self.assertEqual(len(calls), 1)

    def test_a_failed_write_leaves_no_temporary_file_behind(self):
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "presets.json")
            with mock.patch.object(config.os, "replace", side_effect=PermissionError(13, "denied")):
                with self.assertRaises(PermissionError):
                    config.atomic_write_json(target, {"a": 1})
            self.assertEqual(os.listdir(folder), [])

    def test_a_normal_write_still_replaces_the_file_atomically(self):
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "presets.json")
            config.atomic_write_json(target, {"a": 1})
            config.atomic_write_json(target, {"a": 2})
            self.assertEqual(config.load_json(target), {"a": 2})
            self.assertEqual(os.listdir(folder), ["presets.json"])

    def test_the_token_store_reports_an_unwritable_folder_as_a_store_error(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(config.os, "open", side_effect=PermissionError(13, "denied")), \
                mock.patch.object(SecretStore, "_dpapi_protect", return_value="x"):
            with self.assertRaises(SecretStoreError):
                SecretStore(folder)._set_dpapi_secret("Main", "abc.def.ghi")      # the Windows store, on any OS

    @unittest.skipUnless(os.name == "nt", "folder permissions are checked with icacls on Windows")
    def test_a_folder_denied_by_permissions_answers_quickly(self):
        user = os.environ.get("USERNAME")
        with tempfile.TemporaryDirectory() as folder:
            subprocess.check_call(["icacls", folder, "/deny", "{}:(OI)(CI)(W,DC)".format(user)],
                                  stdout=subprocess.DEVNULL)
            try:
                started = time.time()
                with self.assertRaises(PermissionError):
                    config.atomic_write_json(os.path.join(folder, "presets.json"), {"a": 1})
                self.assertLess(time.time() - started, 5)
            finally:
                subprocess.call(["icacls", folder, "/remove:d", user], stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
