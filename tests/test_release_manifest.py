import hashlib
import json
import os
import re
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ReleaseManifestTests(unittest.TestCase):
    def test_manifest_hashes_match_source_tree(self):
        with open(os.path.join(PROJECT_ROOT, "version.json"), "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        for entry in manifest["source_files"]:
            path = os.path.join(PROJECT_ROOT, *entry["path"].split("/"))
            with open(path, "rb") as handle:
                actual = hashlib.sha256(handle.read()).hexdigest()
            self.assertEqual(actual, entry["sha256"], entry["path"])

    def test_manifest_contains_every_runtime_core_module(self):
        with open(os.path.join(PROJECT_ROOT, "version.json"), "r", encoding="utf-8") as handle:
            manifest_paths = {entry["path"] for entry in json.load(handle)["source_files"]}
        core_directory = os.path.join(PROJECT_ROOT, "mudae_core")
        expected = {
            "mudae_core/{}".format(filename)
            for filename in os.listdir(core_directory)
            if filename.endswith(".py")
        }
        self.assertTrue(expected.issubset(manifest_paths), sorted(expected - manifest_paths))

    def test_runtime_and_manifest_versions_match(self):
        with open(os.path.join(PROJECT_ROOT, "version.json"), "r", encoding="utf-8") as handle:
            version = json.load(handle)["version"]
        with open(os.path.join(PROJECT_ROOT, "mudae_bot.py"), "r", encoding="utf-8") as handle:
            match = re.search(r'^CURRENT_VERSION = "([^"]+)"', handle.read(), re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), version)

    def test_manifest_includes_changelog_for_update_confirmation(self):
        with open(os.path.join(PROJECT_ROOT, "version.json"), "r", encoding="utf-8") as handle:
            changelog = json.load(handle).get("changelog")
        self.assertTrue(changelog)

    def test_local_release_executable_matches_manifest_when_present(self):
        executable = os.path.join(PROJECT_ROOT, "MudaRemote.exe")
        if not os.path.exists(executable):
            self.skipTest("Release executable is not part of source checkouts.")
        with open(os.path.join(PROJECT_ROOT, "version.json"), "r", encoding="utf-8") as handle:
            expected = json.load(handle)["exe_sha256"]
        with open(executable, "rb") as handle:
            actual = hashlib.sha256(handle.read()).hexdigest()
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
