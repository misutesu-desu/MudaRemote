import unittest

from mudae_core.filters import (
    CharacterNameSet,
    character_series_line,
    name_or_series_is_configured_wish,
    series_line_has_emoji,
)


class CharacterFilterTests(unittest.TestCase):
    def test_starwish_requires_emoji_on_series_line(self):
        self.assertTrue(series_line_has_emoji("Series Name ⭐\n100 kakera"))
        self.assertTrue(series_line_has_emoji("Series <:starwish:123>\n100 kakera"))
        self.assertFalse(series_line_has_emoji("Series Name\n100 kakera ⭐"))

    def test_starwish_accepts_emoji_on_wrapped_series_line(self):
        description = (
            "JoJo's Bizarre Adventure: Battle\n"
            "Tendency <:sw:1163913219782492220>\n"
            "<:goldkey:689475859429720211> (**6**) +5% kakera value\n"
            "Claims: #1,977"
        )
        self.assertTrue(series_line_has_emoji(description))
        self.assertEqual(
            character_series_line(description),
            "JoJo's Bizarre Adventure: Battle Tendency <:sw:1163913219782492220>",
        )

    def test_metadata_emoji_is_not_a_starwish(self):
        description = (
            "General Mascots\n"
            "<:goldkey:689475859429720211> (**6**) +5% kakera value\n"
            "**1,352**<:kakera:469835869059153940>"
        )
        self.assertFalse(series_line_has_emoji(description))

    def test_plus_signed_value_line_is_not_a_starwish(self):
        # Mudae can write the value as "+613"; its kakera icon must not be
        # folded into the series line and read as a starwish marker.
        description = (
            "Berserk\n"
            "+**613**<:kakera:469835869059153940>\n"
            "Now your SOULMATE!\n"
            "<:chaoskey:690110264166842421> (**10**) Kakera button costs are halved"
        )
        self.assertEqual(character_series_line(description), "Berserk")
        self.assertFalse(series_line_has_emoji(description))
        self.assertTrue(series_line_has_emoji(
            "Berserk <:sw:1163913219782492220>\n+**613**<:kakera:469835869059153940>"
        ))

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

    def test_wishlist_name_ignores_spacing_and_case(self):
        # Users type "EiaiNano" or paste a name with a non-breaking space;
        # Mudae shows "Eiai Nano". Both are the same character.
        wishlist = CharacterNameSet(["EiaiNano", "Hanazono Hakari", " Yoshimoto  Shizuka "])
        self.assertIn("eiai nano", wishlist)
        self.assertIn("Hanazono Hakari", wishlist)
        self.assertIn("yoshimoto shizuka", wishlist)
        self.assertNotIn("eiai", wishlist)
        self.assertTrue(name_or_series_is_configured_wish("Eiai Nano", "Other", ["EiaiNano"], []))

    def test_wishlist_name_set_ignores_blank_entries(self):
        self.assertFalse(CharacterNameSet(["", "  "]))
        self.assertEqual(CharacterNameSet(["AsUnA"]), {"asuna"})


if __name__ == "__main__":
    unittest.main()
