import unittest
from types import SimpleNamespace

from mudae_core.kakera import (
    KakeraInteractionLedger,
    KakeraPowerLedger,
    calculate_kakera_power_cost,
    find_refreshed_component_button,
    get_kakera_emoji_targets,
    get_regular_kakera_filter_reason,
    has_op_perk_five_marker,
    has_perk_eight_discount,
    has_purple_kakera_button,
    is_character_sphere_emoji,
    kakera_embed_text,
    kakera_interaction_key,
    list_includes_purple,
    normalize_character_sphere_emoji,
    parse_kakera_result,
    parse_kakera_result_amount,
    queued_kakera_sort_key,
    should_refill_kakera_power,
    sphere_target_matches,
    unique_messages_by_id,
)


class KakeraPowerTests(unittest.TestCase):
    def test_terminal_purple_is_not_reowned_by_a_deferred_queue(self):
        ledger = KakeraInteractionLedger()
        purple = kakera_interaction_key(100, (0, 0), "kakeraP2")

        self.assertTrue(ledger.begin(purple))
        ledger.mark_terminal(purple, state="confirmed", custom_id="old")

        self.assertFalse(ledger.begin(kakera_interaction_key(100, (0, 0), "kakeraP")))
        self.assertEqual(ledger.terminal_state(purple), "confirmed")

    def test_distinct_button_on_same_message_remains_processable(self):
        ledger = KakeraInteractionLedger()
        purple = kakera_interaction_key(100, (0, 0), "kakeraP")
        white = kakera_interaction_key(100, (0, 1), "kakeraW")
        ledger.begin(purple)
        ledger.mark_terminal(purple)

        self.assertFalse(ledger.begin(purple))
        self.assertTrue(ledger.begin(white))

    def test_duplicate_queue_identity_can_only_be_owned_once(self):
        ledger = KakeraInteractionLedger()
        duplicate_keys = [kakera_interaction_key(200, (1, 2), "kakeraY")] * 3

        self.assertEqual(sum(ledger.begin(key) for key in duplicate_keys), 1)

    def test_duplicate_collected_roll_messages_keep_only_the_first_instance(self):
        original = SimpleNamespace(id=200, payload="original")
        duplicate = SimpleNamespace(id=200, payload="duplicate")
        independent = SimpleNamespace(id=201, payload="independent")

        self.assertEqual(
            unique_messages_by_id([original, duplicate, independent]),
            (original, independent),
        )

    def test_ambiguous_sent_interaction_is_terminal_for_outer_retries(self):
        ledger = KakeraInteractionLedger()
        key = kakera_interaction_key(300, (0, 0), "kakeraL")
        ledger.begin(key)
        ledger.mark_terminal(key, state="sent-ambiguous")

        self.assertFalse(ledger.begin(key))
        self.assertEqual(ledger.terminal_state(key), "sent-ambiguous")

    def test_genuine_failure_releases_identity_for_a_later_attempt(self):
        ledger = KakeraInteractionLedger()
        key = kakera_interaction_key(400, (0, 0), "kakeraO")

        self.assertTrue(ledger.begin(key))
        self.assertTrue(ledger.release(key))
        self.assertTrue(ledger.begin(key))

    def test_same_emoji_on_two_messages_has_independent_identity(self):
        ledger = KakeraInteractionLedger()
        first = kakera_interaction_key(500, (0, 0), "kakeraW")
        second = kakera_interaction_key(501, (0, 0), "kakeraW")
        ledger.begin(first)
        ledger.mark_terminal(first)

        self.assertTrue(ledger.begin(second))

    def test_interaction_ledger_prunes_terminal_entries_to_a_bound(self):
        ledger = KakeraInteractionLedger(maximum_entries=2)
        keys = [kakera_interaction_key(value, (0, 0), "kakeraP") for value in range(3)]
        for key in keys:
            ledger.begin(key)
            ledger.mark_terminal(key)

        self.assertEqual(ledger.terminal_count, 2)
        self.assertFalse(ledger.is_terminal(keys[0]))

    def test_paid_click_cost_is_reserved_until_matching_result(self):
        ledger = KakeraPowerLedger()
        token = ledger.reserve("kakeraL2", 40)

        self.assertEqual(ledger.available_power(100), 60)
        self.assertEqual(ledger.pending_count, 1)
        self.assertEqual(ledger.confirm("kakeraL"), 40)
        self.assertEqual(ledger.pending_count, 0)
        self.assertFalse(ledger.cancel(token))

    def test_lost_click_can_be_cancelled_without_spending_power(self):
        ledger = KakeraPowerLedger()
        token = ledger.reserve("kakeraC2", 40)

        self.assertTrue(ledger.cancel(token))
        self.assertEqual(ledger.available_power(100), 100)
        self.assertEqual(ledger.pending_count, 0)

    def test_result_only_confirms_matching_emoji_and_oldest_attempt(self):
        ledger = KakeraPowerLedger()
        first = ledger.reserve("kakeraL", 40)
        second = ledger.reserve("kakeraL2", 20)
        ledger.reserve("kakeraC", 40)

        self.assertIsNone(ledger.confirm("kakeraY"))
        self.assertEqual(ledger.confirm("kakeraL2"), 40)
        self.assertFalse(ledger.cancel(first))
        self.assertTrue(ledger.cancel(second))
        self.assertEqual(ledger.pending_count, 1)

    def test_status_snapshot_clears_unresolved_power_reservations(self):
        ledger = KakeraPowerLedger()
        ledger.reserve("kakeraL", 40)
        ledger.reserve("kakeraC", 20)

        ledger.clear()

        self.assertEqual(ledger.available_power(100), 100)
        self.assertFalse(ledger.has_pending)

    def test_kakera_result_exposes_emoji_for_power_confirmation(self):
        content = "<:kakeraY:605112931168026629>**karapisicik +421** ($k)"

        result = parse_kakera_result(content, ["karapisicik"])

        self.assertIsNotNone(result)
        self.assertEqual(result.amount, 421)
        self.assertEqual(result.emoji_name, "kakeraY")

    def test_dynamic_dk_refill_requires_authoritative_power(self):
        self.assertFalse(
            should_refill_kakera_power(
                20,
                40,
                power_is_confirmed=False,
            )
        )
        self.assertTrue(
            should_refill_kakera_power(
                20,
                40,
                power_is_confirmed=True,
            )
        )
        self.assertFalse(
            should_refill_kakera_power(
                100,
                40,
                power_is_confirmed=True,
            )
        )

    def test_dynamic_dk_refill_honors_custom_threshold_only_when_authoritative(self):
        self.assertTrue(
            should_refill_kakera_power(
                59,
                40,
                power_is_confirmed=True,
                configured_trigger=60,
            )
        )
        self.assertFalse(
            should_refill_kakera_power(
                59,
                40,
                power_is_confirmed=False,
                configured_trigger=60,
            )
        )

    def test_kakera_result_matches_own_username(self):
        content = "<:kakeraY:605112931168026629>**karapisicik +552** ($k)"
        self.assertEqual(parse_kakera_result_amount(content, ["karapisicik"]), 552)

    def test_kakera_result_ignores_other_users(self):
        content = "<:kakeraY:605112931168026629>**someone_else +552** ($k)"
        self.assertIsNone(parse_kakera_result_amount(content, ["karapisicik"]))

    def test_kakera_result_accepts_animated_emoji_and_grouped_amount(self):
        content = "<a:kakeraP:605112931168026629>**KARAPISICIK +1,234** ($k)"
        self.assertEqual(parse_kakera_result_amount(content, ["karapisicik"]), 1234)

    def test_free_purple_result_accepts_mudaes_free_marker(self):
        content = "<:kakeraP:609264156347990016>(Free) **karapisicik +114** ($k)"
        result = parse_kakera_result(content, ["karapisicik"])
        self.assertEqual(result.amount, 114)
        self.assertEqual(result.emoji_name, "kakeraP")

    def test_kakera_result_requires_the_kakera_confirmation_suffix(self):
        content = "<:kakeraY:605112931168026629>**karapisicik +552**"
        self.assertIsNone(parse_kakera_result_amount(content, ["karapisicik"]))

    def test_regular_kakera_filters_keep_ouroperks_distinct(self):
        self.assertEqual(
            get_regular_kakera_filter_reason(wish_only=True, is_wish=False),
            "character is not wished/starwished",
        )
        self.assertEqual(
            get_regular_kakera_filter_reason(op5_only=True, has_op5=False),
            "embed has no Ouroperk 5 sp emoji",
        )
        self.assertIsNone(
            get_regular_kakera_filter_reason(op5_only=True, has_op5=True)
        )

    def test_chaos_only_accepts_own_half_power_perk_eight_buttons(self):
        self.assertIsNone(
            get_regular_kakera_filter_reason(
                chaos_only=True,
                has_perk_eight_discount=True,
            )
        )
        self.assertIsNotNone(
            get_regular_kakera_filter_reason(
                chaos_only=True,
                is_external_roll=True,
                has_perk_eight_discount=True,
            )
        )
        self.assertIsNotNone(get_regular_kakera_filter_reason(chaos_only=True))

    def test_purple_kakera_button_is_detected_even_with_a_variant_suffix(self):
        class Emoji:
            def __init__(self, name):
                self.name = name

        class Button:
            def __init__(self, name):
                self.emoji = Emoji(name)

        class Row:
            def __init__(self, *buttons):
                self.children = buttons

        self.assertTrue(has_purple_kakera_button([Row(Button("kakeraP2"))]))
        self.assertFalse(has_purple_kakera_button([Row(Button("kakeraL"))]))

    def test_independent_half_cost_discounts_stack(self):
        self.assertEqual(calculate_kakera_power_cost(30), 30)
        self.assertEqual(calculate_kakera_power_cost(30, has_chaos_discount=True), 15)
        self.assertEqual(calculate_kakera_power_cost(30, has_perk_eight_discount=True), 15)
        self.assertEqual(
            calculate_kakera_power_cost(
                30,
                has_chaos_discount=True,
                has_perk_eight_discount=True,
            ),
            7.5,
        )

    def test_external_roll_only_uses_authoritative_perk_marker(self):
        self.assertEqual(
            calculate_kakera_power_cost(
                30,
                has_chaos_discount=True,
                has_perk_eight_discount=True,
                is_external_roll=True,
            ),
            15,
        )

    def test_free_button_cost_is_always_zero(self):
        self.assertEqual(
            calculate_kakera_power_cost(
                30,
                has_chaos_discount=True,
                has_perk_eight_discount=True,
                is_free=True,
            ),
            0,
        )

    def test_op5_and_perk_eight_use_distinct_markers(self):
        self.assertTrue(has_op_perk_five_marker("<:sp:1234567890>"))
        self.assertTrue(has_op_perk_five_marker("<a:sp:1234567890>"))
        self.assertFalse(has_op_perk_five_marker("💎 / 2"))
        self.assertFalse(has_op_perk_five_marker("<:spR:1234567890>"))
        for marker in ("💎/2", "💎 / 2", "💎 ÷ 2", "💎 ➗ 2️⃣"):
            self.assertTrue(has_perk_eight_discount("Perk 8: {}".format(marker)), marker)
        self.assertFalse(has_perk_eight_discount("<:spR:1234567890>"))
        self.assertFalse(has_perk_eight_discount("2x spheres"))

    def test_perk_markers_are_collected_from_embed_fields_and_footer(self):
        embed = SimpleNamespace(
            description="Series",
            fields=[SimpleNamespace(name="Bonus", value="💎 / 2")],
            footer=SimpleNamespace(text="<:sp:1234567890>"),
        )
        marker_text = kakera_embed_text(embed)
        self.assertTrue(has_perk_eight_discount(marker_text))
        self.assertTrue(has_op_perk_five_marker(marker_text))

    def test_red_sphere_button_aliases_match_the_same_target(self):
        self.assertEqual(normalize_character_sphere_emoji("sp"), "spR")
        self.assertEqual(normalize_character_sphere_emoji("spR2"), "spR")
        self.assertTrue(is_character_sphere_emoji("sp"))
        self.assertTrue(sphere_target_matches("sp", ["spR"]))
        self.assertTrue(sphere_target_matches("spR2", ["spR"]))
        self.assertFalse(sphere_target_matches("sp", ["spM"]))

    def test_deferred_clicks_prefer_cooldown_bypass_only_on_equal_priority(self):
        queued = [
            ("ordinary", queued_kakera_sort_key(50, False)),
            ("perk-eight", queued_kakera_sort_key(50, True)),
            ("sphere", queued_kakera_sort_key(999, False)),
        ]

        queued.sort(key=lambda item: item[1], reverse=True)

        self.assertEqual([name for name, _ in queued], ["sphere", "perk-eight", "ordinary"])

    def test_perk_eight_selection_is_used_for_external_and_own_rolls(self):
        normal = ["kakeraR"]
        chaos = ["kakeraO"]
        perk_eight = ["kakeraW"]
        for is_external in (False, True):
            self.assertEqual(
                get_kakera_emoji_targets(
                    normal,
                    chaos,
                    perk_eight,
                    has_chaos_discount=True,
                    has_perk_eight_discount=True,
                    is_external_roll=is_external,
                ),
                ("kakeraW",),
            )
        self.assertEqual(
            get_kakera_emoji_targets(
                normal,
                chaos,
                perk_eight,
                has_chaos_discount=True,
                is_external_roll=True,
            ),
            ("kakeraR",),
        )

    def test_explicit_empty_context_selection_stays_empty(self):
        self.assertEqual(
            get_kakera_emoji_targets(
                ["kakeraR"],
                ["kakeraO"],
                [],
                has_perk_eight_discount=True,
            ),
            (),
        )

    def test_purple_selection_detects_variants_and_normal_colors(self):
        self.assertTrue(list_includes_purple(["kakeraP"]))
        self.assertTrue(list_includes_purple(["kakeraR", "kakeraP2"]))
        self.assertTrue(list_includes_purple(["Kakerap"]))
        self.assertFalse(list_includes_purple(["kakeraR", "kakeraO"]))
        self.assertFalse(list_includes_purple([]))
        self.assertFalse(list_includes_purple(None))

    def test_mk_rolls_use_the_dedicated_mk_selection(self):
        normal = ["kakeraR"]
        chaos = ["kakeraO"]
        perk_eight = ["kakeraW"]
        mk = ["kakeraY"]

        self.assertEqual(
            get_kakera_emoji_targets(
                normal, chaos, perk_eight, mk, is_mk_roll=True,
            ),
            ("kakeraY",),
        )
        # Normal rolls must not leak the MK selection.
        self.assertEqual(
            get_kakera_emoji_targets(
                normal, chaos, perk_eight, mk,
            ),
            ("kakeraR",),
        )

    def test_mk_only_white_and_purple_share_the_same_mk_context(self):
        self.assertIsNone(
            get_regular_kakera_filter_reason(mk_only=True, is_mk_roll=True)
        )
        self.assertEqual(
            get_kakera_emoji_targets(
                ["kakeraR"], ["kakeraO"], ["kakeraY"],
                ["kakeraP", "kakeraW"], is_mk_roll=True,
            ),
            ("kakeraP", "kakeraW"),
        )

    def test_missing_mk_selection_inherits_regular_selection(self):
        self.assertEqual(
            get_kakera_emoji_targets(
                ["kakeraR"], ["kakeraO"], ["kakeraW"], None, is_mk_roll=True,
            ),
            ("kakeraR",),
        )
        # An explicit empty MK selection stays empty instead of restoring
        # every default colour.
        self.assertEqual(
            get_kakera_emoji_targets(
                ["kakeraR"], ["kakeraO"], ["kakeraW"], [], is_mk_roll=True,
            ),
            (),
        )

    def test_perk_eight_marker_still_beats_the_mk_selection(self):
        self.assertEqual(
            get_kakera_emoji_targets(
                ["kakeraR"],
                ["kakeraO"],
                ["kakeraW"],
                ["kakeraY"],
                has_perk_eight_discount=True,
                is_mk_roll=True,
            ),
            ("kakeraW",),
        )

    def test_refreshed_repeated_buttons_prefer_position_over_shared_custom_id(self):
        def button(name, custom_id="shared"):
            return SimpleNamespace(
                emoji=SimpleNamespace(name=name),
                custom_id=custom_id,
            )

        yellow = button("kakeraY")
        first_orange = button("kakeraO")
        second_orange = button("kakeraO")
        rows = [SimpleNamespace(children=[yellow, first_orange, second_orange])]

        resolved = find_refreshed_component_button(
            rows,
            custom_id="shared",
            position=(0, 2),
            emoji_name="kakeraO",
        )
        self.assertIs(resolved, second_orange)

    def test_purple_and_chaos_configuration_semantics(self):
        """Verify exact semantics of only_chaos, collect_purple_kakera, wish_starwish_kakera_only, and kakera_emojis."""
        # Config 1: Reporter setup where only kakeraC is configured in kakera_emojis and chaos_emojis
        kakera_emojis = ["kakeraC"]
        chaos_emojis = ["kakeraC"]

        # Case 1: Ordinary character (not wish, no chaos discount) -> blocked by wish_only and chaos_only
        filter_reason = get_regular_kakera_filter_reason(
            wish_only=True,
            is_wish=False,
            chaos_only=True,
            has_chaos_discount=False,
        )
        self.assertEqual(filter_reason, "character is not wished/starwished")

        # Case 2: Wishlist character without chaos discount -> blocked by chaos_only
        filter_reason = get_regular_kakera_filter_reason(
            wish_only=True,
            is_wish=True,
            chaos_only=True,
            has_chaos_discount=False,
        )
        self.assertEqual(filter_reason, "Chaos Only requires a half-power Kakera reaction on your own roll")

        # Case 3: Starwish character with chaos discount -> filter passes
        filter_reason = get_regular_kakera_filter_reason(
            wish_only=True,
            is_wish=True,
            chaos_only=True,
            has_chaos_discount=True,
        )
        self.assertIsNone(filter_reason)

        # Target list for regular roll with chaos discount:
        targets = get_kakera_emoji_targets(
            kakera_emojis,
            chaos_emojis,
            perk_eight_emojis=[],
            mk_emojis=None,
            has_chaos_discount=True,
        )
        self.assertEqual(targets, ("kakeraC",))
        # Ordinary purple is NOT in targets
        self.assertFalse(list_includes_purple(targets))

        # Case 4: If kakera_emojis includes kakeraP, ordinary purple IS in targets and collected
        kakera_emojis_with_purple = ["kakeraC", "kakeraP"]
        targets_with_purple = get_kakera_emoji_targets(
            kakera_emojis_with_purple,
            chaos_emojis,
            perk_eight_emojis=[],
            mk_emojis=None,
            has_chaos_discount=False,
        )
        self.assertTrue(list_includes_purple(targets_with_purple))


if __name__ == "__main__":
    unittest.main()
