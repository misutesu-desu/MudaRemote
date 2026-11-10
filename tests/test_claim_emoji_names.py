import unittest
from types import SimpleNamespace

import mudae_bot
from mudae_core.claiming import expand_claim_emojis


class ClaimEmojiNamesTests(unittest.TestCase):
    def test_custom_emoji_names(self):
        for text, name in (
            ('<:smirk:1372315229505196162>', 'smirk'),
            ('<a:kekBomb:1400542016567247011>', 'kekBomb'),
            (':smirk:', 'smirk'),
        ):
            with self.subTest(text=text):
                expanded = expand_claim_emojis([text])
                self.assertIn(text, expanded)
                self.assertIn(name, expanded)

    def test_blue_heart_shortcode(self):
        self.assertIn('\U0001f499', expand_claim_emojis([':blue_heart:']))

    def test_custom_emoji_claim_button(self):
        button = SimpleNamespace(emoji=SimpleNamespace(name='smirk'), disabled=False)
        message = SimpleNamespace(components=[SimpleNamespace(children=[button])])
        embed = SimpleNamespace(footer=None)
        emojis = expand_claim_emojis(['<:smirk:1372315229505196162>'])
        self.assertTrue(mudae_bot.has_claim_option(message, embed, emojis))
