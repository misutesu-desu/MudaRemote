import unittest
from types import SimpleNamespace

from mudae_core.kakera import (
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
    normalize_character_sphere_emoji,
    parse_kakera_result,
    parse_kakera_result_amount,
    should_refill_kakera_power,
    sphere_target_matches,
)


class KakeraPowerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
