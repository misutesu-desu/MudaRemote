from types import SimpleNamespace
import unittest

import mudae_bot


def _wish_message(content, *mention_ids):
    return SimpleNamespace(content=content, mentions=[SimpleNamespace(id=i) for i in mention_ids])


class WishLanguageTests(unittest.TestCase):
    def test_english_wish_is_detected(self):
        self.assertTrue(mudae_bot.is_wished_by_self(_wish_message("Wished by <@7001>", 7001), 7001))

    def test_french_wish_is_detected(self):
        # Mudae set to French writes "Souhaité par" instead of "Wished by".
        self.assertTrue(mudae_bot.is_wished_by_self(_wish_message("Souhaité par <@7001>", 7001), 7001))

    def test_wish_for_someone_else_is_ignored(self):
        self.assertFalse(mudae_bot.is_wished_by_self(_wish_message("Souhaité par <@8002>", 8002), 7001))

    def test_mention_without_wish_text_is_ignored(self):
        self.assertFalse(mudae_bot.is_wished_by_self(_wish_message("<@7001> nice roll", 7001), 7001))


if __name__ == "__main__":
    unittest.main()
