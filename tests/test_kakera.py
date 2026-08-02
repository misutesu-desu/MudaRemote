import unittest

from mudae_core.kakera import (
    calculate_kakera_power_cost,
    get_regular_kakera_filter_reason,
    has_op_perk_five_marker,
    has_perk_eight_discount,
    has_purple_kakera_button,
    parse_kakera_result_amount,
)


class KakeraPowerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
