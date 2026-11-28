import json
import hashlib
import os
import re
import tempfile
import unittest

from build import update_source_manifest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_project_file(*parts):
    with open(os.path.join(PROJECT_ROOT, *parts), "r", encoding="utf-8") as handle:
        return handle.read()


class BuildContractTests(unittest.TestCase):
    def test_source_only_manifest_refresh_preserves_executable_checksum(self):
        with tempfile.TemporaryDirectory() as root:
            manifest_path = os.path.join(root, "version.json")
            with open(os.path.join(root, "runtime.py"), "wb") as handle:
                handle.write(b"current source\n")
            with open(manifest_path, "w", encoding="utf-8") as handle:
                json.dump({"exe_sha256": "pending-github-actions", "source_files": [
                    {"path": "runtime.py", "sha256": "stale"}]}, handle)
            update_source_manifest(root)
            with open(manifest_path, encoding="utf-8") as handle:
                updated = json.load(handle)
            self.assertEqual(updated["exe_sha256"], "pending-github-actions")
            self.assertEqual(updated["source_files"][0]["sha256"],
                             hashlib.sha256(b"current source\n").hexdigest())

    def test_release_spec_disables_upx_and_avoids_collect_all(self):
        spec = read_project_file("MudaFork.spec")
        self.assertIn("upx=False", spec)
        self.assertNotIn("collect_all", spec)

    def test_onefile_build_uses_clean_canonical_spec(self):
        build_script = read_project_file("build.py")
        self.assertIn('args = [release_spec, "--noconfirm", "--clean"]', build_script)
        self.assertNotIn('"--collect-all=discord"', build_script)

    def test_release_build_can_update_the_manifest_from_the_exact_artifact(self):
        build_script = read_project_file("build.py")
        self.assertIn('manifest["exe_sha256"] = digest', build_script)
        self.assertIn('update_source_manifest(script_dir)', build_script)
        self.assertIn('entry["sha256"] = hashlib.sha256', build_script)
        self.assertIn('"--update-manifest"', build_script)

    def test_directory_build_explicitly_disables_upx(self):
        build_script = read_project_file("build.py")
        self.assertIn('"--noupx"', build_script)

    def test_packager_versions_are_pinned(self):
        requirements = read_project_file("requirements-dev.txt")
        self.assertRegex(requirements, r"(?m)^pyinstaller==\d+\.\d+\.\d+$")
        self.assertRegex(requirements, r"(?m)^pyinstaller-hooks-contrib==\d+\.\d+$")
        self.assertRegex(requirements, r"(?m)^pillow==\d+\.\d+\.\d+$")

    def test_gui_update_prompt_shows_changelog_before_installing(self):
        editor = read_project_file("mudae_preset_editor.py")
        launch_start = editor.index("def launch_gui(")
        launch_end = editor.index("\ndef run_headless(", launch_start)
        launch_source = editor[launch_start:launch_end]
        self.assertIn("messagebox.askyesno", launch_source)
        self.assertIn("Changelog:", launch_source)
        self.assertIn("check_for_updates(confirm_update=confirm_update)", launch_source)

    def test_android_release_requires_signing_and_verifies_stable_signer(self):
        workflow = read_project_file(".github", "workflows", "android-release.yml")
        required_step = workflow.index("- name: Require and restore release signing configuration")
        build_step = workflow.index("- name: Build ux APK")
        verify_step = workflow.index("- name: Verify stable APK signer continuity")
        artifact_upload = workflow.index("uses: actions/upload-artifact@v4")
        publish_step = workflow.index("- name: Publish Android asset")

        self.assertLess(required_step, build_step)
        self.assertLess(build_step, verify_step)
        self.assertLess(verify_step, artifact_upload)
        self.assertLess(artifact_upload, publish_step)
        for secret in (
            "ANDROID_KEYSTORE_B64",
            "ANDROID_KS_STORE_PASSWORD",
            "ANDROID_KS_ALIAS",
            "ANDROID_KS_KEY_PASSWORD",
        ):
            self.assertIn(f": \"${{{secret}:?", workflow)
        self.assertIn("keytool -list -keystore mudafork-release.jks", workflow)
        self.assertIn('verify --verbose --print-certs "$APK_NAME"', workflow)
        self.assertNotIn("aefcfd68eae4fcddf789a654b90c4818fa128aca9e52bceb2767b39ff6587839", workflow)
        self.assertIn("MudaFork-${VERSION}.apk", workflow)
        self.assertNotIn("falling back to debug signing", workflow)

    def test_fork_points_every_update_and_release_url_at_the_fork(self):
        import glob
        owner = "YoRu72/MudaPersonalFork"
        checked = ["version.json", "mudae_bot.py", "mudae_preset_editor.py"]
        checked += [os.path.relpath(p, PROJECT_ROOT) for p in glob.glob(os.path.join(PROJECT_ROOT, "mudae_core", "*.py"))]
        checked += ["packaging/publish_stable_manifest.py", "android/app/src/main/python/android_bridge.py"]
        checked += [os.path.relpath(p, PROJECT_ROOT) for p in glob.glob(os.path.join(PROJECT_ROOT, ".github", "workflows", "*.yml"))]
        for relative in checked:
            text = read_project_file(*relative.split("/"))
            self.assertNotIn("misutesu", text, relative)
        self.assertIn(owner, read_project_file("mudae_core", "versioning.py"))
        self.assertFalse(os.path.exists(os.path.join(PROJECT_ROOT, ".github", "FUNDING.yml")))

    def test_windows_release_is_manual_only_and_android_release_has_tag_and_manual_triggers(self):
        windows = read_project_file(".github", "workflows", "windows-release.yml")
        triggers = windows[windows.index("on:"):windows.index("permissions:")]
        self.assertIn("workflow_dispatch:", triggers)
        self.assertNotIn("push:", triggers)
        android = read_project_file(".github", "workflows", "android-release.yml")
        triggers = android[android.index("on:"):android.index("permissions:")]
        self.assertIn("workflow_dispatch:", triggers)
        self.assertIn("tags:", triggers)

    def test_ci_builds_the_android_debug_apk_on_fork_branches(self):
        ci = read_project_file(".github", "workflows", "ci.yml")
        self.assertIn("work-mudafork", ci)
        self.assertIn("workflow_dispatch:", ci)
        self.assertIn(":app:assembleDebug", ci)
        self.assertIn("upload-artifact@v4", ci)

    def test_android_app_installs_beside_the_original(self):
        gradle = read_project_file("android", "app", "build.gradle.kts")
        self.assertIn('applicationId = "com.mudafork.android"', gradle)
        manifest = read_project_file("android", "app", "src", "main", "AndroidManifest.xml")
        self.assertIn('android:label="MudaFork"', manifest)


if __name__ == "__main__":
    unittest.main()
