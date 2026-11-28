"""A2: «Main claims good rolls made by its alts» (``main_claims_alt_rolls``).

The alt offers its own roll to the main of its profile; the main judges it
with its OWN rules and live claim state and claims it, or passes and the alt
follows its own rules. One decision point (``AltRollBoard``): never both click.

The two accounts are simulated with two real event loops on two threads, the
way the app runs main and alts in one process. Names, ids and messages are
made up; nothing talks to Discord.
"""

import asyncio
import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from mudae_core import alt_roll_claim as arc
from mudae_core.activity_events import ActivityClassifier
from mudae_core.bot_config import LIVE_CONFIG_ATTRIBUTES, configure_client
from mudae_core.config import validate_preset

ROOT = Path(__file__).resolve().parents[1]
OPTIONS = {"bot_name": "MudaRemote", "claim_emojis": ["c"], "kakera_emojis": ["k"],
           "sphere_emojis": ["s"], "slash_available": True}


# ---------------------------------------------------------------------------
# A small model of the two accounts, following mudae_bot.offer_own_roll_to_main
# (alt) and judge_alt_roll_for_main (main): same board calls, same order.
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
    def __init__(self, key, *, wishlist=(), min_kakera=100, claim=True, paused=False, key_limited=False,
                 rolling=False, lurking=False, snipe_delay=0.05, judge_delay=0.0, clicks=None, lock=None):
        self.key = key
        self.wishlist = list(wishlist)
        self.min_kakera = min_kakera
        self.claim_right_available = claim
        self.paused = paused
        self.key_limited = key_limited
        self.rolling = rolling
        self.lurking = lurking
        self.snipe_delay = snipe_delay
        self.judge_delay = judge_delay
        self.clicks = clicks if clicks is not None else []
        self.lock = lock or threading.Lock()
        self.claimed = set()   # stands for the process-wide ClaimCoordinator

    def interest(self, card):
        return arc.card_interest(name=card["name"], wishlist=self.wishlist, kakera=card["kakera"],
                                 min_kakera=self.min_kakera)

    def would_claim(self, card):
        wanted, _ = self.interest(card)
        return wanted and self.claim_right_available and not self.paused

    def click(self, who, card):
        with self.lock:
            if card["id"] in self.claimed:
                return False
            self.claimed.add(card["id"])
            self.clicks.append((who, card["id"]))
            return True


async def main_judge(board, main, card, alt_label="alt 1", logs=None):
    """judge_alt_roll_for_main, reduced to its decisions."""
    logs = logs if logs is not None else []
    if main.judge_delay:
        await asyncio.sleep(main.judge_delay)
    wanted, why = main.interest(card)
    if not wanted:
        board.main_pass(card["id"], main.key, why)
        return
    blocker = arc.claim_blocker(paused=main.paused, key_limited=main.key_limited,
                                claim_available=main.claim_right_available, rolling=main.rolling,
                                lurking=main.lurking, why=why)
    if blocker:
        board.main_pass(card["id"], main.key, blocker)
        logs.append(arc.not_taken_line(card["name"], alt_label, blocker))
        return
    if not board.main_commit(card["id"], main.key):
        return
    logs.append(arc.taken_line(card["name"], alt_label, why))
    claimed = False
    try:
        await asyncio.sleep(main.snipe_delay)
        claimed = main.click("main", card)
    finally:
        board.main_finish(card["id"], main.key, claimed)


async def alt_sees_own_roll(board, alt, main, main_thread, card, *, option=True, mode=arc.DEFAULT_MODE,
                            decision_timeout=arc.DECISION_WAIT_SECONDS, result_timeout=5.0, logs=None):
    """offer_own_roll_to_main + the alt's own claim paths after it."""
    logs = logs if logs is not None else []
    left_to_main = None
    if option and arc.main_should_be_asked(mode, alt.would_claim(card)):
        precheck = None
        if main.paused:
            precheck = "is paused"
        elif main.key_limited:
            precheck = "is paused at the key limit"
        elif not main.claim_right_available:
            precheck = "has no claim now"
        if precheck is None and board.open(card["id"], main_key=main.key, alt_key=alt.key, alt_label="alt 1",
                                           card=card["name"]) is not None:
            asyncio.run_coroutine_threadsafe(main_judge(board, main, card, logs=logs), main_thread.loop)

            async def sleep(seconds):
                await asyncio.sleep(seconds)
                return True

            state = await board.wait_for_main(card["id"], alt.key, sleep=sleep, decision_timeout=decision_timeout,
                                              result_timeout=result_timeout, step=0.01)
            left_to_main = state in (arc.CLAIMED, arc.TAKING)
            if left_to_main:
                logs.append(arc.left_line(card["name"]))
    if not left_to_main and alt.would_claim(card):
        alt.click("alt", card)
    return left_to_main


class AltRollClaimHarness(unittest.TestCase):
    def setUp(self):
        self.main_thread = LoopThread()
        self.alt_thread = LoopThread()
        self.board = arc.AltRollBoard()
        self.clicks = []
        self.lock = threading.Lock()
        self.logs = []

    def tearDown(self):
        self.main_thread.stop()
        self.alt_thread.stop()

    def accounts(self, main_kwargs=None, alt_kwargs=None):
        shared = {"clicks": self.clicks, "lock": self.lock}
        main = Account("profile#main", **dict(shared, **(main_kwargs or {})))
        alt = Account("profile#alt1", **dict(shared, **(alt_kwargs or {})))
        alt.claimed = main.claimed = set()
        return main, alt

    def roll(self, main, alt, card, **kwargs):
        return self.alt_thread.run(alt_sees_own_roll(self.board, alt, main, self.main_thread, card,
                                                     logs=self.logs, **kwargs))

    def test_main_takes_a_wishlist_roll_of_the_alt_and_the_alt_does_not_click(self):
        main, alt = self.accounts({"wishlist": ["rem"], "min_kakera": 900}, {"min_kakera": 900})
        left = self.roll(main, alt, {"id": 11, "name": "Rem", "kakera": 40})
        self.assertTrue(left)
        self.assertEqual(self.clicks, [("main", 11)])
        self.assertIn("claiming ⁨Rem⁩ rolled by alt 1 (wishlist)", self.logs)
        self.assertIn("left ⁨Rem⁩ for the main", self.logs)

    def test_main_without_a_claim_alt_follows_its_own_rules(self):
        main, alt = self.accounts({"wishlist": ["rem"], "claim": False}, {"wishlist": ["rem"]})
        left = self.roll(main, alt, {"id": 12, "name": "Rem", "kakera": 40}, mode=arc.MODE_PREFER_MAIN)
        self.assertFalse(left)
        self.assertEqual(self.clicks, [("alt", 12)])

    def test_mode_when_alt_would_not_claim_keeps_the_alts_own_good_roll(self):
        main, alt = self.accounts({"wishlist": ["rem"]}, {"wishlist": ["rem"]})
        self.roll(main, alt, {"id": 13, "name": "Rem", "kakera": 40})
        self.assertEqual(self.clicks, [("alt", 13)])
        self.assertIsNone(self.board.get(13), "nothing offered: the alt keeps it")

    def test_mode_when_alt_would_not_claim_main_takes_what_the_alt_passes_on(self):
        main, alt = self.accounts({"min_kakera": 100}, {"min_kakera": 500})
        self.roll(main, alt, {"id": 14, "name": "Kurumi", "kakera": 300})
        self.assertEqual(self.clicks, [("main", 14)])

    def test_mode_prefer_main_takes_even_what_the_alt_wanted(self):
        main, alt = self.accounts({"wishlist": ["rem"]}, {"wishlist": ["rem"]})
        self.roll(main, alt, {"id": 15, "name": "Rem", "kakera": 40}, mode=arc.MODE_PREFER_MAIN)
        self.assertEqual(self.clicks, [("main", 15)])

    def test_option_off_is_todays_behaviour(self):
        main, alt = self.accounts({"wishlist": ["rem"]}, {"min_kakera": 10})
        self.roll(main, alt, {"id": 16, "name": "Rem", "kakera": 40}, option=False, mode=arc.MODE_PREFER_MAIN)
        self.assertEqual(self.clicks, [("alt", 16)])
        self.assertIsNone(self.board.get(16))
        self.assertFalse(self.board.blocks_claim(16, main.key))

    def test_main_paused_or_key_limited_does_not_take(self):
        for index, kwargs in enumerate(({"paused": True}, {"key_limited": True}, {"rolling": True})):
            main, alt = self.accounts(dict({"wishlist": ["rem"]}, **kwargs), {"min_kakera": 10})
            self.clicks.clear()
            self.roll(main, alt, {"id": 20 + index, "name": "Rem", "kakera": 40}, mode=arc.MODE_PREFER_MAIN)
            self.assertEqual(self.clicks, [("alt", 20 + index)], kwargs)

    def test_main_below_min_kakera_passes(self):
        main, alt = self.accounts({"min_kakera": 500}, {"min_kakera": 900})
        left = self.roll(main, alt, {"id": 25, "name": "Nobody", "kakera": 300})
        self.assertFalse(left)
        self.assertEqual(self.clicks, [])
        self.assertEqual(self.board.state(25), arc.PASSED)
        self.assertIn("below min kakera", self.board.get(25).reason)

    def test_timeout_alt_gives_up_then_main_can_no_longer_commit(self):
        main, alt = self.accounts({"wishlist": ["rem"], "judge_delay": 0.4}, {"min_kakera": 10})
        left = self.roll(main, alt, {"id": 30, "name": "Rem", "kakera": 40}, mode=arc.MODE_PREFER_MAIN,
                         decision_timeout=0.1)
        self.assertFalse(left)
        self.main_thread.run(asyncio.sleep(0.6))
        self.assertEqual(self.clicks, [("alt", 30)])
        self.assertEqual(self.board.state(30), arc.GAVE_UP)

    def test_main_committed_but_slow_alt_never_clicks(self):
        main, alt = self.accounts({"wishlist": ["rem"], "snipe_delay": 0.5}, {"min_kakera": 10})
        left = self.roll(main, alt, {"id": 31, "name": "Rem", "kakera": 40}, mode=arc.MODE_PREFER_MAIN,
                         decision_timeout=0.1, result_timeout=0.05)
        self.assertTrue(left, "the main committed: the alt leaves it even before the result")
        self.main_thread.run(asyncio.sleep(0.7))
        self.assertEqual(self.clicks, [("main", 31)])

    def test_never_both_click_under_random_timing(self):
        rng = random.Random(7)
        for index in range(40):
            main, alt = self.accounts(
                {"wishlist": ["rem"], "judge_delay": rng.uniform(0.0, 0.08), "snipe_delay": rng.uniform(0.0, 0.05)},
                {"min_kakera": 10})
            self.clicks.clear()
            self.roll(main, alt, {"id": 100 + index, "name": "Rem", "kakera": 40}, mode=arc.MODE_PREFER_MAIN,
                      decision_timeout=rng.uniform(0.0, 0.08), result_timeout=1.0)
            self.main_thread.run(asyncio.sleep(0.15))
            self.assertEqual(len(self.clicks), 1, self.clicks)


class MainRollsToAltsHarness(unittest.TestCase):
    """The mirror: «Alts claim good rolls made by the main» (one alt, in list order)."""

    def setUp(self):
        self.threads = {name: LoopThread() for name in ("main", "alt1", "alt2")}
        self.board = arc.AltRollBoard()
        self.clicks = []
        self.lock = threading.Lock()
        self.logs = []

    def tearDown(self):
        for thread in self.threads.values():
            thread.stop()

    def accounts(self, alt1=None, alt2=None):
        claimed = set()
        made = {}
        for name, kwargs in (("alt1", alt1), ("alt2", alt2)):
            account = Account("profile#" + name, clicks=self.clicks, lock=self.lock, **(kwargs or {}))
            account.claimed = claimed
            made[name] = account
        return made

    def main_rolls(self, alts, card, option=True, main_claim=False):
        """offer_own_roll_to_alts + offer_main_rolls_to_alts, reduced to the board calls."""
        why = "wishlist"
        if not option or arc.main_will_not_claim(claim_available=main_claim) is None:
            return None, None
        by_key = {account.key: (name, account) for name, account in alts.items()}

        def start(key):
            name, account = by_key[key]
            asyncio.run_coroutine_threadsafe(
                taker_judge(self.board, account, card, why, logs=self.logs), self.threads[name].loop)
            return True

        async def sleep(seconds):
            await asyncio.sleep(seconds)
            return True

        async def run():
            return await self.board.offer_in_turn(
                card["id"], offerer_key="profile#main", offerer_label="the main", card=card["name"],
                takers=[alts["alt1"].key, alts["alt2"].key], start=start, sleep=sleep,
                decision_timeout=1.0, result_timeout=2.0, step=0.01)

        return self.threads["main"].run(run())

    def test_main_without_claim_alt1_takes_it(self):
        alts = self.accounts()
        state, taker = self.main_rolls(alts, {"id": 201, "name": "Rem", "kakera": 40})
        self.assertEqual((state, taker), (arc.CLAIMED, "profile#alt1"))
        self.assertEqual(self.clicks, [("profile#alt1", 201)])
        self.assertIn("claiming \u2068Rem\u2069 rolled by the main (wishlist)", self.logs)

    def test_alt1_without_claim_alt2_takes_it(self):
        alts = self.accounts(alt1={"claim": False})
        state, taker = self.main_rolls(alts, {"id": 202, "name": "Rem", "kakera": 40})
        self.assertEqual((state, taker), (arc.CLAIMED, "profile#alt2"))
        self.assertEqual(self.clicks, [("profile#alt2", 202)])

    def test_nobody_available_nobody_claims(self):
        alts = self.accounts(alt1={"claim": False}, alt2={"key_limited": True})
        state, taker = self.main_rolls(alts, {"id": 203, "name": "Rem", "kakera": 40})
        self.assertEqual((state, taker), (arc.PASSED, None))
        self.assertEqual(self.clicks, [])
        self.assertTrue(self.board.blocks_claim(203, "profile#alt1"), "no alt snipes it outside the hand-off")

    def test_option_off_or_main_can_claim_unchanged(self):
        alts = self.accounts()
        self.assertEqual(self.main_rolls(alts, {"id": 204, "name": "Rem", "kakera": 40}, option=False), (None, None))
        self.assertEqual(self.main_rolls(alts, {"id": 205, "name": "Rem", "kakera": 40}, main_claim=True), (None, None))
        self.assertIsNone(self.board.get(204))
        self.assertIsNone(self.board.get(205))
        self.assertEqual(self.clicks, [])

    def test_timeout_nobody_else_tries(self):
        alts = self.accounts(alt1={"judge_delay": 1.5})
        state, taker = self.main_rolls(alts, {"id": 206, "name": "Rem", "kakera": 40})
        self.assertEqual(state, arc.GAVE_UP)
        self.threads["alt1"].run(asyncio.sleep(1.7))
        self.assertEqual(self.clicks, [], "alt 2 is not asked after a timeout and alt 1 cannot commit late")

    def test_both_options_never_ping_pong(self):
        board = self.board
        # alt 1's roll offered to the main, main passes: the main cannot offer it back to the alts.
        board.open(300, main_key="profile#main", alt_key="profile#alt1", card="Rem")
        board.main_pass(300, "profile#main", "has no claim now")
        self.assertIsNone(board.open(300, taker_key="profile#alt2", offerer_key="profile#main"))
        self.assertFalse(board.pass_on(300, "profile#main", "profile#alt2"))
        # A main roll offered to the alts cannot come back to the main either.
        board.open(301, taker_key="profile#alt1", offerer_key="profile#main", candidates=["profile#alt1"])
        board.main_pass(301, "profile#alt1", "has no claim now")
        self.assertIsNone(board.open(301, main_key="profile#main", alt_key="profile#alt1"))
        self.assertFalse(board.pass_on(301, "profile#main", "profile#alt1"), "each candidate is asked once")
        self.assertFalse(board.blocks_claim(301, "profile#main"), "nobody took it: the roller keeps its own rules")
        self.assertTrue(board.blocks_claim(301, "profile#alt1"), "an asked alt never claims it outside the hand-off")

    def test_main_will_not_claim(self):
        self.assertIsNone(arc.main_will_not_claim())
        self.assertEqual(arc.main_will_not_claim(claim_available=False), "the main has no claim now")
        self.assertIsNone(arc.main_will_not_claim(claim_available=False, restore_usable=True), "its own $rt first")
        self.assertIsNone(arc.main_will_not_claim(claim_available=False, keeping_for_reset=True))
        self.assertEqual(arc.main_will_not_claim(key_limited=True), "the main is paused at the key limit")


async def taker_judge(board, account, card, trusted_why, logs):
    """judge_alt_roll_for_main with ``trusted_why`` (an alt judging the main's roll)."""
    if account.judge_delay:
        await asyncio.sleep(account.judge_delay)
    blocker = arc.claim_blocker(paused=account.paused, key_limited=account.key_limited,
                                claim_available=account.claim_right_available, why=trusted_why)
    if blocker:
        board.main_pass(card["id"], account.key, blocker)
        return
    if not board.main_commit(card["id"], account.key):
        return
    logs.append(arc.taken_line(card["name"], "the main", trusted_why))
    claimed = False
    try:
        await asyncio.sleep(account.snipe_delay)
        claimed = account.click(account.key, card)
    finally:
        board.main_finish(card["id"], account.key, claimed)


class BoardTests(unittest.TestCase):
    def test_one_decision_point(self):
        board = arc.AltRollBoard()
        self.assertIsNotNone(board.open(1, main_key="m", alt_key="a", card="Rem"))
        self.assertIsNone(board.open(1, main_key="m", alt_key="a"), "a roll is offered once")
        self.assertTrue(board.blocks_claim(1, "m"), "the main's own snipe paths wait for the hand-off")
        self.assertFalse(board.blocks_claim(1, "other"), "other accounts are not affected")
        self.assertFalse(board.main_commit(1, "other"))
        self.assertTrue(board.main_commit(1, "m"))
        self.assertFalse(board.blocks_claim(1, "m"), "the hand-off itself may claim")
        self.assertFalse(board.alt_give_up(1, "a"), "after a commit the alt may not claim")
        self.assertTrue(board.main_finish(1, "m", True))
        self.assertEqual(board.state(1), arc.CLAIMED)
        self.assertTrue(board.blocks_claim(1, "m"))

    def test_give_up_before_commit(self):
        board = arc.AltRollBoard()
        board.open(2, main_key="m", alt_key="a")
        self.assertTrue(board.alt_give_up(2, "a"))
        self.assertFalse(board.main_commit(2, "m"))
        self.assertFalse(board.main_pass(2, "m", "late"))

    def test_failed_main_claim_lets_the_alt_claim(self):
        board = arc.AltRollBoard()
        board.open(3, main_key="m", alt_key="a")
        board.main_commit(3, "m")
        board.main_finish(3, "m", False, "the claim could not be sent")
        self.assertIn(board.state(3), arc.ALT_MAY_CLAIM)
        self.assertTrue(board.alt_give_up(3, "a"))

    def test_bounded(self):
        board = arc.AltRollBoard(limit=10)
        for message_id in range(50):
            board.open(message_id, main_key="m", alt_key="a")
        self.assertIsNone(board.get(0))
        self.assertIsNotNone(board.get(49))

    def test_wait_stops_when_the_alt_is_paused(self):
        board = arc.AltRollBoard()
        board.open(4, main_key="m", alt_key="a")

        async def paused(_seconds):
            return False

        state = asyncio.run(board.wait_for_main(4, "a", sleep=paused))
        self.assertEqual(state, arc.GAVE_UP)


class RuleTests(unittest.TestCase):
    def test_card_interest(self):
        self.assertEqual(arc.card_interest(name="Rem", wishlist=["rem"]), (True, "wishlist"))
        self.assertEqual(arc.card_interest(name="Rem", wishlist=["rem"], avoid_list=["rem"])[0], False)
        self.assertEqual(arc.card_interest(name="X", series_hit=True, min_kakera=999), (True, "series wishlist"))
        self.assertEqual(arc.card_interest(name="X", wished=True, min_kakera=999), (True, "wished"))
        self.assertEqual(arc.card_interest(name="X", claim_rank=50, max_claim_rank=100, min_kakera=999),
                         (True, "claim rank #50"))
        self.assertEqual(arc.card_interest(name="X", kakera=300, min_kakera=200), (True, "min kakera, 300 ka"))
        self.assertEqual(arc.card_interest(name="X", kakera=100, min_kakera=200),
                         (False, "below min kakera (100 < 200 ka)"))

    def test_blockers(self):
        self.assertIsNone(arc.claim_blocker())
        self.assertEqual(arc.claim_blocker(paused=True), "is paused")
        self.assertEqual(arc.claim_blocker(key_limited=True), "is paused at the key limit")
        self.assertEqual(arc.claim_blocker(claim_available=False), "has no claim now")
        self.assertEqual(arc.claim_blocker(key_mode_kakera_only=True, claim_available=False),
                         "is in key mode (kakera only)")
        self.assertEqual(arc.claim_blocker(claiming=True), "is busy claiming")
        self.assertEqual(arc.claim_blocker(inactive_hour=True), "is in its inactive hours")
        # Lurker holds the claim hour: wishes yes, value-only no.
        self.assertIsNone(arc.claim_blocker(lurking=True, why="wishlist"))
        self.assertEqual(arc.claim_blocker(lurking=True, why="min kakera, 300 ka"), "waits for its claim hour (Lurker)")

    def test_modes(self):
        self.assertEqual(arc.normalize_mode(None), arc.MODE_WHEN_ALT_PASSES)
        self.assertEqual(arc.normalize_mode("prefer_main"), arc.MODE_PREFER_MAIN)
        self.assertEqual(arc.normalize_mode("nonsense"), arc.MODE_WHEN_ALT_PASSES)
        self.assertFalse(arc.main_should_be_asked(arc.MODE_WHEN_ALT_PASSES, True))
        self.assertTrue(arc.main_should_be_asked(arc.MODE_WHEN_ALT_PASSES, False))
        self.assertTrue(arc.main_should_be_asked(arc.MODE_PREFER_MAIN, True))
        self.assertEqual(arc.validate_alt_roll_claim_settings({}), [])
        self.assertEqual(arc.validate_alt_roll_claim_settings({arc.MODE_SETTING: "prefer the main"}), [])
        self.assertEqual(len(arc.validate_alt_roll_claim_settings({arc.MODE_SETTING: "both"})), 1)

    def test_validate_preset_reports_a_bad_mode(self):
        errors = validate_preset({arc.MODE_SETTING: "both"}, require_runtime=False)
        self.assertTrue(any("Main claims good rolls" in error for error in errors), errors)

    def test_activity_events_with_account_labels(self):
        classifier = ActivityClassifier()
        events = classifier.classify("CLAIM", "main: " + arc.taken_line("Rem", "alt 1", "wishlist"))
        self.assertEqual(events[0][0], "alt_roll_claim")
        self.assertEqual(events[0][1]["character"], "Rem")
        self.assertEqual(events[0][1]["alt"], "alt 1")
        self.assertEqual(events[0][1]["account"], "main")
        self.assertEqual(classifier.classify("CLAIM", "alt 1: " + arc.left_line("Rem"))[0][0], "alt_roll_left")
        mirror = classifier.classify("CLAIM", "main: " + arc.left_line("Rem", "alt 1"))
        self.assertEqual((mirror[0][0], mirror[0][1]["taker"]), ("alt_roll_left", "alt 1"))
        taken = classifier.classify("CLAIM", "alt 1: " + arc.taken_line("Rem", "the main", "min kakera, 300 ka"))
        self.assertEqual(taken[0][1]["alt"], "the main")
        # Ordinary claim lines of a multi-account profile are events too.
        self.assertEqual(classifier.classify("CLAIM", "main: Claim attempt: Rem (300 ka)")[0][0], "claim_attempt")
        self.assertEqual(classifier.classify("CLAIM", "Claim attempt: Rem")[0][0], "claim_attempt")


class SettingsWiring(unittest.TestCase):
    def configured(self, data, index=1, count=2):
        client = SimpleNamespace(command_prefix="!", hourly_tu_refresh=False, preset_name="P")
        data = dict({"token": "made-up", "channel_id": 1, "_account_index": index, "_account_count": count}, **data)
        configure_client(client, "P", data, **OPTIONS)
        return client

    def test_off_by_default(self):
        client = self.configured({})
        self.assertFalse(client.main_claims_alt_rolls)
        self.assertEqual(client.main_claims_alt_rolls_mode, arc.MODE_WHEN_ALT_PASSES)

    def test_on_and_live(self):
        client = self.configured({"main_claims_alt_rolls": True, "main_claims_alt_rolls_mode": "prefer the main"})
        self.assertTrue(client.main_claims_alt_rolls)
        self.assertEqual(client.main_claims_alt_rolls_mode, arc.MODE_PREFER_MAIN)
        self.assertIn("main_claims_alt_rolls", LIVE_CONFIG_ATTRIBUTES)
        self.assertIn("main_claims_alt_rolls_mode", LIVE_CONFIG_ATTRIBUTES)
        self.assertIn("alts_claim_main_rolls", LIVE_CONFIG_ATTRIBUTES)
        self.assertFalse(self.configured({}).alts_claim_main_rolls)
        self.assertTrue(self.configured({"alts_claim_main_rolls": True}).alts_claim_main_rolls)

    def test_no_alts_profile_never_offers(self):
        from mudae_core.account_roles import side_kind_for
        single = self.configured({"main_claims_alt_rolls": True}, index=1, count=1)
        self.assertIsNone(side_kind_for(single), "a one-token profile is no alt: nothing is offered")
        main = self.configured({"main_claims_alt_rolls": True}, index=1, count=2)
        self.assertIsNone(side_kind_for(main), "the main itself never offers its rolls")
        alt = self.configured({"main_claims_alt_rolls": True}, index=2, count=2)
        self.assertEqual(side_kind_for(alt), "alt")

    def test_bot_wiring(self):
        source = (ROOT / "mudae_bot.py").read_text(encoding="utf-8")
        hook = source.index("await offer_own_roll_to_main(message, character_roll_origin)")
        # Before Main Account Sync and every claim path of the roll.
        self.assertLess(hook, source.index("sync_main_id = ("))
        self.assertLess(hook, source.index("Free event card detected"))
        # The offer is made only by an alt of a profile with the option on.
        offer = source[source.index("async def offer_own_roll_to_main"):]
        self.assertIn('getattr(client, "main_claims_alt_rolls", False) or side_kind_for(client) != "alt"', offer[:600])
        # The main never spends $rt here and claims through the normal helper.
        judge = source[source.index("async def judge_alt_roll_for_main"):source.index("async def alt_would_claim_own_roll")]
        self.assertIn("allow_rt=False", judge)
        self.assertIn("snipe_delay_wait(client.snipe_delay)", judge)
        self.assertNotIn("guarded_send", judge)
        self.assertIn("_alt_roll_board.blocks_claim(msg.id, _account_link_key(client))", source)
        # The mirror uses the same judge (roles swapped) and only the main's own rolls.
        self.assertLess(hook, source.index("await offer_own_roll_to_alts(message, character_roll_origin)"))
        self.assertIn("start_alt_roll_judge(\n                    m.id, m.channel.id, \"the main\", c, trusted_why=w)", source)
        self.assertEqual(source.count("own_rolls=False"), 2, "a side's hand-off rolls are never offered on")

    def test_editor_and_android_schema(self):
        editor = (ROOT / "mudae_preset_editor.py").read_text(encoding="utf-8")
        self.assertIn('"main_claims_alt_rolls": False,', editor)
        self.assertIn('"main_claims_alt_rolls_mode": "when the alt would not claim",', editor)
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run([sys.executable, str(ROOT / "android" / "generate_schema.py"), str(ROOT), folder],
                           check=True)
            with open(os.path.join(folder, "android_schema.json"), encoding="utf-8") as handle:
                fields = json.load(handle)["fields"]
        switch = fields["main_claims_alt_rolls"]
        self.assertEqual(switch["type"], "boolean")
        self.assertIs(switch["default"], False)
        self.assertEqual(switch["section"], "Main & alts")
        self.assertEqual(switch["label"], "Main claims good rolls made by its alts")
        mirror = fields["alts_claim_main_rolls"]
        self.assertEqual((mirror["type"], mirror["default"], mirror["section"]), ("boolean", False, "Main & alts"))
        self.assertEqual(mirror["label"], "Alts claim good rolls made by the main")
        mode = fields["main_claims_alt_rolls_mode"]
        self.assertEqual(mode["section"], "Main & alts")
        self.assertEqual(set(mode["choices"]), set(arc.MODES))
        self.assertEqual(mode["default"], arc.MODE_WHEN_ALT_PASSES)


if __name__ == "__main__":
    unittest.main()
