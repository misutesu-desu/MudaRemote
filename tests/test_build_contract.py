import json
import os
import re
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_project_file(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), "r", encoding="utf-8") as handle:
        return handle.read()


class BuildContractTests(unittest.TestCase):
    def test_release_spec_disables_upx_and_avoids_collect_all(self):
        spec = read_project_file("MudaRemote.spec")
        self.assertIn("upx=False", spec)
        self.assertNotIn("collect_all", spec)

    def test_onefile_build_uses_clean_canonical_spec(self):
        build_script = read_project_file("build.py")
        self.assertIn('args = [release_spec, "--noconfirm", "--clean"]', build_script)
        self.assertNotIn('"--collect-all=discord"', build_script)

    def test_directory_build_explicitly_disables_upx(self):
        build_script = read_project_file("build.py")
        self.assertIn('"--noupx"', build_script)

    def test_packager_versions_are_pinned(self):
        requirements = read_project_file("requirements-dev.txt")
        self.assertRegex(requirements, r"(?m)^pyinstaller==\d+\.\d+\.\d+$")
        self.assertRegex(requirements, r"(?m)^pyinstaller-hooks-contrib==\d+\.\d+$")
        self.assertRegex(requirements, r"(?m)^pillow==\d+\.\d+\.\d+$")

    def test_windows_metadata_matches_release_version(self):
        with open(os.path.join(PROJECT_ROOT, "version.json"), "r", encoding="utf-8") as handle:
            release_version = json.load(handle)["version"]
        metadata = read_project_file("packaging", "windows_version_info.txt")
        product_version = re.search(r"StringStruct\('ProductVersion', '([^']+)'\)", metadata)
        file_version = re.search(r"StringStruct\('FileVersion', '([^']+)'\)", metadata)
        self.assertIsNotNone(product_version)
        self.assertIsNotNone(file_version)
        self.assertEqual(product_version.group(1), release_version)
        self.assertEqual(file_version.group(1), release_version + ".0")

    def test_gui_update_prompt_shows_changelog_before_installing(self):
        editor = read_project_file("mudae_preset_editor.py")
        launch_start = editor.index("def launch_gui():")
        launch_end = editor.index("\ndef run_headless(", launch_start)
        launch_source = editor[launch_start:launch_end]
        self.assertIn("messagebox.askyesno", launch_source)
        self.assertIn("Changelog:", launch_source)
        self.assertIn("check_for_updates(confirm_update=confirm_update)", launch_source)


if __name__ == "__main__":
    unittest.main()
