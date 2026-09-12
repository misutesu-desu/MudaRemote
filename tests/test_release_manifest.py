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
        with open(os.path.join(PROJECT_ROOT, "mudae_core", "versioning.py"), "r", encoding="utf-8") as handle:
            match = re.search(r'^CURRENT_VERSION = "([^"]+)"', handle.read(), re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), version)

        import mudae_bot
        self.assertEqual(mudae_bot.CURRENT_VERSION, version)

        from mudae_core.versioning import CURRENT_VERSION as VERSIONING_VERSION
        from mudae_core import CURRENT_VERSION as CORE_VERSION
        self.assertEqual(VERSIONING_VERSION, version)
        self.assertEqual(CORE_VERSION, version)
    def test_manifest_includes_changelog_for_update_confirmation(self):
        with open(os.path.join(PROJECT_ROOT, "version.json"), "r", encoding="utf-8") as handle:
            changelog = json.load(handle).get("changelog")
        self.assertTrue(changelog)

    def test_executable_manifest_checksum_is_well_formed(self):
        with open(os.path.join(PROJECT_ROOT, "version.json"), "r", encoding="utf-8") as handle:
            expected = json.load(handle)["exe_sha256"]
        self.assertTrue(
            expected == "pending-github-actions" or re.fullmatch(r"[0-9a-f]{64}", expected),
            expected,
        )

    def test_release_description_matches_discord_update_log(self):
        with open(os.path.join(PROJECT_ROOT, "version.json"), encoding="utf-8") as handle:
            manifest = json.load(handle)
        notes_path = os.path.join(PROJECT_ROOT, "packaging", "release-notes-v{}.md".format(manifest["version"]))
        with open(notes_path, encoding="utf-8") as handle:
            self.assertEqual(handle.read().strip(), manifest["changelog"].strip())


if __name__ == "__main__":
    unittest.main()
