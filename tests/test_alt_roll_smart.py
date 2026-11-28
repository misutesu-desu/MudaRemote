"""A5: «Smart» sharing of good rolls between the main and its alts.

``main_claims_alt_rolls_mode = "smart"``: any roll of any account of the
profile that is good for ANY account's own rules is claimed by exactly one
account with a claim (``smart_ranking``), through the existing AltRollBoard
hand-off. Accounts run on their own event loops on their own threads, as in
the app. Names, ids and cards are made up; nothing talks to Discord.
"""

import asyncio
import threading
import time
import unittest
from pathlib import Path

from mudae_core import alt_roll_claim as arc

ROOT = Path(__file__).resolve().parents[1]
MAIN, ALT1, ALT2 = "profile#main", "profile#alt1", "profile#alt2"
ORDER = [MAIN, ALT1, ALT2]
LABELS = {MAIN: "the main", ALT1: "alt 1", ALT2: "alt 2"}


def rank(roller, good=(), can=(), order=ORDER):
    return arc.smart_ranking(roller=roller, order=order, good={key: key in good for key in order},
                             can_claim={key: key in can for key in order}, main_key=MAIN)


class SmartRankingTable(unittest.TestCase):
    """roller main/alt × good-for × claim availability × order."""

    TABLE = [
        # roller, good for, can claim, expected ranking
        (ALT1, {ALT1}, {MAIN, ALT1, ALT2}, [ALT1, MAIN, ALT2]),          # its own good roll: roller first
        (ALT1, {MAIN, ALT1}, {MAIN, ALT1, ALT2}, [MAIN, ALT1, ALT2]),    # good for both: the main first
        (ALT1, {ALT1}, {MAIN, ALT2}, [MAIN, ALT2]),                      # alt has no claim: the main takes it
        (ALT1, {ALT1}, {ALT2}, [ALT2]),                                  # main has no claim either: alt 2
        (ALT1, {MAIN}, {ALT1, ALT2}, [ALT1, ALT2]),                      # good for the main only, it cannot: roller
        (ALT1, {ALT2}, {MAIN, ALT1, ALT2}, [ALT2, MAIN, ALT1]),          # good for alt 2 only: alt 2 first
        (ALT1, {ALT1, ALT2}, {MAIN, ALT1, ALT2}, [ALT1, ALT2, MAIN]),    # among alts the roller first
        (ALT2, {ALT1, ALT2}, {MAIN, ALT1, ALT2}, [ALT2, ALT1, MAIN]),
        (ALT2, {ALT1}, {ALT1, ALT2}, [ALT1, ALT2]),
        (MAIN, {MAIN}, {MAIN, ALT1, ALT2}, [MAIN, ALT1, ALT2]),          # main's own good roll
        (MAIN, {MAIN}, {ALT1, ALT2}, [ALT1, ALT2]),                      # main has no claim: alts in order
        (MAIN, {MAIN}, {ALT2}, [ALT2]),
        (MAIN, {ALT1}, {MAIN, ALT1}, [ALT1, MAIN]),                      # good for alt 1 only: alt 1 first
        (MAIN, {ALT1}, {MAIN}, [MAIN]),                                  # alt 1 has no claim: the main, not lost
        (MAIN, {ALT1, ALT2}, {MAIN, ALT1, ALT2}, [ALT1, ALT2, MAIN]),    # alts in their order
        (MAIN, {MAIN, ALT2}, {MAIN, ALT1, ALT2}, [MAIN, ALT2, ALT1]),
        (ALT1, set(), {MAIN, ALT1, ALT2}, []),                           # good for nobody: nothing
        (MAIN, {MAIN, ALT1}, set(), []),                                 # nobody can: nothing
        (ALT2, {MAIN, ALT1, ALT2}, {ALT1}, [ALT1]),
    ]

    def test_table(self):
        for roller, good, can, expected in self.TABLE:
            with self.subTest(roller=roller, good=sorted(good), can=sorted(can)):
                ranking = rank(roller, good, can)
                self.assertEqual(ranking, expected)
                self.assertTrue(all(key in can for key in ranking), "an account without a claim is never chosen")

    def test_order_decides_among_alts(self):
        order = [MAIN, ALT2, ALT1]  # Account Tokens order changed
        self.assertEqual(rank(MAIN, {ALT1, ALT2}, {ALT1, ALT2}, order=order), [ALT2, ALT1])
        self.assertEqual(rank(MAIN, {MAIN}, {ALT1, ALT2}, order=order), [ALT2, ALT1])

    def test_main_key_defaults_to_the_first_of_the_order(self):
        self.assertEqual(arc.smart_ranking(roller=ALT1, order=ORDER, good={MAIN: True, ALT1: True},
                                           can_claim={MAIN: True, ALT1: True}), [MAIN, ALT1])

    def test_single_account_or_missing_entries(self):
        self.assertEqual(arc.smart_ranking(roller=MAIN, order=[MAIN], good={MAIN: True}, can_claim={MAIN: True}), [MAIN])
        self.assertEqual(arc.smart_ranking(roller=ALT1, order=[], good={ALT1: True}, can_claim={}), [])

    def test_reason_and_line(self):
        good = {MAIN: False, ALT1: True, ALT2: False}
        can = {MAIN: True, ALT1: False, ALT2: True}
        reason = arc.smart_reason(MAIN, roller=ALT1, good=good, can_claim=can, labels=LABELS)
        self.assertEqual(reason, "alt 1 has no claim; good for alt 1, which cannot claim it")
        self.assertEqual(arc.smart_line("Rem", "alt 1", "the main", "alt 1 has no claim"),
                         "⁨Rem⁩ (rolled by alt 1) — claimed by the main (smart: alt 1 has no claim)")
        both = arc.smart_reason(MAIN, roller=ALT1, good={MAIN: True, ALT1: True},
                                can_claim={MAIN: True, ALT1: True}, labels=LABELS)
        self.assertEqual(both, "good for both, the main comes first")
        self.assertEqual(arc.smart_reason(ALT2, roller=ALT1, good={ALT2: True}, can_claim={ALT1: True, ALT2: True},
                                          labels=LABELS), "not good for alt 1")


class SmartModeSettings(unittest.TestCase):
    def test_modes(self):
        self.assertIn(arc.MODE_SMART, arc.MODES)
        self.assertEqual(arc.DEFAULT_MODE, arc.MODE_SMART)
        self.assertEqual(arc.MODE_CHOICES[arc.MODE_SMART], "Smart (whoever can claim takes it, whoever rolled it)")
        self.assertEqual(arc.validate_alt_roll_claim_settings({arc.MODE_SETTING: "smart"}), [])

    def test_either_switch_turns_smart_on_and_old_modes_stay_old(self):
        self.assertTrue(arc.smart_on("smart", True, False))
        self.assertTrue(arc.smart_on("smart", False, True))
        self.assertTrue(arc.smart_on(None, True, False), "default mode")
        self.assertFalse(arc.smart_on("smart", False, False), "both switches off: nothing is shared")
        self.assertFalse(arc.smart_on(arc.MODE_WHEN_ALT_PASSES, True, True))
        self.assertFalse(arc.smart_on(arc.MODE_PREFER_MAIN, True, True))
        # The old modes decide exactly as before.
        self.assertFalse(arc.main_should_be_asked(arc.MODE_WHEN_ALT_PASSES, True))
        self.assertTrue(arc.main_should_be_asked(arc.MODE_WHEN_ALT_PASSES, False))
        self.assertTrue(arc.main_should_be_asked(arc.MODE_PREFER_MAIN, True))


# ---------------------------------------------------------------------------
# Flow model, following mudae_bot.smart_share_own_roll and judge_alt_roll_for_main
# ---------------------------------------------------------------------------

class LoopThread:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    def run(self, coroutine, timeout=30):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout)

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.loop.close()


class Account:
    def __init__(self, key, thread, *, wishlist=(), min_kakera=1000, claim=True, judge_delay=0.0, snipe_delay=0.01):
        self.key = key
        self.thread = thread
        self.wishlist = list(wishlist)
        self.min_kakera = min_kakera
        self.claim_right_available = claim
        self.judge_delay = judge_delay
        self.snipe_delay = snipe_delay

    def good(self, card):
        return arc.card_interest(name=card["name"], wishlist=self.wishlist, kakera=card["kakera"],
                                 min_kakera=self.min_kakera)


class Profile:
    def __init__(self, test, **accounts):
        self.test = test
        self.clicks = []
        self.lock = threading.Lock()
        self.claimed = set()
        self.board = arc.AltRollBoard()
        self.logs = []
        self.accounts = accounts  # key -> Account, in ORDER

    def click(self, who, card):
        with self.lock:
            if card["id"] in self.claimed:
                return False
            self.claimed.add(card["id"])
            self.clicks.append((who, card["id"]))
            return True

    async def judge(self, account, card, roller_label, trusted_why):
        """judge_alt_roll_for_main with a trusted verdict: only the taker's claim and state."""
        if account.judge_delay:
            await asyncio.sleep(account.judge_delay)
        blocker = arc.claim_blocker(claim_available=account.claim_right_available, why=trusted_why)
        if blocker:
            self.board.taker_pass(card["id"], account.key, blocker)
            return
        if not self.board.taker_commit(card["id"], account.key):
            return
        self.logs.append(arc.taken_line(card["name"], roller_label, trusted_why))
        claimed = False
        try:
            await asyncio.sleep(account.snipe_delay)
            claimed = self.click(account.key, card)
        finally:
            self.board.taker_finish(card["id"], account.key, claimed)

    async def roll(self, roller_key, card, decision_timeout=1.0, deadline=None):
        """smart_share_own_roll + the roller's own claim paths after it (on the roller's loop)."""
        roller = self.accounts[roller_key]
        good, whys, can = {}, {}, {}
        for key, account in self.accounts.items():
            good[key], whys[key] = account.good(card)
            can[key] = account.claim_right_available
        ranking = arc.smart_ranking(roller=roller_key, order=list(self.accounts), good=good, can_claim=can,
                                    main_key=MAIN)
        own_rules = good[roller_key] and can[roller_key]
        if not ranking:
            return None, ranking
        if ranking[0] == roller_key and good[roller_key]:
            self.click(roller_key, card)  # its own rules
            return roller_key, ranking
        takers = []
        for key in ranking:
            if key == roller_key and good[roller_key]:
                break
            takers.append(key)
        first_why = next(whys[key] for key in self.accounts if good[key])

        def start(key):
            account = self.accounts[key]
            why = whys[key] if good[key] else first_why
            asyncio.run_coroutine_threadsafe(self.judge(account, card, LABELS[roller_key], why), account.thread.loop)
            return True

        async def sleep(seconds):
            await asyncio.sleep(seconds)
            return True

        state, taker = await self.board.offer_in_turn(
            card["id"], offerer_key=roller_key, offerer_label=LABELS[roller_key], card=card["name"], takers=takers,
            start=start, sleep=sleep, candidates=[key for key in self.accounts if key != roller_key],
            decision_timeout=decision_timeout, result_timeout=2.0, step=0.01, deadline=deadline)
        if state == arc.CLAIMED:
            reason = arc.smart_reason(taker, roller=roller_key, good=good, can_claim=can, labels=LABELS)
            self.logs.append(arc.smart_line(card["name"], LABELS[roller_key], LABELS[taker], reason))
            return taker, ranking
        if state == arc.PASSED and own_rules and not self.board.blocks_claim(card["id"], roller_key):
            self.click(roller_key, card)  # everyone before it passed: its own rules
            return roller_key, ranking
        return None, ranking


class SmartFlows(unittest.TestCase):
    def setUp(self):
        self.threads = {key: LoopThread() for key in ORDER}

    def tearDown(self):
        for thread in self.threads.values():
            thread.stop()

    def profile(self, main=None, alt1=None, alt2=None):
        made = {}
        for key, kwargs in ((MAIN, main), (ALT1, alt1), (ALT2, alt2)):
            made[key] = Account(key, self.threads[key], **(kwargs or {}))
        return Profile(self, **{key: made[key] for key in ORDER})

    def roll(self, profile, roller, card, **kwargs):
        return self.threads[roller].run(profile.roll(roller, card, **kwargs))

    def settle(self):
        for thread in self.threads.values():
            thread.run(asyncio.sleep(0.05))

    def test_alt_rolls_alt_has_no_claim_main_claims(self):
        p = self.profile(main={}, alt1={"wishlist": ["rem"], "claim": False}, alt2={"claim": False})
        taker, _ = self.roll(p, ALT1, {"id": 1, "name": "Rem", "kakera": 40})
        self.settle()
        self.assertEqual(taker, MAIN)
        self.assertEqual(p.clicks, [(MAIN, 1)])
        self.assertIn("⁨Rem⁩ (rolled by alt 1) — claimed by the main "
                      "(smart: alt 1 has no claim; good for alt 1, which cannot claim it)", p.logs)

    def test_main_rolls_main_has_no_claim_alt_claims(self):
        p = self.profile(main={"wishlist": ["rem"], "claim": False}, alt1={}, alt2={})
        taker, _ = self.roll(p, MAIN, {"id": 2, "name": "Rem", "kakera": 40})
        self.settle()
        self.assertEqual(taker, ALT1)
        self.assertEqual(p.clicks, [(ALT1, 2)])

    def test_both_can_main_first(self):
        p = self.profile(main={"wishlist": ["rem"]}, alt1={"wishlist": ["rem"]})
        taker, _ = self.roll(p, ALT1, {"id": 3, "name": "Rem", "kakera": 40})
        self.settle()
        self.assertEqual((taker, p.clicks), (MAIN, [(MAIN, 3)]))
        self.assertIn("⁨Rem⁩ (rolled by alt 1) — claimed by the main "
                      "(smart: good for both, the main comes first)", p.logs)

    def test_alt_keeps_its_own_good_roll_when_not_good_for_the_main(self):
        p = self.profile(main={}, alt1={"wishlist": ["rem"]})
        taker, _ = self.roll(p, ALT1, {"id": 4, "name": "Rem", "kakera": 40})
        self.assertEqual((taker, p.clicks), (ALT1, [(ALT1, 4)]))
        self.assertIsNone(p.board.get(4), "nothing offered: its own rules")

    def test_nobody_can_nothing(self):
        p = self.profile(main={"wishlist": ["rem"], "claim": False}, alt1={"claim": False}, alt2={"claim": False})
        taker, ranking = self.roll(p, ALT1, {"id": 5, "name": "Rem", "kakera": 40})
        self.assertEqual((taker, ranking, p.clicks), (None, [], []))
        self.assertIsNone(p.board.get(5))

    def test_good_for_nobody_nothing(self):
        p = self.profile()
        self.assertEqual(self.roll(p, MAIN, {"id": 6, "name": "Nobody", "kakera": 40}), (None, []))
        self.assertEqual(p.clicks, [])

    def test_main_passes_alt_claims_its_own_roll_after(self):
        # Good for both; the main's claim went just before it judged: the alt claims by its own rules.
        p = self.profile(main={"wishlist": ["rem"]}, alt1={"wishlist": ["rem"]})
        original = p.judge  # the roller's ranking sees the main's claim as available …

        async def judge(account, card, roller_label, why):
            if account.key == MAIN:
                account.claim_right_available = False  # … gone by the time it judges
            await original(account, card, roller_label, why)

        p.judge = judge
        taker, _ = self.roll(p, ALT1, {"id": 7, "name": "Rem", "kakera": 40})
        self.settle()
        self.assertEqual((taker, p.clicks), (ALT1, [(ALT1, 7)]))

    def test_main_rolls_good_for_alt_without_claim_main_takes_it(self):
        p = self.profile(main={}, alt1={"wishlist": ["rem"], "claim": False}, alt2={"claim": False})
        taker, _ = self.roll(p, MAIN, {"id": 8, "name": "Rem", "kakera": 40})
        self.settle()
        self.assertEqual((taker, p.clicks), (MAIN, [(MAIN, 8)]), "the main takes it through the same judge")

    def test_alt2_good_alt1_rolls(self):
        p = self.profile(main={}, alt1={}, alt2={"wishlist": ["rem"]})
        taker, _ = self.roll(p, ALT1, {"id": 9, "name": "Rem", "kakera": 40})
        self.settle()
        self.assertEqual((taker, p.clicks), (ALT2, [(ALT2, 9)]))

    def test_exactly_one_click_under_varied_timing(self):
        import random
        rng = random.Random(5)
        for index in range(30):
            p = self.profile(
                main={"wishlist": ["rem"], "claim": rng.random() < 0.6, "judge_delay": rng.uniform(0, 0.03)},
                alt1={"wishlist": ["rem"] if rng.random() < 0.5 else [], "claim": rng.random() < 0.6,
                      "judge_delay": rng.uniform(0, 0.03)},
                alt2={"claim": rng.random() < 0.6, "judge_delay": rng.uniform(0, 0.03)})
            roller = rng.choice(ORDER)
            self.roll(p, roller, {"id": 100 + index, "name": "Rem", "kakera": 40},
                      decision_timeout=rng.uniform(0.0, 0.05))
            self.settle()
            self.assertLessEqual(len(p.clicks), 1, p.clicks)

    def test_deadline_stops_asking_further_takers(self):
        p = self.profile(main={"wishlist": ["rem"], "claim": False}, alt1={"claim": False}, alt2={})
        # alt 1 has no claim in its live state although the roller saw one: it passes; the window is over.
        p.accounts[ALT1].claim_right_available = True
        original = p.judge

        async def judge(account, card, roller_label, why):
            if account.key == ALT1:
                account.claim_right_available = False
            await original(account, card, roller_label, why)

        p.judge = judge
        taker, _ = self.roll(p, MAIN, {"id": 10, "name": "Rem", "kakera": 40}, deadline=time.monotonic() - 1)
        self.settle()
        self.assertEqual((taker, p.clicks), (None, []), "alt 2 is not asked after the claim window")

    def test_candidates_leave_the_roll_to_the_hand_off(self):
        board = arc.AltRollBoard()
        board.open(50, taker_key=MAIN, offerer_key=ALT1, candidates=[MAIN, ALT2])
        self.assertTrue(board.blocks_claim(50, ALT2), "an account not asked yet never snipes it meanwhile")
        self.assertTrue(board.blocks_claim(50, ALT1), "the roller waits")
        self.assertTrue(board.blocks_claim(50, MAIN), "the taker clicks only once it committed")

    def test_roller_offered_to_itself(self):
        board = arc.AltRollBoard()
        board.open(51, taker_key=MAIN, offerer_key=MAIN, candidates=[ALT1])
        self.assertTrue(board.blocks_claim(51, MAIN))
        self.assertTrue(board.taker_commit(51, MAIN))
        self.assertFalse(board.blocks_claim(51, MAIN), "its own judge may click")
        self.assertTrue(board.blocks_claim(51, ALT1))


class SmartWiring(unittest.TestCase):
    def test_bot_hooks(self):
        source = (ROOT / "mudae_bot.py").read_text(encoding="utf-8")
        offer = source[source.index("async def offer_own_roll_to_main"):source.index("async def finish_offer_to_main(")]
        self.assertLess(offer.index("return await smart_share_own_roll(message, background=background)"),
                        offer.index("_alt_claim.main_should_be_asked("))
        to_alts = source[source.index("async def offer_own_roll_to_alts"):source.index("async def offer_leftover_rolls_to_alts")]
        self.assertLess(to_alts.index("smart_share_own_roll(message)"), to_alts.index("main_roll_verdict_for_alts(message)"))
        leftovers = source[source.index("async def offer_leftover_rolls_to_alts"):source.index("async def smart_share_leftovers")]
        self.assertIn("smart_share_leftovers(", leftovers)
        smart = source[source.index("async def smart_share_own_roll"):source.index("async def alt_would_claim_own_roll")]
        self.assertIn("_alt_claim.smart_ranking(", smart)
        self.assertIn("_alt_roll_board.offer_in_turn(", smart)
        self.assertIn("start_alt_roll_judge(", smart, "the existing judge and claim helper: no second system")
        self.assertIn("_best_roll.CLAIM_WINDOW_SECONDS", smart)
        self.assertNotIn("claim_character(", smart)
        self.assertIn("client._account_link.roll_interest = roll_interest_here", source)
        self.assertIn("smart_mode_on()", source[source.index("def alt_handoff_on"):][:400])


if __name__ == "__main__":
    unittest.main()
