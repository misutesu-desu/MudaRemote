"""A3: main & alts work together (mudae_core.main_alt_coop).

1. «Main keeps rolling while an alt can claim» (``main_rolls_while_alt_can_claim``).
2. «Main and alts take each other's kakera» (``accounts_share_kakera_reacts``).
3. Key farming mode: no account's rolling waits on another account.

Accounts run on their own event loops on their own threads where they talk to
each other, the way the app runs main and alts in one process. Names, ids and
messages are made up; nothing talks to Discord or the game bot.
"""

import asyncio
import datetime
import json
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from mudae_core import alt_roll_claim as arc
from mudae_core import main_alt_coop as coop
from mudae_core.bot_config import LIVE_CONFIG_ATTRIBUTES, configure_client
from mudae_core.runtime import (
    can_resume_claim_interrupted_rolls, daily_rolls_decision, normal_roll_behavior_flags,
)

ROOT = Path(__file__).resolve().parents[1]
UTC = datetime.timezone.utc
OPTIONS = {"bot_name": "MudaRemote", "claim_emojis": ["c"], "kakera_emojis": ["k"],
           "sphere_emojis": ["s"], "slash_available": True}


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


async def sleep_ok(seconds):
    await asyncio.sleep(seconds)
    return True


# ---------------------------------------------------------------------------
# 1. The main keeps rolling while an alt can claim
# ---------------------------------------------------------------------------

def alt_state(**overrides):
    state = dict(ready=True, paused=False, key_limited=False, same_channel=True, can_be_asked=True,
                 busy_for_main=False, claim_available=False, rt_available=False, auto_rt_enabled=True,
                 rt_only_self_rolls=False)
    state.update(overrides)
    return state


def main_gate(option_on, alts, *, own_claim=False, own_rt=False, key_mode=False):
    """The main's roll gate as mudae_bot wires it: own state first, then the alts."""
    alt = coop.first_capacity([(label, coop.alt_capacity(**state)) for label, state in alts]) if option_on else None
    immediate, _ = normal_roll_behavior_flags(
        rolling_enabled=True, proceed_to_rolls=True, scheduled_roll_due=False, can_claim=own_claim,
        is_lurking=False, key_mode=key_mode, rt_available=own_rt, is_timing_window=False, is_panic_window=False,
        alt_can_claim=bool(not (own_claim or key_mode or own_rt) and alt is not None),
    )
    return immediate, alt


class RollGateTable(unittest.TestCase):
    def test_gate_table(self):
        rows = [
            # (name, option, alt state, rolls?, counted alt)
            ("alt has a claim", True, alt_state(claim_available=True), True, ("alt 1", coop.CAPACITY_CLAIM)),
            ("alt has only $rt", True, alt_state(rt_available=True), True, ("alt 1", coop.CAPACITY_RT)),
            ("alt has neither", True, alt_state(), False, None),
            ("alt state unknown", True, alt_state(claim_available=None, rt_available=None), False, None),
            ("alt $rt but Auto $rt off", True, alt_state(rt_available=True, auto_rt_enabled=False), False, None),
            ("alt $rt only on own rolls", True, alt_state(rt_available=True, rt_only_self_rolls=True), False, None),
            ("alt paused", True, alt_state(claim_available=True, paused=True), False, None),
            ("alt key-limited", True, alt_state(claim_available=True, key_limited=True), False, None),
            ("alt in another channel", True, alt_state(claim_available=True, same_channel=False), False, None),
            ("alt not connected", True, alt_state(claim_available=True, ready=False), False, None),
            ("alt rolling for the main", True, alt_state(claim_available=True, busy_for_main=True), False, None),
            ("option off, alt has a claim", False, alt_state(claim_available=True), False, None),
        ]
        for name, option, state, rolls, counted in rows:
            with self.subTest(name):
                immediate, alt = main_gate(option, [("alt 1", state)])
                self.assertIs(immediate, rolls)
                self.assertEqual(alt, counted)

    def test_own_claim_and_key_mode_unchanged(self):
        for option in (False, True):
            self.assertTrue(main_gate(option, [], own_claim=True)[0])
            self.assertTrue(main_gate(option, [], own_rt=True)[0])
            self.assertTrue(main_gate(option, [], key_mode=True)[0])
            self.assertFalse(main_gate(option, [])[0], "no alt at all: today's behaviour")

    def test_claim_is_preferred_over_rt_and_order_is_kept(self):
        alts = [("alt 1", coop.CAPACITY_RT), ("alt 2", coop.CAPACITY_CLAIM), ("alt 3", coop.CAPACITY_CLAIM)]
        self.assertEqual(coop.first_capacity(alts), ("alt 2", coop.CAPACITY_CLAIM))
        self.assertEqual(coop.first_capacity([("alt 1", None), ("alt 2", coop.CAPACITY_RT)]), ("alt 2", coop.CAPACITY_RT))
        self.assertIsNone(coop.first_capacity([("alt 1", None)]))
        self.assertEqual(coop.rolls_on(True, False, ("alt 1", "claim")), (True, ("alt 1", "claim")))
        self.assertEqual(coop.rolls_on(False, False, ("alt 1", "claim")), (False, None))
        self.assertEqual(coop.rolls_on(True, True, None), (True, None))

    def test_lurker_hold_is_not_opened_by_an_alt(self):
        immediate, evaluate = normal_roll_behavior_flags(
            rolling_enabled=True, proceed_to_rolls=True, scheduled_roll_due=False, can_claim=False,
            is_lurking=True, key_mode=False, rt_available=False, is_timing_window=False, is_panic_window=False,
            alt_can_claim=True)
        self.assertEqual((immediate, evaluate), (False, False))

    def test_post_claim_stop(self):
        client = SimpleNamespace(rolling_enabled=True, is_paused=False, key_limit_hit=False, pending_claim=None,
                                 rolls_left=4, key_mode=False, claim_right_available=False, rt_available=False,
                                 is_timing_mode_active=False)
        self.assertFalse(can_resume_claim_interrupted_rolls(client), "option off: the batch stops after the claim")
        self.assertTrue(can_resume_claim_interrupted_rolls(client, alt_can_claim=True))
        client.rolls_left = 0
        self.assertFalse(can_resume_claim_interrupted_rolls(client, alt_can_claim=True), "no rolls left")

    def test_auto_rolls_item(self):
        now = datetime.datetime(2026, 11, 28, 12, 0, tzinfo=UTC)
        common = dict(enabled=True, key_mode=False, auto_rolls_in_key_mode=False,
                      next_claim_reset_at_utc=now + datetime.timedelta(minutes=30),
                      roll_reset_at_utc=now + datetime.timedelta(minutes=40), used_this_interval=False,
                      limit_reached=False, ack_retry_ready=True, now_utc=now)
        # mudae_bot passes claim_right_available = own claim or an alt's capacity.
        self.assertEqual(daily_rolls_decision(only_claim_hour=False, claim_right_available=False, **common),
                         "claim-unavailable")
        self.assertEqual(daily_rolls_decision(only_claim_hour=False, claim_right_available=False or True, **common),
                         "execute")
        self.assertEqual(daily_rolls_decision(only_claim_hour=True, claim_right_available=False, **common),
                         "wait-claim-reset")
        self.assertEqual(daily_rolls_decision(only_claim_hour=True, claim_right_available=True, **common), "execute")

    def test_alt_uses_rt_only_through_this_option(self):
        base = dict(option_on=True, from_main=True, claim_available=False, rt_available=True, auto_rt_enabled=True,
                    rt_only_self_rolls=False, kakera=300, restore_min_kakera=200, own_wish=False,
                    restore_for_wishlist=True)
        self.assertTrue(coop.alt_may_restore(**base))
        for change, why in ((dict(option_on=False), "option off"), (dict(from_main=False), "not a roll of the main"),
                            (dict(claim_available=True), "a free claim is used first"),
                            (dict(rt_available=False), "no $rt"), (dict(auto_rt_enabled=False), "Auto $rt off"),
                            (dict(rt_only_self_rolls=True), "$rt only on own rolls"),
                            (dict(kakera=100), "below the $rt minimum")):
            with self.subTest(why):
                self.assertFalse(coop.alt_may_restore(**dict(base, **change)))
        self.assertTrue(coop.alt_may_restore(**dict(base, kakera=10, own_wish=True)), "a wish ignores the minimum")
        self.assertFalse(coop.alt_may_restore(**dict(base, kakera=10, own_wish=True, restore_for_wishlist=False)))

    def test_handoff_is_implied(self):
        self.assertFalse(coop.handoff_enabled(False, False))
        self.assertTrue(coop.handoff_enabled(True, False))
        self.assertTrue(coop.handoff_enabled(False, True))

    def test_lines(self):
        self.assertEqual(coop.capacity_line(("alt 1", "claim")), "rolling on — alt 1 has a claim")
        self.assertEqual(coop.capacity_line(("alt 2", "rt")), "rolling on — alt 2 has $rt")
        self.assertIn("⁨Rem⁩", coop.rt_taken_line("Rem"))
        self.assertTrue(coop.rt_taken_line("Rem").endswith("from the main with $rt"))
        note = coop.ChangeNote(initial=None)
        self.assertFalse(note.update(None), "nothing to say at start")
        self.assertTrue(note.update(("alt 1", "claim")))
        self.assertFalse(note.update(("alt 1", "claim")), "once per change")
        self.assertTrue(note.update(None))


class AltAccount:
    """An alt taking a roll the main handed to it: claim first, else its $rt (option 1)."""

    def __init__(self, key, *, claim=False, rt=False, option=True, clicks, lock, claimed):
        self.key, self.claim, self.rt, self.option = key, claim, rt, option
        self.clicks, self.lock, self.claimed = clicks, lock, claimed
        self.rt_sent = 0

    async def judge(self, board, card):
        """judge_alt_roll_for_main with ``trusted_why`` (main → alt), reduced to its decisions."""
        use_restore = coop.alt_may_restore(option_on=self.option, from_main=True, claim_available=self.claim,
                                           rt_available=self.rt, auto_rt_enabled=True, rt_only_self_rolls=False,
                                           kakera=card["kakera"], restore_min_kakera=0, own_wish=False,
                                           restore_for_wishlist=False)
        blocker = arc.claim_blocker(claim_available=self.claim or use_restore)
        if blocker:
            board.main_pass(card["id"], self.key, blocker)
            return
        if not board.main_commit(card["id"], self.key):
            return
        claimed = False
        try:
            await asyncio.sleep(0.01)
            with self.lock:
                if card["id"] not in self.claimed:
                    if not self.claim:
                        self.rt_sent += 1      # the existing $rt-then-claim helper
                    self.claimed.add(card["id"])
                    self.clicks.append((self.key, card["id"]))
                    claimed = True
        finally:
            board.main_finish(card["id"], self.key, claimed)


class MainToAltsWithRestore(unittest.TestCase):
    def setUp(self):
        self.threads = {name: LoopThread() for name in ("main", "alt1", "alt2")}
        self.board = arc.AltRollBoard()
        self.clicks, self.lock, self.claimed = [], threading.Lock(), set()

    def tearDown(self):
        for thread in self.threads.values():
            thread.stop()

    def alt(self, key, **kwargs):
        return AltAccount(key, clicks=self.clicks, lock=self.lock, claimed=self.claimed, **kwargs)

    def offer(self, alts, card):
        by_key = {alt.key: alt for alt in alts}

        def start(key):
            asyncio.run_coroutine_threadsafe(by_key[key].judge(self.board, card), self.threads[key].loop)
            return True

        return self.threads["main"].run(self.board.offer_in_turn(
            card["id"], offerer_key="main", offerer_label="the main", card=card["name"],
            takers=[alt.key for alt in alts], start=start, sleep=sleep_ok, step=0.01))

    def test_alt_without_claim_uses_its_rt(self):
        alt1 = self.alt("alt1", rt=True)
        state, taker = self.offer([alt1], {"id": 1, "name": "Rem", "kakera": 400})
        self.assertEqual((state, taker), (arc.CLAIMED, "alt1"))
        self.assertEqual(alt1.rt_sent, 1)

    def test_free_claim_first_no_rt(self):
        alt1, alt2 = self.alt("alt1", rt=True, claim=False, option=False), self.alt("alt2", claim=True)
        state, taker = self.offer([alt1, alt2], {"id": 2, "name": "Ram", "kakera": 400})
        self.assertEqual((state, taker), (arc.CLAIMED, "alt2"))
        self.assertEqual(alt1.rt_sent + alt2.rt_sent, 0, "option off on alt 1: its $rt stays untouched")

    def test_nobody_can_nobody_claims(self):
        state, taker = self.offer([self.alt("alt1"), self.alt("alt2", option=False, rt=True)],
                                  {"id": 3, "name": "Emilia", "kakera": 400})
        self.assertEqual((state, taker), (arc.PASSED, None))
        self.assertEqual(self.clicks, [])


# ---------------------------------------------------------------------------
# 2. Accounts take each other's kakera
# ---------------------------------------------------------------------------

class KakeraAccount:
    """One account's own kakera rules: emoji list, power, cost (no $dk for a share)."""

    def __init__(self, key, index, *, emojis=("kakeraR", "kakeraW"), power=100, cost=40, option=True,
                 paused=False, snipe_mode=False, delay=0.0):
        self.key, self.index = key, index
        self.emojis, self.power, self.cost = set(emojis), power, cost
        self.option, self.paused, self.snipe_mode, self.delay = option, paused, snipe_mode, delay
        self.ledger = set()

    def would_click(self, name):
        return not self.paused and name in self.emojis and self.power >= self.cost


class KakeraWorld:
    """The game bot's side of the buttons: each button goes to the first click."""

    def __init__(self):
        self.lock = threading.Lock()
        self.taken = {}
        self.clicks = []

    def click(self, who, button):
        with self.lock:
            self.clicks.append((who, button))
            if button in self.taken:
                return False
            self.taken[button] = who
            return True


async def taker_judge(board, account, world, board_key, name, roller_label, logs):
    """judge_kakera_share, reduced to its decisions."""
    blocker = coop.kakera_share_blocker(option_on=account.option, paused=account.paused,
                                        eligible=name in account.emojis, already_has=board_key in account.ledger,
                                        power_ok=account.power >= account.cost)
    if blocker:
        board.main_pass(board_key, account.key, blocker)
        return
    if not board.main_commit(board_key, account.key):
        return
    clicked = False
    try:
        await asyncio.sleep(account.delay)
        account.ledger.add(board_key)
        clicked = world.click(account.key, board_key)
        if clicked:
            logs.append(coop.kakera_taken_line(name, roller_label))
    finally:
        board.main_finish(board_key, account.key, clicked)


class KakeraShareHarness(unittest.TestCase):
    def setUp(self):
        self.world = KakeraWorld()
        self.board = arc.AltRollBoard()
        self.logs = []
        self.threads = {}

    def tearDown(self):
        for thread in self.threads.values():
            thread.stop()

    def accounts(self, *specs):
        result = []
        for key, index, kwargs in specs:
            self.threads[key] = LoopThread()
            result.append(KakeraAccount(key, index, **kwargs))
        return result

    async def roller_sees_own_roll(self, roller, others, message_id, buttons, option=True):
        """The roller's own kakera decision, then share_left_kakera; others' snipe paths run beside it."""
        for name in buttons:
            if roller.would_click(name):
                roller.ledger.add((message_id, name))
                self.world.click(roller.key, (message_id, name))
        if not option:
            return
        left = coop.left_kakera_buttons([((0, i), name, False, False) for i, name in enumerate(buttons)],
                                        lambda position, name: (message_id, name) in roller.ledger)
        order = coop.share_order([(other.key, other.index) for other in others], roller.key)
        by_key = {other.key: other for other in others}
        for _position, name in left:
            board_key = (message_id, name)

            def start(key, b=board_key, n=name):
                asyncio.run_coroutine_threadsafe(
                    taker_judge(self.board, by_key[key], self.world, b, n,
                                arc.roller_label_for("alt 1" if roller.index > 1 else "main"), self.logs),
                    self.threads[key].loop)
                return True

            await self.board.offer_in_turn(board_key, offerer_key=roller.key, offerer_label="r", card=name,
                                           takers=order, start=start, sleep=sleep_ok, step=0.01)

    def run_roll(self, roller, others, buttons, message_id=1, option=True):
        thread = self.threads[roller.key]
        thread.run(self.roller_sees_own_roll(roller, others, message_id, buttons, option=option))

    def test_roller_cannot_other_takes_once(self):
        main, alt1, alt2 = self.accounts(("main", 1, {}), ("alt1", 2, {"power": 10}), ("alt2", 3, {}))
        self.run_roll(alt1, [main, alt2], ["kakeraR"])
        self.assertEqual(self.world.taken, {(1, "kakeraR"): "main"}, "the main comes first")
        self.assertEqual(len(self.world.clicks), 1)
        self.assertEqual(self.logs, ["took kakera kakeraR on alt 1's roll"])

    def test_main_cannot_then_alts_in_order(self):
        main, alt1, alt2 = self.accounts(("main", 1, {"power": 0}), ("alt1", 2, {"emojis": ("kakeraW",)}),
                                         ("alt2", 3, {}))
        self.run_roll(main, [alt1, alt2], ["kakeraR"])
        self.assertEqual(self.world.taken, {(1, "kakeraR"): "alt2"}, "alt 1 lacks the emoji, alt 2 takes it")
        self.assertEqual(self.logs, ["took kakera kakeraR on the main's roll"])

    def test_roller_can_nobody_else(self):
        main, alt1 = self.accounts(("main", 1, {}), ("alt1", 2, {}))
        self.run_roll(main, [alt1], ["kakeraR"])
        self.assertEqual(self.world.clicks, [("main", (1, "kakeraR"))])

    def test_none_can_nobody(self):
        main, alt1 = self.accounts(("main", 1, {"power": 0}), ("alt1", 2, {"paused": True}))
        self.run_roll(main, [alt1], ["kakeraR"])
        self.assertEqual(self.world.clicks, [])

    def test_option_off_unchanged(self):
        main, alt1 = self.accounts(("main", 1, {"power": 0}), ("alt1", 2, {"option": False}))
        self.run_roll(main, [alt1], ["kakeraR"], option=False)
        self.assertEqual(self.world.clicks, [])
        # Off: the alt's own kakera snipe on the main's roll is not held back.
        self.assertFalse(coop.skip_own_snipe_of_sibling_roll(False, True))

    def test_no_double_click_with_the_snipe_feature(self):
        for seed in range(20):
            random.seed(seed)
            self.world = KakeraWorld()
            self.board = arc.AltRollBoard()
            main, alt1, alt2 = self.accounts(("main%d" % seed, 1, {"power": 0}),
                                             ("a1-%d" % seed, 2, {"snipe_mode": True, "delay": random.uniform(0, 0.03)}),
                                             ("a2-%d" % seed, 3, {"snipe_mode": True, "delay": random.uniform(0, 0.03)}))
            # The siblings' own kakera snipe on the main's roll: skipped while sharing is on.
            for sibling in (alt1, alt2):
                if sibling.snipe_mode and not coop.skip_own_snipe_of_sibling_roll(True, roller_is_sibling=True):
                    self.world.click(sibling.key, (seed, "kakeraR"))
            self.run_roll(main, [alt1, alt2], ["kakeraR"], message_id=seed)
            self.assertEqual(len(self.world.clicks), 1, "one click per button, seed {}".format(seed))
            self.assertEqual(self.world.taken[(seed, "kakeraR")], alt1.key)

    def test_left_buttons_and_order(self):
        buttons = [((0, 0), "kakeraR", False, False), ((0, 1), "kakeraP", False, False),
                   ((0, 2), "spG", False, True), ((0, 3), "kakeraW", True, False), ((0, 4), "kakeraL", False, False)]
        left = coop.left_kakera_buttons(buttons, lambda position, name: name == "kakeraL")
        self.assertEqual(left, [((0, 0), "kakeraR")], "purple, spheres, disabled and taken buttons stay out")
        self.assertEqual(coop.left_kakera_buttons(buttons[:1], lambda p, n: 1 / 0), [], "unsure = never offered")
        self.assertEqual(coop.share_order([("a2", 3), ("m", 1), ("a1", 2), ("r", 2)], "r"), ["m", "a1", "a2"])

    def test_blockers(self):
        self.assertIsNone(coop.kakera_share_blocker())
        self.assertEqual(coop.kakera_share_blocker(option_on=False), "has «take each other's kakera» off")
        self.assertEqual(coop.kakera_share_blocker(key_limited=True), "is paused at the key limit")
        self.assertEqual(coop.kakera_share_blocker(power_known=False), "its power is not known yet")
        self.assertEqual(coop.kakera_share_blocker(power_ok=False), "not enough power for its rules")
        self.assertEqual(coop.kakera_share_blocker(eligible=False), "the emoji is not in its lists")
        self.assertEqual(coop.kakera_taken_line("kakeraO", "the main"), "took kakera kakeraO on the main's roll")


# ---------------------------------------------------------------------------
# 3. Key farming mode: both keep rolling
# ---------------------------------------------------------------------------

class KeyModeIndependence(unittest.TestCase):
    def test_roller_batch_never_awaits_a_handoff(self):
        """The alt's batch sends its rolls on time while the main takes 1 s to decide.

        Each roll result is handled as its own task (as Discord dispatches
        on_message); in key mode the offer's wait runs beside the handling."""
        main_thread, alt_thread = LoopThread(), LoopThread()
        try:
            for key_mode in (True, False):
                board = arc.AltRollBoard()
                kakera_at = []

                async def main_judge(message_id, board=board):
                    await asyncio.sleep(1.0)
                    board.main_pass(message_id, "main", "not wanted")

                async def on_message(message_id, sent_at, board=board, kakera_at=kakera_at, key_mode=key_mode):
                    board.open(message_id, main_key="main", alt_key="alt1", alt_label="alt 1", card="X")
                    asyncio.run_coroutine_threadsafe(main_judge(message_id), main_thread.loop)
                    wait = board.wait_for_main(message_id, "alt1", sleep=sleep_ok, step=0.01)
                    if coop.handoff_wait_inline(key_mode):
                        await wait
                    else:
                        asyncio.get_running_loop().create_task(wait)
                    kakera_at.append(time.monotonic() - sent_at)   # the roll's own kakera / claim paths

                async def batch():
                    started = time.monotonic()
                    for message_id in range(3):
                        message_id += 10 * int(key_mode)   # never the ids of the other run
                        asyncio.get_running_loop().create_task(on_message(message_id, time.monotonic()))
                        await asyncio.sleep(0.05)   # roll speed
                    sent = time.monotonic() - started
                    while len(kakera_at) < 3:
                        await asyncio.sleep(0.01)
                    return sent

                sent = alt_thread.run(batch())
                self.assertLess(sent, 0.5, "the batch itself never waits on the main")
                if key_mode:
                    self.assertLess(max(kakera_at), 0.3, "key mode: the roll's own handling goes on at once")
                else:
                    self.assertGreater(min(kakera_at), 0.9, "outside key mode the alt waits for the main (as before)")
        finally:
            main_thread.stop()
            alt_thread.stop()

    def test_side_turns_and_rules(self):
        self.assertFalse(coop.side_turns_allowed(True))
        self.assertTrue(coop.side_turns_allowed(False))
        self.assertFalse(coop.rolling_blocks_taking(True))
        self.assertTrue(coop.rolling_blocks_taking(False))
        self.assertEqual(coop.KEY_MODE_LINE, "key mode: accounts roll independently")
        self.assertIsNone(arc.claim_blocker(rolling=False))
        self.assertEqual(arc.claim_blocker(rolling=True), "is rolling its own batch")

    def test_lock_scope(self):
        self.assertTrue(coop.receiver_holds_rolls(False, receiving=True, confirming=False), "outside key mode: whole give")
        self.assertFalse(coop.receiver_holds_rolls(True, receiving=True, confirming=False), "key mode: not the whole give")
        self.assertTrue(coop.receiver_holds_rolls(True, receiving=True, confirming=True), "key mode: the «y» step")
        self.assertIsNone(coop.partner_busy_reason(True, rolling=True), "key mode: the main's rolling does not block")
        self.assertEqual(coop.partner_busy_reason(False, rolling=True), "rolling or claiming")
        self.assertEqual(coop.partner_busy_reason(True, claiming=True), "rolling or claiming")
        self.assertEqual(coop.partner_busy_reason(True, own_procedure="giving kakera"), "giving kakera")

    def test_harem_give_marks_only_the_confirm_step(self):
        from tests.test_harem_give import FlowTests, Partner, MAIN_ID, SIDE_ID, CHANNEL

        seen = []
        # The module the giver really runs in (another test may have reloaded harem_give).
        from tests.test_harem_give import HaremGiver
        give_module = SimpleNamespace(**HaremGiver.maybe_give.__globals__)

        class WatchingPartner(Partner):
            def __init__(self, fake):
                super().__init__(fake)
                self.key = "a3-main#confirm-test"   # its own key: no other test's give state

            def busy_reason(self):
                seen.append(("busy", give_module.main_receiving(self.key), give_module.main_confirming(self.key)))
                return None

            async def answer(self, channel_id, text):
                seen.append(("answer", give_module.main_receiving(self.key), give_module.main_confirming(self.key)))
                return await super().answer(channel_id, text)

        flow = FlowTests()
        flow.setUp()
        try:
            giver, fake = flow.make(pages=3)
            partner = WatchingPartner(fake)
            outcome = asyncio.run(giver.maybe_give(
                CHANNEL, give_module.HaremGiveSettings(enabled=True, pages=3), role="side", own_id=SIDE_ID,
                own_names=("SideUser",), main_id=MAIN_ID, partner=partner))
        finally:
            flow.tearDown()
        self.assertEqual(outcome.status, "given", outcome)
        self.assertIn(("answer", True, True), seen, "the main is confirming while it answers «y»")
        self.assertIn(("busy", False, False), seen, "before the give, nothing is held")
        self.assertIn(("busy", True, False), seen, "the choosing step does not hold the main in key mode")
        self.assertFalse(give_module.main_confirming(partner.key))
        self.assertFalse(give_module.main_receiving(partner.key))

    def test_quiet_channel_ignores_siblings_in_key_mode(self):
        self.assertTrue(coop.quiet_wait_ignores(True, author_id=7, interaction_user_id=None, sibling_ids={7}))
        self.assertTrue(coop.quiet_wait_ignores(True, author_id=99, interaction_user_id=7, sibling_ids={7}))
        self.assertFalse(coop.quiet_wait_ignores(True, author_id=8, interaction_user_id=None, sibling_ids={7}))
        self.assertFalse(coop.quiet_wait_ignores(False, author_id=7, interaction_user_id=None, sibling_ids={7}))


# ---------------------------------------------------------------------------
# Settings and wiring
# ---------------------------------------------------------------------------

class SettingsWiring(unittest.TestCase):
    def configured(self, data, index=1, count=2):
        client = SimpleNamespace(command_prefix="!", hourly_tu_refresh=False, preset_name="P")
        data = dict({"token": "made-up", "channel_id": 1, "_account_index": index, "_account_count": count}, **data)
        configure_client(client, "P", data, **OPTIONS)
        return client

    def test_off_by_default_and_live(self):
        client = self.configured({})
        self.assertFalse(client.main_rolls_while_alt_can_claim)
        self.assertFalse(client.accounts_share_kakera_reacts)
        client = self.configured({"main_rolls_while_alt_can_claim": True, "accounts_share_kakera_reacts": True})
        self.assertTrue(client.main_rolls_while_alt_can_claim)
        self.assertTrue(client.accounts_share_kakera_reacts)
        self.assertIn("main_rolls_while_alt_can_claim", LIVE_CONFIG_ATTRIBUTES)
        self.assertIn("accounts_share_kakera_reacts", LIVE_CONFIG_ATTRIBUTES)

    def test_bot_wiring(self):
        source = (ROOT / "mudae_bot.py").read_text(encoding="utf-8")
        # 1. every «no claim» roll gate reads the alts' capacity.
        self.assertEqual(source.count("alt_claim_counts()"), 6)
        self.assertIn("claim_right_available=bool(client.claim_right_available or alt_claim_counts())", source)
        self.assertIn("can_resume_claim_interrupted_rolls(client, alt_can_claim=", source)
        self.assertIn("alt_can_claim=bool(not (can_claim or client.key_mode or client.rt_available) and alt_claim_counts())", source)
        self.assertEqual(source.count("and not alt_claim_counts()"), 2, "Auto $us «stop on claim» (two places)")
        # The hand-off is implied; $rt only through the new rule; the precheck allows it for main → alt.
        self.assertEqual(source.count('getattr(client, "alts_claim_main_rolls", False)'), 1, "read only in alt_handoff_on")
        judge = source[source.index("async def judge_alt_roll_for_main"):source.index("async def alt_would_claim_own_roll")]
        self.assertIn("allow_rt=True", judge)
        self.assertIn("use_restore = await alt_restore_for_main_roll(message, k_val, trusted_why)", judge)
        self.assertIn('side.alt_roll_precheck(allow_restore=getattr(client, "main_rolls_while_alt_can_claim", False))', source)
        # 2. siblings' own kakera snipes step aside; the roller shares after its own decision.
        self.assertIn("_coop.skip_own_snipe_of_sibling_roll(", source)
        self.assertGreaterEqual(source.count("schedule_kakera_share(message)"), 5)
        share = source[source.index("async def judge_kakera_share"):source.index("client._account_link.judge_kakera_share")]
        self.assertIn("allow_refill=False", share)
        self.assertIn("click_kakera_with_confirmation(", share)
        self.assertIn("kakera_reaction_snipe_delay_value", share)
        self.assertNotIn("guarded_send", share)
        # 3. key mode.
        sides = source[source.index("async def ask_sides_to_roll_for_main"):source.index("async def judge_side_roll_for_main")]
        self.assertLess(sides.index("_coop.side_turns_allowed(client.key_mode)"), sides.index("run_for_main"))
        self.assertIn("background=True", source)
        self.assertIn("main_receiving_harem=receiver_holds_rolls()", source)
        self.assertIn("if not await hold_while_answering_give():", source)
        self.assertIn("_coop.quiet_wait_ignores(True, author_id=author_id", source)

    def test_editor_and_android_schema(self):
        editor = (ROOT / "mudae_preset_editor.py").read_text(encoding="utf-8")
        self.assertIn('"main_rolls_while_alt_can_claim": False,', editor)
        self.assertIn('"accounts_share_kakera_reacts": False,', editor)
        self.assertLess(editor.index('"side_rolls_for_main", "Alts roll for the main when it finds nothing"'),
                        editor.index('"main_rolls_while_alt_can_claim", "Main keeps rolling while an alt can claim"'))
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run([sys.executable, str(ROOT / "android" / "generate_schema.py"), str(ROOT), folder],
                           check=True)
            with open(os.path.join(folder, "android_schema.json"), encoding="utf-8") as handle:
                fields = json.load(handle)["fields"]
        roll_on = fields["main_rolls_while_alt_can_claim"]
        self.assertEqual((roll_on["type"], roll_on["default"], roll_on["section"]), ("boolean", False, "Main & alts"))
        self.assertEqual(roll_on["label"], "Main keeps rolling while an alt can claim")
        self.assertEqual(roll_on["order"], fields["side_rolls_for_main"]["order"] + 1, "right under «Alts roll for the main…»")
        share = fields["accounts_share_kakera_reacts"]
        self.assertEqual((share["type"], share["default"], share["section"]), ("boolean", False, "Main & alts"))
        self.assertEqual(share["label"], "Main and alts take each other's kakera")

    def test_manifest_lists_the_module(self):
        manifest = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
        self.assertIn("mudae_core/main_alt_coop.py", [entry["path"] for entry in manifest["source_files"]])


if __name__ == "__main__":
    unittest.main()
