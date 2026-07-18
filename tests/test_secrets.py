import os
import tempfile
import unittest
from unittest import mock

from mudae_core.secrets import SecretStore


class SecretStoreTests(unittest.TestCase):
    def test_environment_override_uses_sanitized_preset_name(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SecretStore(directory)
            with mock.patch.dict(os.environ, {"MUDAREMOTE_TOKEN_MAIN_ACCOUNT": "from-env"}, clear=False):
                self.assertEqual(store.get_token("Main Account", "legacy"), "from-env")


if __name__ == "__main__":
    unittest.main()
