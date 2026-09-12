"""Shop 7 regressions using the reported blue Chaos + two grey Yellow buttons."""
import inspect
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import discord
import mudae_bot
from android.generate_schema import main as generate_schema
from mudae_preset_editor import build_recommended_preset
from tests.test_kakera_snipe_ownership import _create_test_client, _build_roll_message


DESCRIPTION = (
    'Persona 5 <:sw:1163913219782492220>\n'
    '<:chaoskey:690110264166842421> (**47,510**) +5% kakera value\n'
    '<:chaoskey:690110264166842421> (**47,511**) +5% kakera value\n'
    '**9,194,872**<:kakera:469835869059153940>\n'
    '23<:sp:1437140700604137554> ☑️'
)


class ShopSevenTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client, self.channel = _create_test_client()
        self.assertFalse(self.client.shop_perk_7_only)
        self.client.shop_perk_7_only = True
        self.client.dk_consumption = 30
        self.message, self.blue = _build_roll_message(
            self.channel, 1548150204442873967, self.client.user.id,
            self.client.user.name, kakera_emoji='kakeraC', client=self.client,
        )
        self.blue.style = discord.ButtonStyle.primary
        self.message.embeds[0].description = DESCRIPTION
        self.greys = []
        for index in range(2):
            _, grey = _build_roll_message(
                self.channel, 100 + index, self.client.user.id,
                self.client.user.name, client=self.client,
            )
            self.greys.append(grey)
        self.message.components[0].children.extend(self.greys)
        self.channel.fetch_message = mock.AsyncMock(return_value=self.message)

    async def test_reported_mixed_buttons_click_only_blue(self):
        await self.client.events['on_message'](self.message)
        self.blue.click.assert_awaited_once()
        for grey in self.greys:
            grey.click.assert_not_awaited()
        self.assertEqual(self.client.kakera_power_ledger.available_power(100), 85)

    async def test_shop_seven_and_discount_filters_are_independent(self):
        self.message.embeds[0].description = 'Persona 5'
        self.client.only_chaos = True
        await self.client._runtime_claim_character(
            self.client, self.channel, self.message, is_kakera=True,
        )
        self.blue.click.assert_not_awaited()
        self.client.only_chaos = False
        await self.client._runtime_claim_character(
            self.client, self.channel, self.message, is_kakera=True,
        )
        self.blue.click.assert_awaited_once()
        # A blue background does not itself grant a power discount.
        self.assertEqual(self.client.kakera_power_ledger.available_power(100), 70)

    async def test_existing_color_and_power_rules_still_apply_to_external_rolls(self):
        self.client.kakera_emojis = ['kakeraY']
        await self.client._runtime_claim_character(
            self.client, self.channel, self.message, is_kakera=True, is_snipe=True,
        )
        self.blue.click.assert_not_awaited()
        self.client.kakera_emojis = ['kakeraC']
        self.client.current_dk_power = 20
        await self.client._runtime_claim_character(
            self.client, self.channel, self.message, is_kakera=True, is_snipe=True,
        )
        self.blue.click.assert_not_awaited()
        self.client.current_dk_power = 100
        await self.client._runtime_claim_character(
            self.client, self.channel, self.message, is_kakera=True, is_snipe=True,
        )
        self.blue.click.assert_awaited_once()
        self.assertEqual(self.client.kakera_power_ledger.available_power(100), 70)

    async def test_deferred_collection_and_refreshed_style(self):
        self.client.immediate_kakera_click = False
        self.client.auto_mk_enabled = False
        self.client._preserve_collected_rolls = True
        self.client.collected_kakera_rolls = [self.message]
        # The candidate was blue when queued, but is grey by the time it is fetched.
        refreshed = SimpleNamespace(
            id=self.message.id,
            components=[SimpleNamespace(children=[SimpleNamespace(
                emoji=self.blue.emoji, custom_id=self.blue.custom_id, disabled=False,
                style=discord.ButtonStyle.secondary, click=self.blue.click,
            )] + self.greys)],
        )
        self.channel.fetch_message.return_value = refreshed
        with mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)):
            await self.client._runtime_start_roll_commands(
                self.client, self.channel, 0, False, False, is_us_pull=True,
            )
        self.blue.click.assert_not_awaited()
        self.assertEqual(self.client.kakera_power_ledger.pending_count, 0)
        self.assertEqual(self.client.kakera_interaction_ledger.in_flight_count, 0)
        self.channel.fetch_message.return_value = self.message
        self.client._preserve_collected_rolls = True
        self.client.collected_kakera_rolls = [self.message]
        with mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True)):
            await self.client._runtime_start_roll_commands(
                self.client, self.channel, 0, False, False, is_us_pull=True,
            )
        self.blue.click.assert_awaited_once()
        for grey in self.greys:
            grey.click.assert_not_awaited()

    def test_filter_checks_button_style_and_preserves_free_collection(self):
        details = inspect.getclosurevars(inspect.getclosurevars(self.client._runtime_claim_character).nonlocals['click_kakera_with_confirmation']).nonlocals['kakera_click_details']
        eligible = inspect.getclosurevars(details).nonlocals['kakera_button_is_eligible']
        for name, style, expected in (
            ('kakeraC', 1, True), ('kakeraC2', discord.ButtonStyle.primary, True),
            ('kakeraC', 2, False), ('kakeraC', None, False),
            ('kakeraY', 2, False), ('kakera', 1, False),
            ('kakeraP', 2, True), ('spR', 2, True),
        ):
            with self.subTest(name=name, style=style):
                button = SimpleNamespace(emoji=SimpleNamespace(name=name), style=style)
                self.client.sphere_click_targets = ['spR']
                self.assertEqual(details(self.message, button) is not None, expected)
                button.disabled = True
                self.assertFalse(eligible(button, [name], None))
        self.client.shop_perk_7_only = False
        self.assertTrue(eligible(self.greys[0], ['kakeraY'], None))
        self.assertFalse(eligible(self.blue, ['kakeraC'], 'another Only filter'))

    def test_desktop_and_android_default_to_disabled(self):
        self.assertFalse(build_recommended_preset()['shop_perk_7_only'])
        with tempfile.TemporaryDirectory() as directory:
            generate_schema(str(Path(__file__).resolve().parents[1]), directory)
            field = json.loads(Path(directory, 'android_schema.json').read_text(encoding='utf-8'))['fields']['shop_perk_7_only']
        self.assertEqual(field['type'], 'boolean')
        self.assertFalse(field['default'])
        self.assertEqual(field['section'], 'Kakera Reactions')


if __name__ == '__main__':
    unittest.main()
