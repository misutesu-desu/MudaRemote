"""Main/Side hand-off: a Side rolls for its Main when the Main found nothing.

The fakes below stand in for running accounts (the real handles live in
mudae_bot.py and wrap a Discord client). All ids are made up.
"""

import asyncio
import unittest

from mudae_core.coordinator import ClaimCoordinator, SideRollCoordinator


class FakeMain:
    def __init__(self, key="main-1", name="Main", profile_id="pmain", channel_id=111,
                 enabled=True, max_sides=1, leftovers=False, user_id=9001):
        self.key = key
        self.name = name
        self.profile_id = profile_id
        self.account_index = 1
        self.role = "main"
        self.main_profile_id = ""
        self.main_account_id = ""
        self.side_order = 1
        self.channel_id = channel_id
        self.user_id = user_id
        self.claim_available = True
        self.reset_key = "reset-1"
        self.enabled = enabled
        self.max_sides = max_sides
        self.leftovers = leftovers
        # Cards the Main's own rules would claim (by name).
        self.wants = set()
        self.claim_coordinator = ClaimCoordinator()

    def options(self):
        return {"enabled": self.enabled, "max_sides": self.max_sides, "leftovers": self.leftovers}

    def claim_open(self):
        return self.claim_available

    def claim_reset_key(self):
        return self.reset_key

    def is_ready(self):
        return True

    def is_paused(self):
        return False

    def is_rolling(self):
        return False

    def rolls_left(self):
        return 0

    def judge(self, handoff, message_id, card):
        """What the Main's on_message does with a card a Side rolled."""
        claimed = False
        if self.claim_available and card in self.wants and self.claim_coordinator.reserve_claim(message_id):
            self.claim_coordinator.mark_completed(message_id)
            self.claim_available = False
            claimed = True
        handoff.record_main_decision(message_id, claimed, card if claimed else None)
        return claimed


class FakeSide:
    def __init__(self, main, key, name, *, rolls=("Rem",), rolls_left=None, order=1,
                 channel_id=None, paused=False, rolling=False, fails=False, user_id=None,
                 profile_id=None, legacy_main_id=""):
        self.main = main
        self.key = key
        self.name = name
        self.profile_id = profile_id or "p" + key
        self.account_index = 1
        self.role = "side"
        self.main_profile_id = "" if legacy_main_id else main.profile_id
        self.main_account_id = legacy_main_id
        self.side_order = order
        self.channel_id = main.channel_id if channel_id is None else channel_id
        self.user_id = user_id or (abs(hash(key)) % 10000 + 10)
        self.cards = list(rolls)
        self._rolls_left = len(self.cards) if rolls_left is None else rolls_left
        self.paused = paused
        self.rolling = rolling
        self.fails = fails
        self.sent = []
        self.self_claimed = []
        self.wants = set()
        self.claim_available = True

    def is_ready(self):
        return True

    def is_paused(self):
        return self.paused

    def is_rolling(self):
        return self.rolling

    def rolls_left(self):
        return self._rolls_left

    async def run_handoff_rolls(self, handoff):
        if self.fails:
            raise RuntimeError("gateway closed")
        for index, card in enumerate(self.cards):
            if handoff.should_stop() or self._rolls_left <= 0:
                break
            self._rolls_left -= 1
            message_id = "{}-{}".format(self.key, index)
            self.sent.append(card)
            assert handoff.is_side_roll(self.user_id, self.channel_id)
            handoff.note_side_roll()
            self.main.judge(handoff, message_id, card)
            # Leftovers: only after the Main passed, with the Side's own rules.
            if (handoff.claim_leftovers and handoff.main_decision(message_id) is False
                    and self.claim_available and card in self.wants
                    and self.main.claim_coordinator.reserve_claim(message_id)):
                self.claim_available = False
                self.self_claimed.append(card)
            await asyncio.sleep(0)


def run(coro):
    return asyncio.run(coro)


class SideRollHandoffTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = SideRollCoordinator()
        self.lines = []

    def log(self, message, level="INFO"):
        self.lines.append((level, message))

    def handoff(self, main, **kwargs):
        return run(self.coordinator.run_for_main(main, log=self.log, **kwargs))

    def register(self, *handles):
        for handle in handles:
            self.coordinator.register(handle)

    def test_main_with_no_claim_asks_its_side_and_claims_from_the_side_roll(self):
        main = FakeMain()
        main.wants = {"Rem"}
        side = FakeSide(main, "side-a", "جانبي", rolls=("Ram", "Rem", "Emilia"))
        self.register(main, side)

        summary = self.handoff(main)

        self.assertEqual(summary["asked"], ["جانبي"])
        self.assertEqual(summary["claimed"], "Rem")
        self.assertFalse(main.claim_available)
        # The Side stopped rolling as soon as the Main claimed.
        self.assertEqual(side.sent, ["Ram", "Rem"])
        self.assertEqual(side.self_claimed, [])
        self.assertIn(("CLAIM", "Main found nothing — asking side ⁨جانبي⁩ to roll"), self.lines)
        self.assertIsNone(self.coordinator.handoff_for_main(main.key))
        self.assertIsNone(self.coordinator.handoff_for_side(side.key))

    def test_option_off_does_nothing(self):
        main = FakeMain(enabled=False)
        side = FakeSide(main, "side-a", "Alt")
        self.register(main, side)
        summary = self.handoff(main)
        self.assertEqual(summary, {"asked": [], "claimed": None, "reason": "off"})
        self.assertEqual(side.sent, [])
        self.assertEqual(self.lines, [])

    def test_used_claim_means_no_handoff(self):
        main = FakeMain()
        main.claim_available = False
        side = FakeSide(main, "side-a", "Alt")
        self.register(main, side)
        self.assertEqual(self.handoff(main)["reason"], "claim-used")
        self.assertEqual(side.sent, [])

    def test_side_without_rolls_is_skipped_and_the_next_side_is_used(self):
        main = FakeMain(max_sides=2)
        main.wants = {"Rem"}
        empty = FakeSide(main, "side-a", "Empty", rolls_left=0, order=1)
        second = FakeSide(main, "side-b", "Second", rolls=("Rem",), order=2)
        self.register(main, second, empty)

        summary = self.handoff(main)

        self.assertEqual(summary["asked"], ["Second"])
        self.assertEqual(summary["claimed"], "Rem")
        self.assertEqual(empty.sent, [])
        self.assertTrue(any("⁨Empty⁩ skipped: has no rolls left" in line for _, line in self.lines))

    def test_second_side_rolls_when_the_first_found_nothing(self):
        main = FakeMain(max_sides=2)
        main.wants = {"Rem"}
        first = FakeSide(main, "side-a", "First", rolls=("Ram",), order=1)
        second = FakeSide(main, "side-b", "Second", rolls=("Rem",), order=2)
        self.register(main, first, second)

        summary = self.handoff(main)

        self.assertEqual(summary["asked"], ["First", "Second"])
        self.assertEqual(summary["claimed"], "Rem")
        self.assertEqual(first.sent, ["Ram"])
        self.assertEqual(second.sent, ["Rem"])

    def test_max_sides_per_reset_is_respected_across_calls(self):
        main = FakeMain(max_sides=1)
        first = FakeSide(main, "side-a", "First", rolls=("Ram",), order=1)
        second = FakeSide(main, "side-b", "Second", rolls=("Rem",), order=2)
        self.register(main, first, second)

        self.assertEqual(self.handoff(main)["asked"], ["First"])
        self.assertEqual(second.sent, [])
        # Another batch ends in the same claim window: the limit still holds.
        self.assertEqual(self.handoff(main)["reason"], "limit")
        self.assertEqual(second.sent, [])
        # After the claim reset a new window starts.
        main.reset_key = "reset-2"
        self.assertEqual(self.handoff(main)["asked"], ["Second"])

    def test_stops_when_the_main_claim_window_resets_mid_roll(self):
        main = FakeMain(max_sides=3)
        first = FakeSide(main, "side-a", "First", rolls=("A", "B", "C"))
        second = FakeSide(main, "side-b", "Second", rolls=("D",), order=2)
        original_judge = main.judge

        def judge_and_reset(handoff, message_id, card):
            result = original_judge(handoff, message_id, card)
            if card == "A":
                main.reset_key = "reset-2"
            return result

        main.judge = judge_and_reset
        self.register(main, first, second)

        summary = self.handoff(main)

        self.assertEqual(first.sent, ["A"])
        self.assertEqual(second.sent, [])
        self.assertEqual(summary["reason"], "claim-window-changed")

    def test_a_failing_side_does_not_stop_the_main_or_the_next_side(self):
        main = FakeMain(max_sides=2)
        main.wants = {"Rem"}
        broken = FakeSide(main, "side-a", "Broken", fails=True, order=1)
        good = FakeSide(main, "side-b", "Good", rolls=("Rem",), order=2)
        self.register(main, broken, good)

        summary = self.handoff(main)

        self.assertEqual(summary["asked"], ["Broken", "Good"])
        self.assertEqual(summary["claimed"], "Rem")
        self.assertTrue(any(level == "WARN" and "⁨Broken⁩ could not roll" in line
                            for level, line in self.lines))
        self.assertIsNone(self.coordinator.handoff_for_side(broken.key))

    def test_ineligible_sides_paused_rolling_or_other_channel(self):
        main = FakeMain(max_sides=5)
        paused = FakeSide(main, "s1", "Paused", paused=True)
        busy = FakeSide(main, "s2", "Busy", rolling=True)
        elsewhere = FakeSide(main, "s3", "Elsewhere", channel_id=222)
        self.register(main, paused, busy, elsewhere)

        summary = self.handoff(main)

        self.assertEqual(summary["asked"], [])
        self.assertEqual(summary["reason"], "no-side")
        text = " ".join(line for _, line in self.lines)
        self.assertIn("is paused", text)
        self.assertIn("is in its own rolling session", text)
        self.assertIn("is not in this channel", text)
        self.assertIn("no side account can roll", text)

    def test_side_never_claims_for_itself_unless_leftovers_is_on(self):
        main = FakeMain(leftovers=False)
        side = FakeSide(main, "side-a", "Alt", rolls=("Ram",))
        side.wants = {"Ram"}
        self.register(main, side)
        self.handoff(main)
        self.assertEqual(side.self_claimed, [])

        main2 = FakeMain(key="main-2", profile_id="pmain2", leftovers=True)
        side2 = FakeSide(main2, "side-b", "Alt2", rolls=("Ram",))
        side2.wants = {"Ram"}
        coordinator = SideRollCoordinator()
        coordinator.register(main2)
        coordinator.register(side2)
        run(coordinator.run_for_main(main2, log=self.log))
        self.assertEqual(side2.self_claimed, ["Ram"])
        self.assertTrue(main2.claim_available)

    def test_leftovers_never_take_a_card_the_main_claimed(self):
        main = FakeMain(leftovers=True)
        main.wants = {"Rem"}
        side = FakeSide(main, "side-a", "Alt", rolls=("Rem",))
        side.wants = {"Rem"}
        self.register(main, side)
        self.handoff(main)
        self.assertFalse(main.claim_available)
        self.assertEqual(side.self_claimed, [])

    def test_legacy_main_account_id_links_a_side_by_discord_user_id(self):
        main = FakeMain(user_id=424242)
        main.wants = {"Rem"}
        side = FakeSide(main, "side-a", "Legacy", rolls=("Rem",), legacy_main_id="424242")
        self.register(main, side)
        self.assertIs(self.coordinator.resolve_main(side), main)
        self.assertEqual(self.handoff(main)["claimed"], "Rem")

    def test_sides_of_another_main_or_extra_accounts_are_not_used(self):
        main = FakeMain()
        other_main = FakeMain(key="main-2", profile_id="pother")
        foreign = FakeSide(other_main, "side-x", "Foreign")
        self.register(main, other_main, foreign)
        self.assertEqual(self.coordinator.sides_for(main), [])
        self.assertEqual(self.coordinator.sides_for(other_main), [foreign])
        # Only a profile's first account is its Main.
        second_account = FakeMain(key="main-1b", profile_id="pmain")
        second_account.account_index = 2
        side = FakeSide(main, "side-a", "Alt")
        self.register(second_account, side)
        self.assertIs(self.coordinator.resolve_main(side), main)

    def test_unregistering_a_side_closes_its_handoff(self):
        main = FakeMain()
        side = FakeSide(main, "side-a", "Alt")
        self.register(main, side)
        seen = {}

        async def roll(handoff):
            seen["handoff"] = handoff
            self.coordinator.unregister(side)
            self.assertTrue(handoff.should_stop())

        side.run_handoff_rolls = roll
        self.handoff(main)
        self.assertTrue(seen["handoff"].closed)
        self.assertEqual(self.coordinator.accounts(), [main])

    def test_a_hanging_side_is_abandoned_and_the_next_side_rolls(self):
        main = FakeMain(max_sides=2)
        main.wants = {"Rem"}
        hung = FakeSide(main, "side-a", "Hung", order=1)
        good = FakeSide(main, "side-b", "Good", rolls=("Rem",), order=2)

        async def never_finishes(handoff):
            await asyncio.Event().wait()

        hung.run_handoff_rolls = never_finishes
        self.register(main, hung, good)
        summary = self.handoff(main, timeout_seconds=0.05)
        self.assertEqual(summary["asked"], ["Hung", "Good"])
        self.assertEqual(summary["claimed"], "Rem")
        self.assertTrue(any("took too long" in line for _, line in self.lines))

    def test_a_side_that_disconnects_mid_roll_releases_the_main_at_once(self):
        main = FakeMain()
        side = FakeSide(main, "side-a", "Gone")

        async def disconnect(handoff):
            self.coordinator.unregister(side)
            await asyncio.Event().wait()

        side.run_handoff_rolls = disconnect
        self.register(main, side)
        summary = self.handoff(main, timeout_seconds=30)
        self.assertEqual(summary["asked"], ["Gone"])
        self.assertTrue(any("stopped while rolling" in line for _, line in self.lines))

    def test_handoff_rejects_rolls_from_other_users_or_channels(self):
        main = FakeMain()
        side = FakeSide(main, "side-a", "Alt", user_id=5555)
        self.register(main, side)
        captured = {}

        async def roll(handoff):
            captured["side"] = handoff.is_side_roll(5555, main.channel_id)
            captured["other_user"] = handoff.is_side_roll(6666, main.channel_id)
            captured["other_channel"] = handoff.is_side_roll(5555, 999)
            captured["active"] = self.coordinator.handoff_for_main(main.key) is handoff

        side.run_handoff_rolls = roll
        self.handoff(main)
        self.assertEqual(captured, {"side": True, "other_user": False, "other_channel": False, "active": True})


if __name__ == "__main__":
    unittest.main()
