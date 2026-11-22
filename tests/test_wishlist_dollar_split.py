"""Wishlist entries pasted from Mudae as "A$B$C" also split when the preset JSON is edited by hand."""

from types import SimpleNamespace
import unittest

from mudae_core.bot_config import configure_client
from mudae_core.filters import split_dollar_names

OPTIONS = {"bot_name": "MudaRemote", "claim_emojis": [], "kakera_emojis": [],
           "sphere_emojis": [], "slash_available": True}


class WishlistDollarSplitTests(unittest.TestCase):
    def test_list_items_split_on_dollar_but_keep_commas(self):
        self.assertEqual(
            split_dollar_names([" Ram $ Rem ", "Ram$$Emilia$", "Saber, Alter"]),
            ["Ram", "Rem", "Emilia", "Saber, Alter"],
        )

    def test_plain_string_splits_on_dollar_and_comma(self):
        self.assertEqual(split_dollar_names("Ram$Rem, Emilia"), ["Ram", "Rem", "Emilia"])
        self.assertEqual(split_dollar_names(None), [])

    def test_preset_json_with_dollar_entries_reaches_the_bot_split(self):
        client = SimpleNamespace(hourly_tu_refresh=False)
        configure_client(client, "test", {
            "channel_id": 1,
            "wishlist": ["Ram$Rem$Emilia"],
            "series_wishlist": ["Re:Zero$Fate/stay night"],
        }, **OPTIONS)
        for name in ("Ram", "Rem", "Emilia"):
            self.assertIn(name, client.wishlist)
        self.assertNotIn("Ram$Rem$Emilia", client.wishlist)
        self.assertEqual(client.series_wishlist, {"re:zero", "fate/stay night"})


if __name__ == "__main__":
    unittest.main()
