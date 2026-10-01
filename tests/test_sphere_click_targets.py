import unittest

from mudae_core.bot_config import configure_client  # noqa: F401  (import must keep working)
from mudae_core.kakera import resolve_sphere_click_targets, sphere_target_matches

ALL = {"spp", "spb", "spt", "spg", "spy", "spo", "spr", "spw", "spl", "spd", "spm", "spu"}


class SphereClickTargetsTest(unittest.TestCase):
    def test_unset_targets_click_every_sphere_colour(self):
        self.assertEqual(resolve_sphere_click_targets(None), ALL)

    def test_the_old_nine_colour_default_is_upgraded(self):
        old = ["spG", "spY", "spO", "spR", "spW", "spL", "spD", "spM", "spU"]
        self.assertEqual(resolve_sphere_click_targets(old), ALL)

    def test_a_deliberate_choice_is_kept(self):
        self.assertEqual(resolve_sphere_click_targets(["spP", "spG"]), {"spp", "spg"})
        self.assertEqual(resolve_sphere_click_targets([]), set())

    def test_variants_and_aliases_still_match(self):
        targets = resolve_sphere_click_targets(None)
        for name in ("spP", "spB2", "spT", "sp", "spU"):
            self.assertTrue(sphere_target_matches(name, targets), name)


if __name__ == "__main__":
    unittest.main()
