import unittest

from mudae_core.versioning import compare_versions, is_newer_version


class VersioningTests(unittest.TestCase):
    def test_numeric_segments_are_not_compared_lexically(self):
        self.assertGreater(compare_versions("4.10.0", "4.9.9"), 0)

    def test_prerelease_precedes_final_release(self):
        self.assertTrue(is_newer_version("5.0.0", "5.0.0-rc1"))
        self.assertFalse(is_newer_version("5.0.0-rc1", "5.0.0"))

    def test_optional_v_prefix_and_missing_segments(self):
        self.assertEqual(compare_versions("v4.6", "4.6.0"), 0)


if __name__ == "__main__":
    unittest.main()
