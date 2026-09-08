import hashlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

from mudae_core.updater import (
    REQUIRED_SOURCE_PATHS,
    UpdateError,
    apply_update,
    discover_update_manifest,
    format_update_changelog,
)


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
            "file-{}".format(index): b"# generated test source\n"
            for index, _ in enumerate(sorted(REQUIRED_SOURCE_PATHS))
        }
        manifest = {
            "version": "4.10.0",
            "source_files": [
                _entry(path, key, files[key])
                for key, path in zip(files, sorted(REQUIRED_SOURCE_PATHS))
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            result = apply_update(_Session(files), manifest, "4.9.9", directory)
            self.assertEqual(result, "source")
            with open(os.path.join(directory, "mudae_core", "__init__.py"), "rb") as handle:
                entry = next(item for item in manifest["source_files"] if item["path"] == "mudae_core/__init__.py")
                self.assertEqual(handle.read(), files[entry["url"]])

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
            with self.assertRaisesRegex(UpdateError, "current installation was kept unchanged"):
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

    def test_source_update_commits_version_metadata(self):
        files = {
            "file-{}".format(index): b"# module content\n"
            for index, _ in enumerate(sorted(REQUIRED_SOURCE_PATHS))
        }
        manifest = {
            "version": "4.10.0",
            "source_files": [
                _entry(path, key, files[key])
                for key, path in zip(sorted(files.keys()), sorted(REQUIRED_SOURCE_PATHS))
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            result = apply_update(_Session(files), manifest, "4.9.0", directory)
            self.assertEqual(result, "source")
            self.assertTrue(os.path.isfile(os.path.join(directory, "version.json")))
            self.assertTrue(os.path.isfile(os.path.join(directory, ".version")))
            with open(os.path.join(directory, ".version"), "r", encoding="utf-8") as vh:
                self.assertEqual(vh.read().strip(), "4.10.0")

    def test_frozen_update_creates_payload_and_powershell_artifacts(self):
        content = b"fake-frozen-exe"
        session = _Session({"exe": content})
        manifest = {
            "version": "5.0.0",
            "exe_download_url": "exe",
            "exe_sha256": hashlib.sha256(content).hexdigest(),
        }
        with tempfile.TemporaryDirectory() as directory:
            executable = os.path.join(directory, "MudaRemote.exe")
            with mock.patch("mudae_core.updater.subprocess.Popen"):
                result = apply_update(session, manifest, "4.0.0", directory, frozen=True, executable=executable)
            self.assertEqual(result, "frozen")

            # Verify isolated per-attempt directory is created with all artifacts
            stage_dirs = [d for d in os.listdir(directory) if d.startswith("mudae-frozen-update-")]
            self.assertTrue(stage_dirs)
            stage_path = os.path.join(directory, stage_dirs[0])
            self.assertTrue(os.path.isfile(os.path.join(stage_path, "update_payload.json")))
            self.assertTrue(os.path.isfile(os.path.join(stage_path, "update_helper.ps1")))
            self.assertTrue(os.path.isfile(os.path.join(stage_path, "update.bat")))

            # Verify update_helper.ps1 contains the lock timeout abort check
            with open(os.path.join(stage_path, "update_helper.ps1"), "r", encoding="utf-8") as h:
                ps_text = h.read()
            self.assertIn("if ($null -eq $lockStream)", ps_text)
            self.assertIn("exit 6", ps_text)

            # Verify update.bat uses %~dp0 and does NOT interpolate arbitrary arguments
            with open(os.path.join(stage_path, "update.bat"), "r", encoding="utf-8") as h:
                bat_text = h.read()
            self.assertIn("%~dp0update_helper.ps1", bat_text)
            self.assertNotIn("start \"\"", bat_text)

    def test_frozen_update_rejects_concurrent_installation_lock(self):
        content = b"fake-frozen-exe"
        session = _Session({"exe": content})
        manifest = {
            "version": "5.0.0",
            "exe_download_url": "exe",
            "exe_sha256": hashlib.sha256(content).hexdigest(),
        }
        with tempfile.TemporaryDirectory() as directory:
            executable = os.path.join(directory, "MudaRemote.exe")
            install_lock = os.path.join(directory, "update_frozen_install.lock")
            # Hold lock using OS locking to simulate an active helper
            fd = os.open(install_lock, os.O_CREAT | os.O_RDWR)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                with self.assertRaisesRegex(UpdateError, "Another frozen update installation is currently in progress"):
                    apply_update(session, manifest, "4.0.0", directory, frozen=True, executable=executable)
            finally:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "requires Windows PowerShell")
    def test_powershell_helper_execution_moves_and_verifies_hash(self):
        import json, subprocess, sys, time
        with tempfile.TemporaryDirectory() as td:
            current = os.path.join(td, "app.exe")
            with open(current, "wb") as f:
                f.write(b"OLD_BINARY")

            with open(sys.executable, "rb") as ef:
                py_bytes = ef.read()
            py_hash = hashlib.sha256(py_bytes).hexdigest()

            session = _Session({"dummy": py_bytes})
            manifest = {
                "version": "9.9.9",
                "exe_download_url": "dummy",
                "exe_sha256": py_hash,
            }
            with mock.patch("mudae_core.updater.subprocess.Popen"):
                apply_update(session, manifest, "1.0.0", td, frozen=True, executable=current)

            stage_dirs = [d for d in os.listdir(td) if d.startswith("mudae-frozen-update-")]
            stage_path = os.path.join(td, stage_dirs[0])
            ps_path = os.path.join(stage_path, "update_helper.ps1")
            payload_path = os.path.join(stage_path, "update_payload.json")

            with open(payload_path, "r", encoding="utf-8") as f:
                p = json.load(f)
            p["pid"] = 9999999
            p["arguments"] = ["-c", "import sys; sys.exit(0)"]
            with open(payload_path, "w", encoding="utf-8") as f:
                json.dump(p, f)

            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps_path, "-PayloadPath", payload_path]
            run_res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run_res.returncode, 0)

            with open(current, "rb") as f:
                self.assertEqual(f.read(), py_bytes)
            self.assertFalse(os.path.exists(stage_path))
            time.sleep(1.0)

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "requires Windows PowerShell")
    def test_powershell_helper_lock_timeout_aborts_without_mutation(self):
        import json, msvcrt, subprocess
        with tempfile.TemporaryDirectory() as td:
            current = os.path.join(td, "app.exe")
            with open(current, "wb") as f:
                f.write(b"ORIGINAL_BYTES")
            content = b"NEW_BYTES"
            session = _Session({"dummy": content})
            manifest = {
                "version": "9.9.9",
                "exe_download_url": "dummy",
                "exe_sha256": hashlib.sha256(content).hexdigest(),
            }
            with mock.patch("mudae_core.updater.subprocess.Popen"):
                apply_update(session, manifest, "1.0.0", td, frozen=True, executable=current)

            stage_dirs = [d for d in os.listdir(td) if d.startswith("mudae-frozen-update-")]
            stage_path = os.path.join(td, stage_dirs[0])
            ps_path = os.path.join(stage_path, "update_helper.ps1")
            payload_path = os.path.join(stage_path, "update_payload.json")

            with open(payload_path, "r", encoding="utf-8") as f:
                p = json.load(f)
            p["pid"] = 9999999
            with open(payload_path, "w", encoding="utf-8") as f:
                json.dump(p, f)

            with open(ps_path, "r", encoding="utf-8") as pf:
                ps_code = pf.read().replace("AddSeconds(30)", "AddSeconds(1)")
            with open(ps_path, "w", encoding="utf-8") as pf:
                pf.write(ps_code)

            lock_file = os.path.join(td, "update_frozen_install.lock")
            fd = os.open(lock_file, os.O_CREAT | os.O_RDWR)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            try:
                cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps_path, "-PayloadPath", payload_path]
                run_res = subprocess.run(cmd, capture_output=True, text=True)
                self.assertEqual(run_res.returncode, 6)
                with open(current, "rb") as f:
                    self.assertEqual(f.read(), b"ORIGINAL_BYTES")
            finally:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                os.close(fd)

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "requires Windows PowerShell")
    def test_powershell_helper_checksum_mismatch_restores_backup(self):
        import json, subprocess
        with tempfile.TemporaryDirectory() as td:
            current = os.path.join(td, "app.exe")
            with open(current, "wb") as f:
                f.write(b"ORIGINAL_BYTES")
            content = b"STAGED_CONTENT"
            session = _Session({"dummy": content})
            manifest = {
                "version": "9.9.9",
                "exe_download_url": "dummy",
                "exe_sha256": hashlib.sha256(content).hexdigest(),
            }
            with mock.patch("mudae_core.updater.subprocess.Popen"):
                apply_update(session, manifest, "1.0.0", td, frozen=True, executable=current)

            stage_dirs = [d for d in os.listdir(td) if d.startswith("mudae-frozen-update-")]
            stage_path = os.path.join(td, stage_dirs[0])
            ps_path = os.path.join(stage_path, "update_helper.ps1")
            payload_path = os.path.join(stage_path, "update_payload.json")

            with open(payload_path, "r", encoding="utf-8") as f:
                p = json.load(f)
            p["pid"] = 9999999
            # Tamper with expected_hash to exercise helper's post-staging checksum mismatch detection
            p["expected_hash"] = "1111111111111111111111111111111111111111111111111111111111111111"
            with open(payload_path, "w", encoding="utf-8") as f:
                json.dump(p, f)
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps_path, "-PayloadPath", payload_path]
            run_res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run_res.returncode, 4)
            with open(current, "rb") as f:
                self.assertEqual(f.read(), b"ORIGINAL_BYTES")

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "requires Windows PowerShell")
    def test_powershell_helper_child_process_argv_round_trip(self):
        import json, subprocess, sys, time
        with tempfile.TemporaryDirectory() as td:
            current = os.path.join(td, "app.exe")
            with open(current, "wb") as f:
                f.write(b"OLD_BYTES")

            with open(sys.executable, "rb") as ef:
                py_bytes = ef.read()
            py_hash = hashlib.sha256(py_bytes).hexdigest()

            session = _Session({"dummy": py_bytes})
            manifest = {
                "version": "9.9.9",
                "exe_download_url": "dummy",
                "exe_sha256": py_hash,
            }
            with mock.patch("mudae_core.updater.subprocess.Popen"):
                apply_update(session, manifest, "1.0.0", td, frozen=True, executable=current)

            stage_dirs = [d for d in os.listdir(td) if d.startswith("mudae-frozen-update-")]
            stage_path = os.path.join(td, stage_dirs[0])
            ps_path = os.path.join(stage_path, "update_helper.ps1")
            payload_path = os.path.join(stage_path, "update_payload.json")

            out_file = os.path.join(td, "argv_out.json")
            script_file = os.path.join(td, "record_argv.py")
            with open(script_file, "w", encoding="utf-8") as sf:
                sf.write(f'import sys, json; json.dump(sys.argv[1:], open(r"{out_file}", "w", encoding="utf-8"))')

            test_args = [
                script_file,
                "--flag",
                "",
                "with space",
                "C:\\trailing\\",
                "a&b",
                'with "quote"',
                "%PATH%",
                "unicode_µ_ğ",
                "excl!mark",
            ]

            with open(payload_path, "r", encoding="utf-8") as f:
                p = json.load(f)
            p["pid"] = 9999999
            p["arguments"] = test_args
            with open(payload_path, "w", encoding="utf-8") as f:
                json.dump(p, f)

            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps_path, "-PayloadPath", payload_path]
            run_res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run_res.returncode, 0)
            time.sleep(1.0)

            with open(out_file, "r", encoding="utf-8") as f:
                received = json.load(f)
            self.assertEqual(received, test_args[1:])

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "requires Windows PowerShell")
    def test_powershell_helper_launch_failure_restores_backup_and_exits_5(self):
        import json, subprocess
        with tempfile.TemporaryDirectory() as td:
            current = os.path.join(td, "app.exe")
            with open(current, "wb") as f:
                f.write(b"ORIGINAL_BACKUP_BYTES")

            staged_bytes = b"CORRUPTED_NON_PE_BYTES"
            staged_hash = hashlib.sha256(staged_bytes).hexdigest()

            session = _Session({"dummy": staged_bytes})
            manifest = {
                "version": "9.9.9",
                "exe_download_url": "dummy",
                "exe_sha256": staged_hash,
            }
            with mock.patch("mudae_core.updater.subprocess.Popen"):
                apply_update(session, manifest, "1.0.0", td, frozen=True, executable=current)

            stage_dirs = [d for d in os.listdir(td) if d.startswith("mudae-frozen-update-")]
            stage_path = os.path.join(td, stage_dirs[0])
            ps_path = os.path.join(stage_path, "update_helper.ps1")
            payload_path = os.path.join(stage_path, "update_payload.json")

            with open(payload_path, "r", encoding="utf-8") as f:
                p = json.load(f)
            p["pid"] = 9999999
            with open(payload_path, "w", encoding="utf-8") as f:
                json.dump(p, f)

            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps_path, "-PayloadPath", payload_path]
            run_res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run_res.returncode, 5)
            with open(current, "rb") as f:
                self.assertEqual(f.read(), b"ORIGINAL_BACKUP_BYTES")
    def test_discover_update_manifest(self):
        import json
        beta_manifest = json.dumps({"version": "4.9.1-beta.3"}).encode("utf-8")
        main_manifest = json.dumps({"version": "4.8.10"}).encode("utf-8")
        session = _Session({
            "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/refs/heads/beta/version.json": beta_manifest,
            "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/refs/heads/main/version.json": main_manifest,
        })
        # Beta user looking for updates discovers 4.9.1-beta.3
        discovered = discover_update_manifest(session, current_version="4.9.1-beta.2", channel="beta")
        self.assertEqual(discovered["status"], "available")
        self.assertEqual(discovered["version"], "4.9.1-beta.3")

        # Stable user querying main does not see beta
        stable = discover_update_manifest(session, current_version="4.8.10", channel="main")
        self.assertEqual(stable["status"], "current")

    def test_discover_update_manifest_skips_pending_frozen_and_handles_primary_error(self):
        import json
        pending_manifest = json.dumps({
            "version": "5.0.0",
            "exe_download_url": "https://example.com/MudaRemote.exe",
            "exe_sha256": "pending-github-actions",
        }).encode("utf-8")
        session = _Session({
            "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/refs/heads/beta/version.json": pending_manifest,
        })
        # Frozen update should skip pending exe checksum
        result = discover_update_manifest(session, current_version="4.9.1-beta.2", channel="beta", frozen=True)
        self.assertEqual(result["status"], "current")

    def test_replace_transactionally_rolls_back_on_failure(self):
        from mudae_core.updater import _replace_transactionally
        with tempfile.TemporaryDirectory() as base_dir, tempfile.TemporaryDirectory() as stage_dir:
            file_a = os.path.join(base_dir, "a.py")
            file_b = os.path.join(base_dir, "b.py")
            with open(file_a, "w") as f:
                f.write("original A")
            with open(file_b, "w") as f:
                f.write("original B")

            stage_a = os.path.join(stage_dir, "a.py")
            stage_b = os.path.join(stage_dir, "b.py")
            with open(stage_a, "w") as f:
                f.write("new A")
            with open(stage_b, "w") as f:
                f.write("new B")

            real_replace = os.replace
            call_count = [0]
            def failing_replace(src, dst):
                call_count[0] += 1
                if call_count[0] == 2:  # Fail on second file
                    raise OSError("Simulated disk error during replacement")
                return real_replace(src, dst)

            with mock.patch("mudae_core.updater.os.replace", side_effect=failing_replace):
                with self.assertRaises(OSError):
                    _replace_transactionally(base_dir, stage_dir, ["a.py", "b.py"])

            # Verify both files were restored to original
            with open(file_a, "r") as f:
                self.assertEqual(f.read(), "original A")
            with open(file_b, "r") as f:
                self.assertEqual(f.read(), "original B")

    def test_interrupted_update_recovery_restores_original_files(self):
        from mudae_core.updater import recover_interrupted_update
        import json, shutil
        with tempfile.TemporaryDirectory() as base_dir:
            file_a = os.path.join(base_dir, "app.py")
            with open(file_a, "w") as f:
                f.write("corrupted mid-commit app")

            backup_dir = os.path.join(base_dir, "mudae-backup-recovery-test")
            os.makedirs(backup_dir, exist_ok=True)
            with open(os.path.join(backup_dir, "app.py"), "w") as f:
                f.write("pristine original app")

            journal_path = os.path.join(base_dir, "update_journal.json")
            with open(journal_path, "w", encoding="utf-8") as f:
                json.dump({"backup_dir": backup_dir, "replaced": ["app.py"]}, f)

            # Run recovery
            recovered = recover_interrupted_update(base_dir)
            self.assertTrue(recovered)
            with open(file_a, "r") as f:
                self.assertEqual(f.read(), "pristine original app")
            self.assertFalse(os.path.exists(journal_path))
            self.assertFalse(os.path.exists(backup_dir))

    def test_replace_transactionally_preserves_backup_on_restoration_failure(self):
        from mudae_core.updater import _replace_transactionally, UpdateError
        import os, shutil
        with tempfile.TemporaryDirectory() as base_dir, tempfile.TemporaryDirectory() as stage_dir:
            file_a = os.path.join(base_dir, "a.py")
            file_b = os.path.join(base_dir, "b.py")
            with open(file_a, "w") as f:
                f.write("orig A")
            with open(file_b, "w") as f:
                f.write("orig B")
            with open(os.path.join(stage_dir, "a.py"), "w") as f:
                f.write("new A")
            with open(os.path.join(stage_dir, "b.py"), "w") as f:
                f.write("new B")

            real_replace = os.replace
            real_copy = shutil.copyfile
            def failing_replace(src, dst):
                if src.endswith("b.py"):
                    raise OSError("Disk locked on b.py")
                return real_replace(src, dst)

            def failing_copy(src, dst):
                if "mudae-backup" in src:
                    raise OSError("Disk locked during rollback restoration")
                return real_copy(src, dst)

            with mock.patch("mudae_core.updater.os.replace", side_effect=failing_replace), \
                 mock.patch("mudae_core.updater.shutil.copyfile", side_effect=failing_copy):
                with self.assertRaises(UpdateError) as cm:
                    _replace_transactionally(base_dir, stage_dir, ["a.py", "b.py"])
                self.assertIn("backup preserved at", str(cm.exception))

if __name__ == "__main__":
    unittest.main()
