"""Eligibility combinations and real collection paths, without Discord access."""
import asyncio
import copy
import inspect
import itertools
import json
from pathlib import Path
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest import mock

import mudae_bot
from android.generate_schema import main as generate_schema
from mudae_core.config import atomic_write_json, validate_preset
from mudae_core.kakera import get_regular_kakera_filter_reason
from mudae_preset_editor import PresetEditor, build_recommended_preset
from tests.test_kakera_snipe_ownership import _create_test_client, _build_roll_message


FILTERS = ('chaos_only', 'shop_seven_only', 'mk_only', 'op5_only', 'wish_only')
MATCHES = ('has_chaos_discount', 'is_shop_seven', 'is_mk_roll', 'has_op5', 'is_wish')


class MatchingTests(unittest.TestCase):
    def test_native_desktop_control_defaults_to_all_and_switches_to_any(self):
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('No desktop display available')
        self.addCleanup(root.destroy)
        root.withdraw()
        editor = PresetEditor.__new__(PresetEditor)
        editor.root = root
        editor.widgets = {}
        editor.settings_fields = []
        editor.subframe_controls = {}
        editor.rounds_frame = None
        editor.mark_dirty = mock.Mock()
        editor.apply_theme()
        PresetEditor.add_choice_field(editor, root, 'kakera_filter_match_mode', 'Match selected filters:',
                                     {'all': 'All (AND)', 'any': 'Any (OR)'})
        self.assertEqual(editor.widgets['kakera_filter_match_mode'].get(), 'all')
        container = root.winfo_children()[0]
        radio_buttons = container.winfo_children()[1:]
        # The real settings search runs even with an empty query when a preset opens.
        for query in ('', 'any', 'unrelated search', '', 'kakera_filter_match_mode'):
            editor._filter_container_children(root, query)
            self.assertEqual(container.winfo_manager() == 'pack', query != 'unrelated search')
            for button in radio_buttons:
                self.assertEqual(button.winfo_manager(), 'pack', (query, button.cget('text')))
        radio_buttons[1].invoke()
        self.assertEqual(editor.widgets['kakera_filter_match_mode'].get(), 'any')
        radio_buttons[0].invoke()
        self.assertEqual(editor.widgets['kakera_filter_match_mode'].get(), 'all')

    def test_all_enabled_and_matching_combinations(self):
        for mode, enabled, matched in itertools.product(
            ('all', 'any'), itertools.product((False, True), repeat=5),
            itertools.product((False, True), repeat=5),
        ):
            selected = [value for use, value in zip(enabled, matched) if use]
            expected = not selected or (all(selected) if mode == 'all' else any(selected))
            reason = get_regular_kakera_filter_reason(
                match_mode=mode, **dict(zip(FILTERS, enabled)), **dict(zip(MATCHES, matched)),
            )
            self.assertEqual(reason is None, expected, (mode, enabled, matched))

    def test_discount_evidence_and_ownership(self):
        for mode in ('all', 'any'):
            for external, keys, perk, expected in (
                (False, True, False, True), (True, True, False, False),
                (False, False, True, True), (True, False, True, True),
                (False, False, False, False),
            ):
                self.assertEqual(get_regular_kakera_filter_reason(
                    match_mode=mode, chaos_only=True, is_external_roll=external,
                    has_chaos_discount=keys, has_perk_eight_discount=perk,
                    is_mk_roll=True, is_shop_seven=True,
                ) is None, expected)

    def test_preset_defaults_validation_storage_and_android_schema(self):
        preset = build_recommended_preset()
        self.assertEqual(preset['kakera_filter_match_mode'], 'all')
        preset.update(kakera_filter_match_mode='any', only_chaos=True, mk_only=True,
                      kakera_reaction_snipe_mode=True, kakera_emojis=[], chaos_emojis=[], mk_kakera_emojis=[])
        self.assertEqual(validate_preset(preset, require_runtime=False), [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'presets.json')
            atomic_write_json(str(path), {'Any': preset, 'Legacy': {}})
            restored = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(restored['Any']['kakera_filter_match_mode'], 'any')
            self.assertEqual(restored['Legacy'].get('kakera_filter_match_mode', 'all'), 'all')
            generate_schema(str(Path(__file__).resolve().parents[1]), directory)
            fields = json.loads(Path(directory, 'android_schema.json').read_text(encoding='utf-8'))['fields']
        field = fields['kakera_filter_match_mode']
        self.assertEqual(field['default'], 'all')
        self.assertEqual(set(field['choices']), {'all', 'any'})
        self.assertIn('All: discounted AND Shop 7. Any: discounted OR Shop 7.', field['description'])
        for key in ('only_chaos', 'shop_perk_7_only', 'mk_only', 'op_perk_5_only', 'wish_starwish_kakera_only'):
            self.assertEqual(fields[key]['section'], 'Kakera Reactions')
            self.assertGreater(fields[key]['order'], field['order'])
        self.assertTrue(validate_preset(dict(preset, kakera_filter_match_mode='invalid'), require_runtime=False))

    def test_desktop_form_saves_and_loads_each_mode(self):
        # Exercise the actual form methods without creating a window or touching user presets.
        for mode in ('all', 'any'):
            editor = mock.Mock(spec=PresetEditor)
            editor.current_preset = 'test'
            editor.widgets = {'kakera_filter_match_mode': mock.Mock(get=lambda: mode),
                              'inactive_hours': mock.Mock(get=lambda: ''),
                              'reactive_kakera_delay_min': mock.Mock(get=lambda: '0'),
                              'reactive_kakera_delay_max': mock.Mock(get=lambda: '0')}
            editor._persist_preset_data.return_value = True
            self.assertTrue(PresetEditor.save_current_preset(editor, show_success=False))
            data = editor._persist_preset_data.call_args.args[0]
            self.assertEqual(data['kakera_filter_match_mode'], mode)
        for preset, expected in (({}, 'all'), ({'kakera_filter_match_mode': 'any'}, 'any')):
            editor = mock.Mock(spec=PresetEditor)
            editor.current_preset = None
            editor.presets = {'test': preset}
            editor.bot_processes = {}
            editor.widgets = {key: mock.Mock() for key in ('kakera_filter_match_mode', 'inactive_hours',
                                                          'reactive_kakera_delay_min', 'reactive_kakera_delay_max')}
            editor.preset_listbox = mock.Mock(size=lambda: 0)
            editor.secret_store = mock.Mock(get_tokens=lambda *args: [])
            editor.root = mock.Mock()
            editor.title_label = mock.Mock()
            editor.run_status_label = mock.Mock()
            PresetEditor._select_preset_impl(editor, 'test')
            editor.widgets['kakera_filter_match_mode'].set.assert_called_once_with(expected)


class CollectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sleep = mock.patch.object(mudae_bot, 'pause_interruptible_sleep', mock.AsyncMock(return_value=True))
        self.sleep.start()
        self.addCleanup(self.sleep.stop)
        log = mock.patch.object(mudae_bot.BotLogger, 'log')
        log.start()
        self.addCleanup(log.stop)
        self.bot, self.channel = _create_test_client()
        self.bot.dk_consumption = 30

    def message(self, name='kakeraC', style=2, description='Series', owner=None, message_id=6001):
        msg, btn = _build_roll_message(self.channel, message_id, owner or self.bot.user.id,
                                       'other' if owner else self.bot.user.name, name, client=self.bot)
        btn.style = style
        msg.embeds[0].description = description
        self.channel.fetch_message = mock.AsyncMock(return_value=msg)
        return msg, btn

    async def collect(self, msg, queued=False, **context):
        if not queued:
            return await self.bot._runtime_claim_character(self.bot, self.channel, msg, is_kakera=True, **context)
        self.bot.immediate_kakera_click = False
        self.bot.auto_mk_enabled = False
        self.bot._preserve_collected_rolls = True
        self.bot.collected_kakera_rolls = [msg, msg]
        await self.bot._runtime_start_roll_commands(self.bot, self.channel, 0, False, False, is_us_pull=True)

    async def test_shop_and_discount_qualify_independently_in_any_on_each_path(self):
        for queued, mode, style, desc in itertools.product(
            (False, True), ('all', 'any'), (1, 2), ('Series', 'Series 💎 / 2'),
        ):
            with self.subTest(queued=queued, mode=mode, style=style, desc=desc):
                self.bot.kakera_filter_match_mode = mode
                self.bot.only_chaos = self.bot.shop_perk_7_only = True
                self.bot.kakera_interaction_ledger = mudae_bot.KakeraInteractionLedger()
                self.bot.kakera_power_ledger.clear()
                msg, btn = self.message(style=style, description=desc)
                await self.collect(msg, queued)
                expected = (style == 1 and '💎' in desc) if mode == 'all' else (style == 1 or '💎' in desc)
                self.assertEqual(btn.click.await_count, int(expected))
                self.assertEqual(self.bot.kakera_power_ledger.available_power(100),
                                 100 - (15 if '💎' in desc else 30) if expected else 100)

    async def test_op5_wish_starwish_mk_are_alternatives_not_mandatory(self):
        for mode in ('all', 'any'):
            self.bot.kakera_filter_match_mode = mode
            self.bot.op_perk_5_only = self.bot.wish_starwish_kakera_only = self.bot.mk_only = True
            for index, (desc, mk) in enumerate((('Series <:sp:123>', False), ('Series <:wish:123>', False),
                                              ('Series <:sw:123>', False), ('Series', True),
                                              ('Series <:sw:123>\n<:sp:456>', True))):
                self.bot.kakera_power_ledger.clear()
                msg, btn = self.message(description=desc, message_id=6100 + index + (10 if mode == 'any' else 0))
                await self.collect(msg, is_mk_roll=mk)
                self.assertEqual(btn.click.await_count, int(mode == 'any' or index == 4), (mode, desc, mk))

    async def test_context_colors_and_empty_overrides_remain_authoritative(self):
        self.bot.kakera_filter_match_mode = 'any'
        self.bot.shop_perk_7_only = self.bot.op_perk_5_only = True
        self.bot.kakera_emojis = ['kakeraC']
        self.bot.chaos_emojis = ['kakeraY']
        self.bot.sphere_perk_emojis = ['kakeraR']
        self.bot.mk_kakera_emojis = ['kakeraW']
        details = inspect.getclosurevars(inspect.getclosurevars(self.bot._runtime_claim_character).nonlocals['click_kakera_with_confirmation']).nonlocals['kakera_click_details']
        for desc, context, selected in (
            ('Series <:sp:123>', {}, 'kakeraC'),
            ('Series <:sp:123>\n<:chaoskey:123> (**10**)', {}, 'kakeraY'),
            ('Series <:sp:123> 💎 / 2', {}, 'kakeraR'),
            ('Series <:sp:123>', {'is_mk_roll': True}, 'kakeraW'),
            ('Series <:sp:123>\n<:chaoskey:123> (**10**)', {'is_snipe': True}, 'kakeraC'),
            ('Series <:sp:123> 💎 / 2', {'is_snipe': True, 'is_mk_roll': True}, 'kakeraR'),
        ):
            for name in ('kakeraC', 'kakeraY', 'kakeraR', 'kakeraW'):
                msg, btn = self.message(name=name, description=desc)
                self.assertEqual(details(msg, btn, **context) is not None, name == selected, (desc, context, name))
        self.bot.mk_kakera_emojis = []
        msg, btn = self.message(description='Series <:sp:123>')
        self.assertIsNone(details(msg, btn, is_mk_roll=True))
        inherited, _ = _create_test_client(kakera_emojis_preset=['kakeraY'])
        for field in ('chaos_emojis', 'sphere_perk_emojis', 'mk_kakera_emojis'):
            self.assertEqual(getattr(inherited, field), ['kakeraY'])
        self.assertEqual(inherited.kakera_filter_match_mode, 'all')
        loaded, _ = _create_test_client(kakera_filter_match_mode_preset='any')
        self.assertEqual(loaded.kakera_filter_match_mode, 'any')

    async def test_free_green_every_color_bypasses_filters_colors_power_and_cooldown(self):
        self.bot.only_chaos = self.bot.shop_perk_7_only = self.bot.mk_only = True
        self.bot.op_perk_5_only = self.bot.wish_starwish_kakera_only = True
        self.bot.kakera_emojis = self.bot.chaos_emojis = self.bot.sphere_perk_emojis = self.bot.mk_kakera_emojis = []
        self.bot.kakera_power_thresholds = {'kakeraC': 100, 'kakeraY': 100}
        self.bot.current_dk_power = None
        self.bot.kakera_react_available = False
        for index, name in enumerate(mudae_bot.KAKERA_EMOJIS + ['kakeraG', 'kakeraT', 'kakeraC2']):
            msg, btn = self.message(name=name, style=3, message_id=6200 + index)
            await self.bot.events['on_message'](msg)
            btn.click.assert_awaited_once()
        self.assertEqual(self.bot.kakera_power_ledger.pending_count, 0)
        msg, claim = self.message(name='💖', style=3)
        await self.collect(msg)
        claim.click.assert_not_awaited()

    async def test_mixed_free_paid_and_duplicate_disabled_buttons(self):
        for queued in (False, True):
            self.bot.kakera_interaction_ledger = mudae_bot.KakeraInteractionLedger()
            self.bot.kakera_power_ledger.clear()
            self.bot.current_dk_power = 20
            self.bot.kakera_filter_match_mode = 'any'
            self.bot.shop_perk_7_only = True
            msg, free = self.message(name='kakeraY', style=3)
            _, paid = self.message(style=1, message_id=6301)
            _, disabled = self.message(name='kakeraR', style=3, message_id=6302)
            disabled.disabled = True
            msg.components[0].children += [paid, disabled]
            self.channel.fetch_message.return_value = msg
            await self.collect(msg, queued)
            await self.collect(msg, queued)
            free.click.assert_awaited_once()
            paid.click.assert_not_awaited()
            disabled.click.assert_not_awaited()
            self.assertEqual(self.bot.kakera_power_ledger.available_power(20), 20)

    async def test_free_context_still_requires_channel_and_snipe_permission(self):
        self.bot.kakera_filter_match_mode = 'any'
        msg, btn = self.message(style=3, owner=9999)
        await self.bot.events['on_message'](msg)
        btn.click.assert_not_awaited()
        self.bot.kakera_reaction_snipe_mode_active = True
        self.bot.kakera_reaction_snipe_targets = ['8888']
        await self.bot.events['on_message'](msg)
        btn.click.assert_not_awaited()
        self.bot.kakera_reaction_snipe_targets = ['9999']
        msg.channel = SimpleNamespace(id=99999)
        await self.bot.events['on_message'](msg)
        btn.click.assert_not_awaited()
        msg.channel = self.channel
        await self.bot.events['on_message'](msg)
        btn.click.assert_awaited_once()

    async def test_refreshed_and_retried_styles_recheck_eligibility_and_cost(self):
        for queued, initial, refreshed_style, power, expected in (
            (True, 3, 1, 20, 0), (True, 1, 3, 0, 1),
            (True, 2, 3, 0, 1),
            (False, 3, 1, 20, 1), (False, 1, 3, 30, 2),
        ):
            with self.subTest(queued=queued, initial=initial, refreshed=refreshed_style):
                self.bot.kakera_interaction_ledger = mudae_bot.KakeraInteractionLedger()
                self.bot.kakera_power_ledger.clear()
                self.bot.kakera_filter_match_mode = 'any'
                self.bot.shop_perk_7_only = True
                self.bot.current_dk_power = power
                msg, btn = self.message(style=initial)
                refreshed = copy.copy(msg)
                second = copy.copy(btn)
                second.style = refreshed_style
                refreshed.components = [SimpleNamespace(children=[second])]
                self.channel.fetch_message.return_value = refreshed
                if not queued:
                    second.click = mock.AsyncMock(side_effect=btn.click.side_effect)
                    btn.click.side_effect = None
                original_wait = asyncio.wait_for

                async def fast_timeout(future, timeout):
                    if timeout == 2.5 and not future.done():
                        future.cancel()
                        raise asyncio.TimeoutError
                    return await original_wait(future, timeout)

                with mock.patch.object(mudae_bot.asyncio, 'wait_for', side_effect=fast_timeout):
                    await self.collect(msg, queued)
                clicks = btn.click.await_count + (second.click.await_count if not queued else 0)
                self.assertEqual(clicks, expected)
                self.assertEqual(self.bot.kakera_power_ledger.pending_count, 0)
                self.assertEqual(self.bot.kakera_interaction_ledger.in_flight_count, 0)

    async def test_refresh_after_free_click_can_enable_another_free_button(self):
        self.bot.shop_perk_7_only = True
        self.bot.kakera_filter_match_mode = 'any'
        self.bot.current_dk_power = 0
        self.bot.kakera_priority_order = ['kakeraC', 'kakeraY']
        msg, first = self.message(style=3)
        _, second = self.message(name='kakeraY', style=2, message_id=6501)
        msg.components[0].children.append(second)
        refreshed = copy.copy(msg)
        free_second = copy.copy(second)
        free_second.style = 3
        refreshed.components = [SimpleNamespace(children=[first, free_second])]
        self.channel.fetch_message.return_value = refreshed
        await asyncio.gather(self.collect(msg), self.collect(msg))
        first.click.assert_awaited_once()
        second.click.assert_awaited_once()
        self.assertEqual(self.bot.kakera_power_ledger.pending_count, 0)

    async def test_retry_rejects_disabled_button_and_changed_embed_selection(self):
        for disabled in (False, True):
            self.bot.kakera_interaction_ledger = mudae_bot.KakeraInteractionLedger()
            msg, btn = self.message(style=1)
            self.bot.shop_perk_7_only = True
            self.bot.sphere_perk_emojis = []
            refreshed = copy.deepcopy(msg)
            refreshed.embeds[0].description = 'Series 💎 / 2'
            refreshed.components[0].children[0].disabled = disabled
            self.channel.fetch_message.return_value = refreshed
            btn.click.side_effect = None
            with mock.patch.object(mudae_bot.asyncio, 'wait_for', side_effect=asyncio.TimeoutError):
                await self.collect(msg)
            btn.click.assert_awaited_once()
            refreshed.components[0].children[0].click.assert_not_awaited()
            self.assertEqual(self.bot.kakera_power_ledger.pending_count, 0)

    async def test_late_free_confirmation_during_refresh_prevents_duplicate(self):
        msg, btn = self.message(style=3)
        btn.click.side_effect = None

        async def confirm_during_refresh(message_id):
            for waiters in self.bot._kakera_result_waiters.values():
                for waiter in waiters:
                    waiter.set_result(150)
            btn.disabled = True
            return msg

        self.channel.fetch_message.side_effect = confirm_during_refresh
        with mock.patch.object(mudae_bot.asyncio, 'wait_for', side_effect=asyncio.TimeoutError):
            self.assertTrue(await self.collect(msg))
        btn.disabled = False
        await self.collect(msg)
        btn.click.assert_awaited_once()

    async def test_purple_and_sphere_selections_remain_separate(self):
        self.bot.only_chaos = self.bot.shop_perk_7_only = True
        self.bot.collect_purple_kakera = False
        self.bot.kakera_emojis = []
        self.bot.sphere_click_targets = []
        details = inspect.getclosurevars(inspect.getclosurevars(self.bot._runtime_claim_character).nonlocals['click_kakera_with_confirmation']).nonlocals['kakera_click_details']
        for name in ('kakeraP', 'spR'):
            msg, btn = self.message(name=name)
            self.assertIsNone(details(msg, btn, allow_special_purple=True))
        self.bot.collect_purple_kakera = True
        self.bot.sphere_click_targets = ['spR']
        for name in ('kakeraP', 'spR'):
            msg, btn = self.message(name=name)
            self.assertEqual(details(msg, btn, allow_special_purple=True)[0], 0)

    async def test_any_paid_threshold_and_ownership_limits_still_apply(self):
        self.bot.kakera_filter_match_mode = 'any'
        self.bot.only_chaos = self.bot.shop_perk_7_only = True
        self.bot.kakera_power_thresholds = {'kakeraC': 80}
        self.bot.current_dk_power = 70
        msg, btn = self.message(style=1, description='Series\n<:chaoskey:123> (**10**)')
        await self.collect(msg, is_snipe=True)
        btn.click.assert_not_awaited()
        self.bot.kakera_power_thresholds = {}
        await self.collect(msg, is_snipe=True)
        btn.click.assert_awaited_once()
        self.assertEqual(self.bot.kakera_power_ledger.available_power(70), 40)


if __name__ == '__main__':
    unittest.main()
