import unittest

from mudae_core.kakera import (
    calculate_kakera_power_cost,
    has_op_perk_five_marker,
    has_perk_eight_discount,
)


class KakeraPowerTests(unittest.TestCase):
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
        self.assertTrue(has_op_perk_five_marker("<:spR:1234567890>"))
        self.assertTrue(has_op_perk_five_marker("<a:spR:1234567890>"))
        self.assertFalse(has_op_perk_five_marker("💎 / 2"))
        self.assertFalse(has_op_perk_five_marker("<:spr:1234567890>"))
        for marker in ("💎/2", "💎 / 2", "💎 ÷ 2", "💎 ➗ 2️⃣"):
            self.assertTrue(has_perk_eight_discount("Perk 8: {}".format(marker)), marker)
        self.assertFalse(has_perk_eight_discount("<:spR:1234567890>"))
        self.assertFalse(has_perk_eight_discount("2x spheres"))


if __name__ == "__main__":
    unittest.main()
