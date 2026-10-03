"""Auto $oq (Sphere Quest) and $ot (Sphere Trace) solvers and board flow."""
from types import SimpleNamespace
import unittest
from unittest import mock

from mudae_core.sphere_runtime import SphereRuntime, sphere_game_kind, sphere_reveal_costs_click
from mudae_core.spheres import (
    choose_quest_position,
    choose_trace_position,
    parse_trace_rules,
    quest_purple_layouts,
)

# Finished boards reported by a user (row by row).
QUEST_TEXT = (
    "You can click **7** times on the buttons below (2 minutes).\n"
    "**Find 3 purple spheres** (out of 4) to turn the 4th purple into a **red sphere** or more.\n"
    "Colors define the number of neighboring purples (8 tiles around).\n"
    "Blue = 0, teal = 1, green = 2, yellow = 3, orange = 4\n\nMultiplier: **7x**"
)
QUEST_BOARD = [
    "spB", "spG", "spP", "spY", "sp",
    "spT", "spY", "spP", "spY", "spT",
    "spP", "spG", "spT", "spT", "spB",
    "spT", "spT", "spB", "spB", "spB",
    "spB", "spB", "spB", "spB", "spB",
]
TRACE_TEXT = (
    "You can click **4** times on the buttons below (2 minutes).\n"
    "**All colors are free (they don't consume clicks) except for the blue spheres**\n"
    "Identical colors follow one another on the same row or column. For example, there is a line or a "
    "column having ALL the green spheres following one another.\n"
    "Spheres to find: teal = 4, green = 3, yellow = 3, rarer spheres = 2.\n\n"
    "Number of different colors: **6**\nMultiplier: **7x**"
)
TRACE_BOARD = [
    "spG", "spG", "spG", "spT", "spB",
    "spB", "spB", "spB", "spT", "spB",
    "spO", "spB", "spB", "spT", "spL",
    "spO", "spB", "spB", "spT", "spL",
    "spB", "spY", "spY", "spY", "spB",
]


class QuestSolverTests(unittest.TestCase):
    def test_finished_board_has_exactly_one_purple_layout(self):
        layouts = quest_purple_layouts(QUEST_BOARD)
        self.assertEqual(len(layouts), 1)
        self.assertEqual([i for i in range(25) if layouts[0] >> i & 1], [2, 4, 7, 10])

    def test_first_click_is_the_center(self):
        self.assertEqual(choose_quest_position(["spU"] * 25, [False] * 25), 12)

    def test_certain_purple_is_clicked_next(self):
        board = ["spU"] * 25
        disabled = [False] * 25
        # A corner teal has one purple neighbor and two of its three neighbors are revealed.
        for index, name in ((0, "spT"), (1, "spT"), (5, "spT")):
            board[index], disabled[index] = name, True
        self.assertEqual(choose_quest_position(board, disabled), 6)


class TraceSolverTests(unittest.TestCase):
    def test_rules_are_read_from_the_board_text(self):
        rules = parse_trace_rules(TRACE_TEXT)
        self.assertEqual(rules.lengths, {"spT": 4, "spG": 3, "spY": 3})
        self.assertEqual((rules.rare_length, rules.rare_colors), (2, 2))

    def test_partial_run_is_extended_along_its_line(self):
        board = ["spU"] * 25
        disabled = [False] * 25
        for index in (3, 8):
            board[index], disabled[index] = "spT", True
        self.assertIn(choose_trace_position(board, disabled, parse_trace_rules(TRACE_TEXT)), {13, 18})


class SphereKindTests(unittest.TestCase):
    def test_board_texts_are_recognised(self):
        self.assertEqual(sphere_game_kind(SimpleNamespace(content=QUEST_TEXT)), "oq")
        self.assertEqual(sphere_game_kind(SimpleNamespace(content=TRACE_TEXT)), "ot")

    def test_click_costs(self):
        self.assertFalse(sphere_reveal_costs_click("oq", "spP"))
        self.assertTrue(sphere_reveal_costs_click("oq", "spY"))
        self.assertFalse(sphere_reveal_costs_click("ot", "spL"))
        self.assertTrue(sphere_reveal_costs_click("ot", "spB"))


class _FakeBoard:
    """A Mudae board that reveals the hidden answer and ends like Mudae does."""

    def __init__(self, client, kind, truth, paid_limit):
        self.client, self.kind, self.truth, self.paid_limit = client, kind, truth, paid_limit
        self.paid = 0
        self.buttons = [
            SimpleNamespace(index=i, emoji=SimpleNamespace(name="spU"), disabled=False, style=1)
            for i in range(25)
        ]
        self.message = SimpleNamespace(
            id=77, content=QUEST_TEXT if kind == "oq" else TRACE_TEXT,
            components=[SimpleNamespace(children=self.buttons[row * 5:row * 5 + 5]) for row in range(5)],
        )

    def names(self):
        return [button.emoji.name for button in self.buttons]

    async def click(self, button):
        revealed = self.truth[button.index]
        button.emoji = SimpleNamespace(name="spP" if revealed == "sp" else revealed)
        button.disabled = True
        if sphere_reveal_costs_click(self.kind, revealed):
            self.paid += 1
        found_purples = self.names().count("spP")
        if self.kind == "oq" and found_purples >= 3:
            for other in self.buttons:
                if self.truth[other.index] in {"spP", "sp"} and other.emoji.name == "spU":
                    other.emoji = SimpleNamespace(name="sp")
        if self.paid >= self.paid_limit or (self.kind == "oq" and found_purples >= 3):
            for other in self.buttons:
                other.disabled = True
        self.client._sphere_board_update_events[self.message.id].set()
        return True

    async def fetch_message(self, _message_id):
        return self.message


def _runtime(board_factory):
    client = SimpleNamespace(
        is_paused=False, _sphere_board_update_events={}, _sphere_game_bonus_clicks=0,
        oc_reward_priority_order=[], oh_priority_order=[], oh_unknown_explore_clicks=3,
        oc_collect_after_red=True,
    )
    board = board_factory(client)

    async def wait(_seconds):
        return True

    runtime = SphereRuntime(
        client, target_bot_id=1, log=mock.Mock(), send=mock.AsyncMock(return_value=True),
        click=board.click, wait=wait, maintenance_active=lambda: False,
        claim_pending=lambda: False, resolve_channel=mock.AsyncMock(),
        wake_status=lambda: None, ambiguous_error=lambda error: False,
    )
    return runtime, board


class SphereBoardFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_quest_finds_three_purples_within_seven_paid_clicks(self):
        runtime, board = _runtime(lambda client: _FakeBoard(client, "oq", QUEST_BOARD, 7))
        self.assertTrue(await runtime.play_sphere_game(board, board.message, "oq"))
        self.assertEqual(board.names().count("spP"), 3)
        self.assertEqual(board.names().count("sp"), 1)
        self.assertLessEqual(board.paid, 7)

    async def test_trace_finds_every_colored_sphere_with_four_blue_clicks(self):
        runtime, board = _runtime(lambda client: _FakeBoard(client, "ot", TRACE_BOARD, 4))
        self.assertTrue(await runtime.play_sphere_game(board, board.message, "ot"))
        found = [name for name in board.names() if name not in {"spU", "spB"}]
        self.assertEqual(len(found), 14)
        self.assertLessEqual(board.paid, 4)

    async def test_enabled_quest_and_trace_stock_is_played(self):
        client = SimpleNamespace(
            _sphere_games_running=False, sphere_game_counts={"oh": 0, "oc": 0, "oq": 7, "ot": 3},
            _sphere_game_retry_after={}, oh_use_individually=False, is_processing_cycle=False,
            auto_oh_enabled=True, auto_oc_enabled=True, auto_oq_enabled=True, auto_ot_enabled=False,
            _deferred_independent_known_work=False,
        )
        runtime = SphereRuntime(
            client, target_bot_id=1, log=mock.Mock(), send=mock.AsyncMock(), click=mock.AsyncMock(),
            wait=mock.AsyncMock(return_value=True), maintenance_active=lambda: False,
            claim_pending=lambda: False, resolve_channel=mock.AsyncMock(),
            wake_status=lambda: None, ambiguous_error=lambda error: False,
        )
        with mock.patch.object(runtime, "run_sphere_game", mock.AsyncMock(return_value=True)) as run:
            await runtime.run_available_sphere_games("channel")
        run.assert_awaited_once_with("channel", "oq", 7)


if __name__ == "__main__":
    unittest.main()
