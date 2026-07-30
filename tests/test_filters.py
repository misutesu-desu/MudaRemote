import unittest

from mudae_core.filters import (
    character_series_line,
    name_or_series_is_configured_wish,
    series_line_has_emoji,
)


class CharacterFilterTests(unittest.TestCase):
    def test_starwish_requires_emoji_on_series_line(self):
        self.assertTrue(series_line_has_emoji("Series Name ⭐\n100 kakera"))
        self.assertTrue(series_line_has_emoji("Series <:starwish:123>\n100 kakera"))
        self.assertFalse(series_line_has_emoji("Series Name\n100 kakera ⭐"))

    def test_configured_name_and_series_wishes_are_case_insensitive(self):
        self.assertTrue(name_or_series_is_configured_wish("Rem", "", ["rem"], []))
        self.assertTrue(
            name_or_series_is_configured_wish(
                "Other",
                "Re:Zero − Starting Life",
                [],
                ["re:zero"],
            )
        )
        self.assertEqual(character_series_line("\nSeries Name\nValue"), "Series Name")


if __name__ == "__main__":
    unittest.main()
