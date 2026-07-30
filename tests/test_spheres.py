import unittest

from mudae_core.spheres import (
    chest_red_candidates,
    choose_chest_position,
    choose_chest_reward_position,
    choose_harvest_position,
    count_harvest_bonus_clicks,
    harvest_reveal_is_free,
    normalize_sphere_emoji,
    parse_sphere_game_status,
)


class SphereStatusTests(unittest.TestCase):
    def test_counts_dark_to_purple_bonus_from_separate_result_message(self):
        result = (
            "<:spT:1> +304\n"
            "<:spD:2> turns into <:spP:3>\n"
            "<:spP:3> (Free) +224"
        )

        self.assertEqual(count_harvest_bonus_clicks(result), 1)
        self.assertEqual(count_harvest_bonus_clicks("<:spD:2> +110"), 0)

    def test_parses_supplied_tu_stock_and_refill(self):
        status = parse_sphere_game_status(
            "**0** $oh left for today, **1** $oc, **0** $oq and **0** $ot.\n"
            "**1h 43** min before the refill."
        )

        self.assertIsNotNone(status)
        self.assertEqual((status.oh, status.oc, status.oq, status.ot), (0, 1, 0, 0))
        self.assertEqual(status.refill_minutes, 103)

    def test_returns_none_when_tu_has_no_sphere_game_section(self):
        self.assertIsNone(parse_sphere_game_status("You have 15 rolls left. $rt is available!"))

    def test_stored_uses_are_added_to_daily_uses(self):
        status = parse_sphere_game_status(
            "**0** $oh left for today, **0** $oc (+**4** stored), **0** $oq and **0** $ot.\n"
            "**10h 51** min before the refill."
        )

        self.assertIsNotNone(status)
        self.assertEqual(status.oc, 0)
        self.assertEqual(status.oc_stored, 4)
        self.assertEqual(status.available_for("oc"), 4)
        self.assertEqual(status.refill_minutes, 651)

    def test_localized_stored_uses_are_added(self):
        status = parse_sphere_game_status(
            "0 $oh restantes hoje (+8 armazenados), 0 $oc (+7 armazenados), "
            "0 $oq (+7 armazenados) e 0 $ot (+3 armazenados)."
        )

        self.assertIsNotNone(status)
        self.assertEqual(status.available_for("oh"), 8)
        self.assertEqual(status.available_for("oc"), 7)


class SphereBoardTests(unittest.TestCase):
    def test_chest_solver_finds_red_on_supplied_board_within_five_clicks(self):
        completed_board = [
            "spG", "spT", "spT", "spO", "sp",
            "spB", "spB", "spB", "spY", "spO",
            "spB", "spB", "spY", "spB", "spG",
            "spB", "spT", "spB", "spB", "spG",
            "spY", "spB", "spB", "spB", "spG",
        ]
        visible = ["spU"] * 25
        disabled = [False] * 25
        found = False

        for _ in range(5):
            position = choose_chest_position(visible, disabled)
            self.assertIsNotNone(position)
            visible[position] = completed_board[position]
            disabled[position] = True
            if completed_board[position] == "sp":
                found = True
                break

        self.assertTrue(found)

    def test_first_chest_click_uses_guaranteed_safe_center(self):
        self.assertEqual(choose_chest_position(["spU"] * 25, [False] * 25), 12)

    def test_revealed_clues_reduce_red_candidates(self):
        board = ["spU"] * 25
        board[12] = "spY"
        self.assertEqual(chest_red_candidates(board), (0, 4, 6, 8, 16, 18, 20, 24))

    def test_chest_uses_remaining_clicks_for_best_visible_reward(self):
        board = ["spB"] * 25
        board[4] = "sp"
        board[3] = "spO"
        disabled = [False] * 25
        disabled[4] = True

        self.assertEqual(choose_chest_reward_position(board, disabled, 4), 3)
        self.assertEqual(choose_chest_position(board, disabled), 3)

    def test_chest_prefers_promising_unknown_over_blue_after_red(self):
        board = ["spB"] * 25
        board[4] = "sp"
        board[3] = "spU"
        disabled = [False] * 25
        disabled[4] = True

        self.assertEqual(choose_chest_reward_position(board, disabled, 4), 3)

    def test_custom_chest_reward_priority_overrides_default_value_order(self):
        board = ["spB"] * 25
        board[4] = "sp"
        board[3] = "spO"
        board[2] = "spG"
        disabled = [False] * 25
        disabled[4] = True

        self.assertEqual(
            choose_chest_position(
                board,
                disabled,
                reward_priority_order=["spG", "spO"],
            ),
            2,
        )

    def test_harvest_prefers_high_value_revealed_sphere(self):
        board = ["spU"] * 25
        board[2] = "spB"
        board[7] = "spW"
        self.assertEqual(choose_harvest_position(board, [False] * 25, paid_clicks=4), 7)

    def test_custom_harvest_priority_can_prefer_a_lower_default_reward(self):
        board = ["spB"] * 25
        board[2] = "spG"
        board[7] = "spW"
        self.assertEqual(
            choose_harvest_position(
                board,
                [False] * 25,
                paid_clicks=4,
                priority_order=["spG", "spW"],
            ),
            2,
        )

    def test_harvest_secures_high_value_reveal_before_early_unknown(self):
        board = ["spU"] * 25
        board[3] = "spT"
        board[7] = "spG"
        self.assertEqual(choose_harvest_position(board, [False] * 25, paid_clicks=0), 7)

    def test_free_purple_variant_is_normalized(self):
        self.assertEqual(normalize_sphere_emoji("spP2"), "spP")
        self.assertTrue(harvest_reveal_is_free("spP2"))
        self.assertFalse(harvest_reveal_is_free("spB2"))

    def test_harvest_preserves_enough_clicks_for_all_guaranteed_prizes(self):
        board = ["spU"] * 25
        board[7] = "spR"
        board[18] = "spW"
        self.assertEqual(choose_harvest_position(board, [False] * 25, paid_clicks=3), 18)

    def test_harvest_prioritizes_free_purple_click(self):
        board = ["spU"] * 25
        board[4] = "spW"
        board[18] = "spP"
        self.assertEqual(choose_harvest_position(board, [False] * 25), 18)

    def test_harvest_explores_unknown_instead_of_early_low_value_reveal(self):
        board = ["spU"] * 25
        board[12] = "spB"
        board[14] = "spT"
        board[23] = "spB"
        self.assertEqual(choose_harvest_position(board, [False] * 25, paid_clicks=0), 7)

    def test_harvest_saves_dark_sphere_for_last_two_paid_clicks(self):
        board = ["spB"] * 25
        board[4] = "spD"
        board[12] = "spU"
        self.assertEqual(choose_harvest_position(board, [False] * 25, paid_clicks=1), 12)
        self.assertEqual(choose_harvest_position(board, [False] * 25, paid_clicks=3), 4)

    def test_board_choice_stops_when_every_button_is_disabled(self):
        disabled = [True] * 25
        self.assertIsNone(choose_chest_position(["spU"] * 25, disabled))
        self.assertIsNone(choose_harvest_position(["spU"] * 25, disabled))


if __name__ == "__main__":
    unittest.main()
