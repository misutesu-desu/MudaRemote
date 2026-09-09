"""Regressions for long-running slash sessions and missing PowerShell PATH."""
import ast
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from mudae_core.updater import _find_update_powershell, UpdateError
from mudae_core.updater import discover_update_manifest
from mudae_core.versioning import get_update_manifest_urls


class SlashRecoveryTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / "mudae_bot.py").read_text(encoding="utf-8"))
        names = {"_activate_slash_fallback", "_slash_ready"}
        nodes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names]
        self.client = SimpleNamespace(use_slash_rolls=True, slash_fallback_active=False,
                                      slash_retry_at=0, slash_fail_streak=3,
                                      mudae_slash_cache={"stale": {}})
        self.clock = mock.Mock()
        self.clock.monotonic.return_value = 172800.0
        self.scope = {"client": self.client, "time": self.clock, "BotLogger": mock.Mock(), "preset_name": "test"}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<slash recovery>", "exec"), self.scope)

    def test_long_running_session_recovers_and_refreshes_commands(self):
        self.scope["_activate_slash_fallback"]()
        self.assertFalse(self.scope["_slash_ready"]())
        self.clock.monotonic.return_value += 59
        self.assertFalse(self.scope["_slash_ready"]())
        self.clock.monotonic.return_value += 1
        self.assertTrue(self.scope["_slash_ready"]())
        self.assertFalse(self.client.slash_fallback_active)
        self.assertEqual(self.client.slash_fail_streak, 0)
        self.assertEqual(self.client.mudae_slash_cache, {})
        # A failed recovery gets another bounded cooldown, never a permanent switch.
        self.scope["_activate_slash_fallback"]()
        self.assertFalse(self.scope["_slash_ready"]())
        self.clock.monotonic.return_value += 60
        self.assertTrue(self.scope["_slash_ready"]())

    def test_text_presets_do_not_switch_to_slash(self):
        self.client.use_slash_rolls = False
        self.assertFalse(self.scope["_slash_ready"]())


class PowerShellDiscoveryTests(unittest.TestCase):
    def test_system_install_works_without_path_entry(self):
        expected = os.path.join("C:/Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        with mock.patch.dict(os.environ, {"SystemRoot": "C:/Windows"}), \
                mock.patch("mudae_core.updater.shutil.which", return_value=None), \
                mock.patch("mudae_core.updater.os.path.isfile", side_effect=lambda path: path == expected):
            self.assertEqual(_find_update_powershell(), expected)

    def test_powershell_seven_is_supported(self):
        with mock.patch("mudae_core.updater.shutil.which", side_effect=[None, "C:/Program Files/PowerShell/7/pwsh.exe"]):
            self.assertEqual(_find_update_powershell(), "C:/Program Files/PowerShell/7/pwsh.exe")

    def test_missing_shell_reports_discovery_failure(self):
        with mock.patch("mudae_core.updater.shutil.which", return_value=None), \
                mock.patch("mudae_core.updater.os.path.isfile", return_value=False):
            with self.assertRaisesRegex(UpdateError, "could not be found"):
                _find_update_powershell()


class StableManifestTests(unittest.TestCase):
    def test_published_stable_wins_over_stale_main_for_source_and_exe(self):
        urls = get_update_manifest_urls("main")
        manifests = {
            urls[0]: {"version": "4.8.10", "exe_download_url": "old", "exe_sha256": "a" * 64},
            urls[1]: {"version": "4.9.0", "exe_download_url": "stable", "exe_sha256": "b" * 64},
        }
        session = mock.Mock()
        session.get.side_effect = lambda url, **kwargs: SimpleNamespace(
            content=json.dumps(manifests[url]).encode(), raise_for_status=lambda: None)
        for frozen in (False, True):
            result = discover_update_manifest(session, "4.8.10", "main", frozen=frozen)
            self.assertEqual(result["status"], "available")
            self.assertEqual(result["version"], "4.9.0")
            result = discover_update_manifest(session, "4.9.1-beta.7", "main", frozen=frozen)
            self.assertEqual(result["status"], "current")
            self.assertEqual(result["version"], "4.9.0")

    def test_publication_pins_stable_sources_and_refuses_bad_hashes(self):
        import runpy
        prepare = runpy.run_path(str(Path(__file__).resolve().parents[1] / "packaging" / "publish_stable_manifest.py"))["prepare_manifest"]
        source = b"stable source"
        manifest = {"version": "4.9.0", "exe_sha256": "a" * 64, "source_files": [{
            "path": "mudae_bot.py", "sha256": hashlib.sha256(source).hexdigest(),
            "url": "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/beta/mudae_bot.py"}]}
        release = {"tag_name": "v4.9.0", "assets": [{"name": "MudaRemote.exe", "digest": "sha256:" + "a" * 64}]}
        def read_ref(tag, path):
            self.assertEqual(tag, "v4.9.0")
            return json.dumps(manifest).encode() if path == "version.json" else source
        result = prepare(release, read_ref)
        self.assertIn("/v4.9.0/", result["source_files"][0]["url"])
        manifest["source_files"][0]["sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "source checksum"):
            prepare(release, read_ref)
