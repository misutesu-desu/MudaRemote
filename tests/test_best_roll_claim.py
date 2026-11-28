"""A4.1: «Claim the best roll when nothing meets the minimum» (``claim_best_when_nothing_qualifies``).

A fake monotonic clock drives one profile's round (main + alts); the model
below follows mudae_bot.drive_best_roll_round / claim_round_best_roll: the
same board calls in the same order. Names, ids and values are made up.
"""

import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mudae_core import best_roll_claim as brc
from mudae_core.bot_config import LIVE_CONFIG_ATTRIBUTES, configure_client
from mudae_core.config import validate_preset

ROOT = Path(__file__).resolve().parents[1]
OPTIONS = {"bot_name": "MudaRemote", "claim_emojis": ["c"], "kakera_emojis": ["k"],
           "sphere_emojis": ["s"], "slash_available": True}
PROFILE = "profile-test"
WINDOW_END = brc.CLAIM_WINDOW_SECONDS - brc.CLAIM_SAFETY_MARGIN_SECONDS  # 39 s


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class Profile:
    """The model: accounts with claim state, one driver, a click log."""

    def __init__(self, *, claims=None, policy=True, floor=0, excluded=None):
        self.clock = Clock()
        self.board = brc.BestRollBoard()
        self.claims = dict(claims or {"main": True, "alt 1": True})
        self.policy = policy
        self.floor = floor
        self.excluded = dict(excluded or {})
        self.rolling = set()
        self.clicks = []
        self.logs = []
        self.ids = 0

    def roll(self, roller, card, kakera, *, qualifies=False):
        self.ids += 1
        if qualifies:
            self.board.mark_qualified(PROFILE, f"{card} met the claim rules", driver_key=roller)
            return self.ids
        self.board.add(PROFILE, brc.Candidate(self.ids, card, kakera, roller, roller, 7, self.clock()),
                       floor=self.floor, driver_key=roller)
        return self.ids

    def step(self):
        decision = self.board.step(
            PROFILE, self.clock(), rolling=bool(self.rolling), policy_allows=self.policy,
            exclude=lambda candidate: self.excluded.get(candidate.message_id),
        )
        if decision.kind == "let_go":
            self.logs.append(brc.let_go_line(decision.candidate.card, decision.candidate.kakera))
        elif decision.kind == "below_floor":
            self.logs.append(brc.below_floor_line(decision.candidate.card, decision.candidate.kakera, self.floor))
        elif decision.kind == "claim":
            candidate = decision.candidate
            order = brc.claimer_order(candidate.roller_key, "main", ["alt 1", "alt 2"])
            chosen = brc.choose_claimer(order, lambda key: None if self.claims.get(key) else "has no claim now")
            if chosen is None:
                self.logs.append(brc.nobody_line(candidate.card, candidate.kakera, "no account has a claim"))
                self.board.finish(PROFILE, False, "nobody")
            else:
                self.clicks.append((chosen, candidate.card))
                self.logs.append(chosen + ": " + brc.claiming_line(candidate.card, candidate.kakera, candidate.roller_label))
                self.board.finish(PROFILE, True)
        return decision

    def run(self, seconds, step=0.5):
        """Advance the clock, stepping like the driver; returns the decisions that did something."""
        done = []
        end = self.clock.now + seconds
        while self.clock.now < end:
            decision = self.step()
            if decision.kind not in ("wait", "idle"):
                done.append(decision)
            self.clock.now += step
        return done


class RoundTests(unittest.TestCase):
    def test_round_end_claims_the_best_roll(self):
        p = Profile()
        p.rolling = {"main"}
        p.roll("main", "Low One", 40)
        p.clock.now += 2
        p.roll("main", "Best One", 90)
        p.clock.now += 2
        p.roll("main", "Mid One", 60)
        p.rolling = set()
        p.run(5)
        self.assertEqual(p.clicks, [("main", "Best One")])
        self.assertIn("main: nothing met the minimum this round — claiming the best roll, ⁨Best One⁩ (90 ka), "
                      "rolled by the main", p.logs)
        self.assertEqual(p.board.state(PROFILE), brc.DONE)

    def test_candidate_expiring_mid_batch_is_let_go_and_next_best_tracked(self):
        p = Profile()
        p.rolling = {"main"}
        p.roll("main", "Early Best", 120)
        p.clock.now += 1
        p.roll("main", "Later", 50)
        # The batch is still running when «Early Best» reaches 39 s: a later roll may beat it.
        decisions = p.run(WINDOW_END)
        self.assertEqual([d.kind for d in decisions], ["let_go"])
        self.assertIn("let ⁨Early Best⁩ (120 ka) go: expired", p.logs[0])
        p.rolling = set()
        p.run(5)
        self.assertEqual(p.clicks, [("main", "Later")])

    def test_better_roll_arriving_later_wins(self):
        p = Profile()
        p.rolling = {"main", "alt 1"}
        p.roll("main", "First", 70)
        p.clock.now += 10
        p.roll("alt 1", "Better", 95)
        p.rolling = set()
        p.run(5)
        self.assertEqual(p.clicks, [("alt 1", "Better")])

    def test_expiring_best_is_claimed_when_nobody_rolls_any_more(self):
        p = Profile()
        p.rolling = {"main"}
        p.roll("main", "Only", 80)
        p.rolling = set()
        # settle (3 s) ends first and claims; same result as claiming at expiry
        p.run(1)
        self.assertEqual(p.clicks, [])
        p.run(3)
        self.assertEqual(p.clicks, [("main", "Only")])

    def test_expiry_claim_while_settling(self):
        board = brc.BestRollBoard(settle_seconds=60)
        clock = Clock()
        board.add(PROFILE, brc.Candidate(1, "Old", 80, "main", "main", 7, clock() - WINDOW_END))
        decision = board.step(PROFILE, clock(), rolling=False, policy_allows=True)
        self.assertEqual((decision.kind, decision.reason), ("claim", "about to expire"))

    def test_qualifying_roll_stands_the_round_down(self):
        p = Profile()
        p.rolling = {"main"}
        p.roll("main", "Cheap", 30)
        p.roll("alt 1", "Wished", 10, qualifies=True)
        p.rolling = set()
        decisions = p.run(5)
        self.assertEqual([d.kind for d in decisions], ["stand_down"])
        self.assertEqual(p.clicks, [])

    def test_a_claim_of_the_profile_stands_the_round_down(self):
        p = Profile()
        p.rolling = {"main"}
        p.roll("main", "Cheap", 30)
        self.assertTrue(p.board.note_claimed(PROFILE))
        p.rolling = set()
        p.run(5)
        self.assertEqual(p.clicks, [])

    def test_policy_last_round_not_now(self):
        p = Profile(policy=False)
        p.roll("main", "Cheap", 30)
        decisions = p.run(5)
        self.assertEqual([d.kind for d in decisions], ["not_now"])
        self.assertEqual(p.clicks, [])

    def test_policy_every_round(self):
        self.assertEqual(brc.normalize_when("every round"), brc.WHEN_EVERY_ROUND)
        self.assertEqual(brc.normalize_when(None), brc.WHEN_LAST_ROUND)
        p = Profile(policy=True)
        p.roll("main", "Cheap", 30)
        p.run(5)
        self.assertEqual(p.clicks, [("main", "Cheap")])

    def test_floor(self):
        p = Profile(floor=100)
        p.roll("main", "Below", 99)
        p.roll("alt 1", "Also Below", 50)
        decisions = p.run(5)
        self.assertEqual([d.kind for d in decisions], ["below_floor"])
        self.assertIn("skipped ⁨Below⁩ (99 ka): below your floor of 100", p.logs[0])
        self.assertEqual(p.clicks, [])
        p2 = Profile(floor=100)
        p2.roll("main", "Below", 99)
        p2.roll("alt 1", "Above", 100)
        p2.run(5)
        self.assertEqual(p2.clicks, [("alt 1", "Above")])

    def test_floor_zero_means_any_value(self):
        p = Profile(floor=0)
        p.roll("main", "Zero", 0)
        p.run(5)
        self.assertEqual(p.clicks, [("main", "Zero")])

    def test_tie_goes_to_the_newest(self):
        p = Profile()
        p.roll("main", "Older", 80)
        p.clock.now += 1
        p.roll("alt 1", "Newer", 80)
        p.run(5)
        self.assertEqual(p.clicks, [("alt 1", "Newer")])

    def test_roller_without_claim_the_main_claims(self):
        p = Profile(claims={"main": True, "alt 1": False, "alt 2": True})
        p.roll("alt 1", "Alt Card", 60)
        p.run(5)
        self.assertEqual(p.clicks, [("main", "Alt Card")])
        self.assertIn("rolled by alt 1", p.logs[-1])

    def test_roller_and_main_without_claim_the_next_alt_claims(self):
        p = Profile(claims={"main": False, "alt 1": False, "alt 2": True})
        p.roll("alt 1", "Alt Card", 60)
        p.run(5)
        self.assertEqual(p.clicks, [("alt 2", "Alt Card")])

    def test_nothing_claimable_nothing_happens(self):
        p = Profile(claims={"main": False, "alt 1": False})
        p.roll("main", "Card", 60)
        p.run(5)
        self.assertEqual(p.clicks, [])
        self.assertIn("no account has a claim", p.logs[-1])
        # excluded (taken by another account meanwhile) → nothing
        p2 = Profile(excluded={1: "someone is already claiming it"})
        p2.roll("main", "Taken", 60)
        decisions = p2.run(5)
        self.assertEqual([d.kind for d in decisions], ["empty"])
        self.assertEqual(p2.clicks, [])

    def test_excluded_best_falls_back_to_next(self):
        p = Profile(excluded={2: "it is already claimed"})
        p.roll("main", "Second", 50)
        p.roll("main", "Owned", 90)
        p.run(5)
        self.assertEqual(p.clicks, [("main", "Second")])

    def test_exactly_one_claim_action_per_round(self):
        p = Profile()
        for value in (10, 20, 30, 40):
            p.roll("main", f"C{value}", value)
        decisions = p.run(10)
        self.assertEqual(len(p.clicks), 1)
        self.assertEqual(sum(1 for d in decisions if d.kind == "claim"), 1)
        # a second step after the decision does nothing
        self.assertEqual(p.board.step(PROFILE, p.clock(), rolling=False, policy_allows=True).kind, "idle")
        # commit is single: a concurrent step during «claiming» cannot claim again
        board = brc.BestRollBoard(settle_seconds=0)
        board.add(PROFILE, brc.Candidate(1, "A", 5, "main", "main", 7, 0.0))
        board.add(PROFILE, brc.Candidate(2, "B", 4, "main", "main", 7, 0.0))
        self.assertEqual(board.step(PROFILE, 1.0, rolling=False, policy_allows=True).kind, "claim")
        self.assertEqual(board.step(PROFILE, 1.5, rolling=False, policy_allows=True).kind, "idle")

    def test_new_round_after_done(self):
        p = Profile()
        p.roll("main", "One", 10)
        p.run(5)
        first = p.board.round_number(PROFILE)
        p.roll("main", "Two", 20)
        self.assertEqual(p.board.round_number(PROFILE), first + 1)
        p.run(5)
        self.assertEqual(p.clicks, [("main", "One"), ("main", "Two")])

    def test_one_driver_per_round(self):
        board = brc.BestRollBoard()
        self.assertTrue(board.add(PROFILE, brc.Candidate(1, "A", 1, "main", "main", 7, 0.0), driver_key="main"))
        self.assertFalse(board.add(PROFILE, brc.Candidate(2, "B", 1, "alt 1", "alt 1", 7, 0.0), driver_key="alt 1"))
        self.assertFalse(board.mark_qualified(PROFILE, driver_key="alt 1"))


class LastRoundTests(unittest.TestCase):
    def test_last_round_detection(self):
        now = datetime.datetime(2026, 11, 28, 12, 0, tzinfo=datetime.timezone.utc)
        reset = now + datetime.timedelta(minutes=50)
        minute = datetime.timedelta(minutes=1)
        # next batches start after the claim reset → last round
        self.assertTrue(brc.is_last_round(now=now, claim_reset_at=reset,
                                          next_batches=[(now + 60 * minute, minute), (now + 61 * minute, minute)]))
        # one account's next batch finishes before the reset → not the last round
        self.assertFalse(brc.is_last_round(now=now, claim_reset_at=reset,
                                           next_batches=[(now + 60 * minute, minute), (now + 30 * minute, minute)]))
        # a batch starting just before the reset but finishing after it → last round
        self.assertTrue(brc.is_last_round(now=now, claim_reset_at=reset,
                                          next_batches=[(now + 49 * minute, 2 * minute)]))
        # unknown reset or unknown batch start → not «last» (no claim)
        self.assertFalse(brc.is_last_round(now=now, claim_reset_at=None, next_batches=[]))
        self.assertFalse(brc.is_last_round(now=now, claim_reset_at=reset, next_batches=[(None, minute)]))
        # single account, no further batch known before the reset
        self.assertTrue(brc.is_last_round(now=now, claim_reset_at=reset, next_batches=[]))

    def test_claimer_order(self):
        self.assertEqual(brc.claimer_order("alt 2", "main", ["alt 1", "alt 2"]), ["alt 2", "main", "alt 1"])
        self.assertEqual(brc.claimer_order("main", "main", []), ["main"])


class SettingTests(unittest.TestCase):
    def test_defaults_off_and_validation(self):
        client = SimpleNamespace(command_prefix="!", hourly_tu_refresh=False, preset_name="P")
        configure_client(client, "P", {"token": "made-up", "channel_id": 1}, **OPTIONS)
        self.assertFalse(client.claim_best_when_nothing_qualifies)
        self.assertEqual(client.claim_best_when, brc.WHEN_LAST_ROUND)
        self.assertEqual(client.claim_best_min_kakera, 0)
        configure_client(client, "P", {"token": "made-up", "channel_id": 1, "claim_best_when_nothing_qualifies": True,
                                  "claim_best_when": "every round", "claim_best_min_kakera": 75}, **OPTIONS)
        self.assertTrue(client.claim_best_when_nothing_qualifies)
        self.assertEqual(client.claim_best_when, brc.WHEN_EVERY_ROUND)
        self.assertEqual(client.claim_best_min_kakera, 75)
        for key in (brc.SETTING, brc.WHEN_SETTING, brc.FLOOR_SETTING):
            self.assertIn(key, LIVE_CONFIG_ATTRIBUTES)
        self.assertEqual(brc.validate_best_roll_settings({"claim_best_when": "sometimes"})[:1],
                         ["«Claim the best roll» timing must be «last round» or «every round»."])
        self.assertTrue(brc.validate_best_roll_settings({"claim_best_min_kakera": -1}))
        self.assertEqual(brc.validate_best_roll_settings({"claim_best_when": "last round", "claim_best_min_kakera": 0}), [])
        errors = validate_preset({"claim_best_when": "sometimes"})
        self.assertTrue(any("Claim the best roll" in str(error) for error in errors))

    def test_window_constants(self):
        self.assertEqual(brc.CLAIM_WINDOW_SECONDS, 45)
        self.assertEqual(brc.claim_deadline(100.0), 139.0)

    def test_android_schema_and_editor(self):
        with tempfile.TemporaryDirectory() as out:
            subprocess.run([sys.executable, str(ROOT / "android" / "generate_schema.py"), str(ROOT), out],
                           check=True, capture_output=True)
            with open(os.path.join(out, "android_schema.json"), encoding="utf-8") as handle:
                settings = json.load(handle)["fields"]
        self.assertEqual(settings["claim_best_when_nothing_qualifies"]["type"], "boolean")
        self.assertIs(settings["claim_best_when_nothing_qualifies"]["default"], False)
        self.assertEqual(settings["claim_best_when"]["default"], "last round")
        self.assertEqual(set(settings["claim_best_when"]["choices"]), {"last round", "every round"})
        self.assertEqual(settings["claim_best_min_kakera"]["default"], 0)
        for key in ("claim_best_when_nothing_qualifies", "claim_best_when", "claim_best_min_kakera"):
            self.assertEqual(settings[key].get("section"), "Claiming")

    def test_bot_wiring_present(self):
        source = (ROOT / "mudae_bot.py").read_text(encoding="utf-8")
        self.assertIn("note_best_roll(message, embed.author.name.strip(), k_val, qualifies, is_avoided)", source)
        self.assertIn("client._account_link.claim_best_roll = claim_best_roll_here", source)
        # never $rt for this feature
        start = source.index("async def claim_best_roll_here(")
        body = source[start:source.index("client._account_link.claim_best_roll = claim_best_roll_here")]
        self.assertIn("allow_rt=False", body)
        self.assertNotIn("send_rt_command", body)


if __name__ == "__main__":
    unittest.main()
