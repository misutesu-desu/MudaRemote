import unittest

from mudae_core.versioning import (
    CURRENT_VERSION,
    compare_versions,
    get_update_manifest_url,
    get_update_manifest_urls,
    is_newer_version,
    is_prerelease,
    load_update_channel_setting,
    resolve_update_channel,
    save_update_channel_setting,
)


class VersioningTests(unittest.TestCase):
    def test_numeric_segments_are_not_compared_lexically(self):
        self.assertGreater(compare_versions("4.10.0", "4.9.9"), 0)

    def test_prerelease_precedes_final_release(self):
        self.assertTrue(is_newer_version("5.0.0", "5.0.0-rc1"))
        self.assertFalse(is_newer_version("5.0.0-rc1", "5.0.0"))

    def test_optional_v_prefix_and_missing_segments(self):
        self.assertEqual(compare_versions("v4.6", "4.6.0"), 0)

    def test_is_prerelease_detects_beta_alpha_rc(self):
        self.assertTrue(is_prerelease("4.9.1-beta.2"))
        self.assertTrue(is_prerelease("5.0.0-rc1"))
        self.assertTrue(is_prerelease("1.0.0a1"))
        self.assertFalse(is_prerelease("4.8.10"))
        self.assertFalse(is_prerelease("4.9.0"))
        self.assertTrue(is_prerelease())  # default is CURRENT_VERSION (4.9.1-beta.2)

    def test_resolve_update_channel(self):
        import os
        # Default from CURRENT_VERSION (beta)
        self.assertEqual(resolve_update_channel(), "beta")
        # Stable version defaults to main
        self.assertEqual(resolve_update_channel(current_version="4.8.10"), "main")
        # Explicit argument overrides
        self.assertEqual(resolve_update_channel(channel="main"), "main")
        self.assertEqual(resolve_update_channel(channel="stable"), "main")
        self.assertEqual(resolve_update_channel(channel="beta"), "beta")
        # Environment variable override
        try:
            os.environ["MUDAREMOTE_UPDATE_CHANNEL"] = "main"
            self.assertEqual(resolve_update_channel(), "main")
            os.environ["MUDAREMOTE_UPDATE_CHANNEL"] = "beta"
            self.assertEqual(resolve_update_channel(current_version="4.8.10"), "beta")
        finally:
            os.environ.pop("MUDAREMOTE_UPDATE_CHANNEL", None)

    def test_get_update_manifest_urls(self):
        beta_urls = get_update_manifest_urls("beta")
        self.assertEqual(len(beta_urls), 2)
        self.assertIn("/beta/", beta_urls[0])
        self.assertIn("/main/", beta_urls[1])

        main_urls = get_update_manifest_urls("main")
        self.assertEqual(len(main_urls), 1)
        self.assertIn("/main/", main_urls[0])
        self.assertEqual(get_update_manifest_url("main"), main_urls[0])

    def test_load_and_save_update_channel_setting(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            # Initially none saved
            self.assertIsNone(load_update_channel_setting(td))
            self.assertEqual(resolve_update_channel(base_path=td), "beta")

            # Toggle beta off -> saves "main"
            saved = save_update_channel_setting("main", base_path=td)
            self.assertEqual(saved, "main")
            self.assertEqual(load_update_channel_setting(td), "main")
            self.assertEqual(resolve_update_channel(base_path=td), "main")

            # Toggle beta on -> saves "beta"
            saved = save_update_channel_setting("beta", base_path=td)
            self.assertEqual(saved, "beta")
            self.assertEqual(load_update_channel_setting(td), "beta")
            self.assertEqual(resolve_update_channel(base_path=td), "beta")

if __name__ == "__main__":
    unittest.main()
