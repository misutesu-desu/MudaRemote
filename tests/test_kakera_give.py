import asyncio
import datetime
import os
import tempfile
import unittest
from types import SimpleNamespace

from mudae_core.account_state import AccountStateStore
from mudae_core.kakera_give import (
    BotReply, GiveSettings, KakeraGiver, give_amount, parse_give_question, parse_give_success,
    validate_give_settings,
)
from mudae_core.totals import KAKERA, SOURCE_TU, AccountTotals

SIDE_ID = "300000000000000003"
MAIN_ID = "100000000000000001"
KAKERA_EMOJI = "<:kakera:469835869059153940>"
WHEN = datetime.datetime(2026, 11, 28, 12, 0, tzinfo=datetime.timezone.utc)
CHANNEL = SimpleNamespace(id=555)


def question(amount):
    return "SideUser, do you really want to give {} {} ? (y/n/yes/no)".format(amount, KAKERA_EMOJI)


def success(amount, sender=SIDE_ID, receiver=MAIN_ID):
    return "<@{}> just gifted {} {} to <@{}>".format(sender, amount, KAKERA_EMOJI, receiver)


class FakeBot:
    """Plays the game bot: answers each message the giver sends via a script."""

    def __init__(self, giver_ref, script):
        self.giver_ref = giver_ref
        self.script = list(script)  # one entry per message we send: list of reply texts, "REFUSE", or None
        self.sent = []
        self.next_id = 1000
        self.first_id = None

    async def send(self, channel, text):
        self.sent.append(text)
        self.next_id += 1
        my_id = self.next_id
        if self.first_id is None:
            self.first_id = my_id
        replies = self.script.pop(0) if self.script else None
        loop = asyncio.get_running_loop()
        for reply in replies or ():
            if reply == "REFUSE":
                loop.call_soon(self.giver_ref[0].on_refused, my_id)
                continue
            if reply == "ACK":  # ✅ on the message being sent now
                loop.call_soon(self.giver_ref[0].on_ack, my_id)
                continue
            if reply == "ACK_COMMAND":  # ✅ on our first message (the command)
                loop.call_soon(self.giver_ref[0].on_ack, self.first_id)
                continue
            self.next_id += 1
            loop.call_soon(self.giver_ref[0].on_reply, BotReply(self.next_id, channel.id, reply))
        return SimpleNamespace(id=my_id)


class GiveFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AccountStateStore(os.path.join(self.tmp.name, "state.json"))
        self.logs = []
        self.side = AccountTotals("Side", clock=lambda: WHEN)
        self.main = AccountTotals("Main", clock=lambda: WHEN)
        self.side.set_total(KAKERA, 45132, SOURCE_TU)
        self.main.set_total(KAKERA, 1000, SOURCE_TU)
        self.clock_value = [0.0]

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, script, timeout=0.3):
        ref = [None]
        bot = FakeBot(ref, script)

        async def wait(seconds):
            await asyncio.sleep(min(seconds, 0.01))
            return True

        giver = KakeraGiver(
            key="pside#1", store=self.store, send=bot.send, wait=wait,
            log=lambda message, level: self.logs.append((level, message)),
            clock=lambda: WHEN, question_timeout=timeout, result_timeout=timeout, answer_delay=(0, 0),
        )
        ref[0] = giver
        return giver, bot

    def give(self, giver, settings=None, **overrides):
        options = dict(role="side", own_id=SIDE_ID, own_names=("SideUser",), main_id=MAIN_ID,
                       totals=self.side, main_totals=self.main)
        options.update(overrides)
        settings = settings or GiveSettings(enabled=True, threshold=45000, give_extra=True, daily_cap=3)
        return asyncio.run(giver.maybe_give(CHANNEL, settings, **options))

    # -- amounts ---------------------------------------------------------
    def test_owner_example_amounts(self):
        self.assertEqual(give_amount(45132, 45000, True), 45132)
        self.assertEqual(give_amount(45132, 45000, False), 45000)
        self.assertIsNone(give_amount(44999, 45000, True))
        self.assertIsNone(give_amount(None, 45000, True))

    def test_parsers(self):
        self.assertEqual(parse_give_question(question("45,132")), 45132)
        self.assertEqual(parse_give_question("SideUser, do you really want to give 500 :kakera: ? (y/n/yes/no)"), 500)
        self.assertIsNone(parse_give_question("do you really want to give 500 scraps? (y/n)"))
        self.assertIsNone(parse_give_question("do you really want to give 500 " + KAKERA_EMOJI))
        gift = parse_give_success(success(500))
        self.assertEqual((gift.amount, gift.sender_id, gift.receiver_id), (500, SIDE_ID, MAIN_ID))

    # -- happy paths -----------------------------------------------------
    def test_happy_path_gives_the_extra(self):
        giver, bot = self.make([[question(45132)], [success(45132)]])
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "given", outcome)
        self.assertEqual(bot.sent, ["$givek <@{}> 45132".format(MAIN_ID), "y"])
        self.assertEqual(self.side.kakera, 0)
        self.assertEqual(self.main.kakera, 1000 + 45132)
        self.assertEqual(self.store.gives_today("pside#1", WHEN.date()), 1)

    def test_check_reaction_on_the_command_after_y_is_success(self):
        giver, bot = self.make([[question(45132)], ["ACK_COMMAND"]])
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "given", outcome)
        self.assertEqual(self.side.kakera, 0)
        self.assertEqual(self.main.kakera, 1000 + 45132)

    def test_check_reaction_on_our_y_is_success(self):
        giver, bot = self.make([[question(45132)], ["ACK"]])
        self.assertEqual(self.give(giver).status, "given")
        self.assertEqual(bot.sent, ["$givek <@{}> 45132".format(MAIN_ID), "y"])

    def test_check_reaction_before_any_answer_is_not_success(self):
        giver, bot = self.make([["ACK"], None])
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "stopped")
        self.assertNotIn("y", bot.sent)
        self.assertEqual(self.side.kakera, 45132)

    def test_happy_path_without_extra(self):
        giver, bot = self.make([[question(45000)], [success(45000)]])
        outcome = self.give(giver, GiveSettings(enabled=True, threshold=45000, give_extra=False, daily_cap=3))
        self.assertEqual(outcome.status, "given")
        self.assertEqual(bot.sent[0], "$givek <@{}> 45000".format(MAIN_ID))
        self.assertEqual(self.side.kakera, 132)
        self.assertEqual(self.main.kakera, 46000)

    def test_unrelated_messages_are_ignored(self):
        other = "OtherUser, do you really want to give 45132 {} ? (y/n/yes/no)".format(KAKERA_EMOJI)
        giver, bot = self.make([[other, "<@999> just gifted 7 {} to <@1>".format(KAKERA_EMOJI), question(45132)],
                                [success(45132)]])
        self.assertEqual(self.give(giver).status, "given")

    # -- stops -------------------------------------------------------------
    def test_amount_mismatch_answers_n(self):
        giver, bot = self.make([[question(4513)], None])
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(bot.sent[-1], "n")
        self.assertNotIn("y", bot.sent)
        self.assertEqual(self.side.kakera, 45132)
        self.assertIn("instead of", outcome.reason)

    def test_question_timeout(self):
        giver, bot = self.make([None])
        outcome = self.give(giver, )
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(bot.sent, ["$givek <@{}> 45132".format(MAIN_ID)])
        self.assertIn("did not ask", outcome.reason)
        self.assertTrue(any(level == "WARN" for level, _ in self.logs))

    def test_result_timeout_makes_total_unknown_and_counts(self):
        giver, bot = self.make([[question(45132)], None])
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "stopped")
        self.assertIsNone(self.side.kakera)
        self.assertEqual(self.store.gives_today("pside#1", WHEN.date()), 1)

    def test_refusal_text_stops_and_logs_bot_text(self):
        text = "SideUser, you don't have enough kakera."
        giver, bot = self.make([[text]])
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(outcome.bot_text, text)
        self.assertTrue(any(text in message for _level, message in self.logs))
        self.assertEqual(bot.sent, ["$givek <@{}> 45132".format(MAIN_ID)])

    def test_stop_sign_reaction_stops(self):
        giver, bot = self.make([["REFUSE"]])
        self.assertIn("refused", self.give(giver).reason)

    def test_backoff_grows_and_blocks_retries(self):
        now = [0.0]
        giver, bot = self.make([None, None])
        giver._monotonic = lambda: now[0]
        giver.question_timeout = 0.0
        self.give(giver)
        reason = self.give(giver).reason
        self.assertIn("backing off", reason)
        self.assertEqual(len(bot.sent), 1)
        now[0] = 601.0
        self.give(giver)
        self.assertEqual(len(bot.sent), 2)
        self.assertEqual(giver._retry_at, 601.0 + 1800.0)

    def test_daily_cap(self):
        for _ in range(3):
            self.store.count_give("pside#1", WHEN.date())
        giver, bot = self.make([])
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "skipped")
        self.assertIn("daily limit", outcome.reason)
        self.assertEqual(bot.sent, [])

    def test_busy_account_defers(self):
        giver, bot = self.make([])
        outcome = self.give(giver, busy=lambda: "rolling")
        self.assertEqual((outcome.status, bot.sent), ("skipped", []))
        self.assertIn("rolling", outcome.reason)

    def test_main_unknown_or_self_or_not_side(self):
        for overrides, words in (({"main_id": ""}, "not known"), ({"main_id": SIDE_ID}, "itself"),
                                 ({"role": "main"}, "only a side")):
            giver, bot = self.make([])
            outcome = self.give(giver, **overrides)
            self.assertEqual(outcome.status, "skipped")
            self.assertIn(words, outcome.reason)
            self.assertEqual(bot.sent, [])

    def test_below_threshold_or_unknown_total(self):
        self.side.set_total(KAKERA, 44999, SOURCE_TU)
        giver, bot = self.make([])
        self.assertIn("below", self.give(giver).reason)
        self.side.set_total(KAKERA, None, SOURCE_TU)
        self.assertIn("unknown", self.give(giver).reason)
        self.assertEqual(bot.sent, [])

    def test_off_by_default(self):
        self.assertFalse(GiveSettings.from_preset({}).enabled)
        settings = GiveSettings.from_preset({})
        self.assertEqual((settings.threshold, settings.give_extra, settings.daily_cap), (45000, True, 3))

    def test_validation(self):
        self.assertEqual(validate_give_settings({"give_kakera_threshold": 45000, "give_kakera_daily_cap": 3}), [])
        self.assertTrue(validate_give_settings({"give_kakera_threshold": 0}))
        self.assertTrue(validate_give_settings({"give_kakera_daily_cap": "x"}))


class GiveAllNowTests(GiveFlowTests.__bases__[0]):
    """«Give all kakera now» (the button)."""

    setUp = GiveFlowTests.setUp
    tearDown = GiveFlowTests.tearDown
    make = GiveFlowTests.make

    def press(self, giver, minimum=1000, **overrides):
        options = dict(role="side", own_id=SIDE_ID, own_names=("SideUser",), main_id=MAIN_ID,
                       totals=self.side, main_totals=self.main, total_wait_seconds=0.5, busy_wait_seconds=0.5,
                       poll_seconds=0.01)
        options.update(overrides)
        return giver.give_all_now(CHANNEL, minimum=minimum, **options)

    def test_happy_path_gives_whole_total_and_skips_cap(self):
        for _ in range(3):
            self.store.count_give("pside#1", WHEN.date())  # automatic cap reached: the button still works
        giver, bot = self.make([[question(45132)], [success(45132)]])
        outcome = asyncio.run(self.press(giver))
        self.assertEqual(outcome.status, "given", outcome)
        self.assertEqual(bot.sent, ["$givek <@{}> 45132".format(MAIN_ID), "y"])
        self.assertEqual((self.side.kakera, self.main.kakera), (0, 1000 + 45132))
        self.assertEqual(self.store.gives_today("pside#1", WHEN.date()), 3)
        self.assertIn("gave 45,132", giver.manual_status)

    def test_below_minimum(self):
        self.side.set_total(KAKERA, 500, SOURCE_TU)
        giver, bot = self.make([])
        outcome = asyncio.run(self.press(giver, minimum=1000))
        self.assertEqual(outcome.status, "skipped")
        self.assertEqual(outcome.reason, "Only 500 kakera — the minimum is 1,000")
        self.assertIn("Only 500 kakera — the minimum is 1,000", giver.manual_status)
        self.assertEqual(bot.sent, [])

    def test_unknown_total_waits_for_tu_then_goes(self):
        self.side.set_total(KAKERA, None, SOURCE_TU)
        giver, bot = self.make([[question(2000)], [success(2000)]])

        async def run():
            task = asyncio.ensure_future(self.press(giver))
            await asyncio.sleep(0.05)
            self.assertTrue(any("waiting for the next $tu" in message for _level, message in self.logs))
            self.side.set_total(KAKERA, 2000, SOURCE_TU)  # the program's own $tu arrived
            return await task

        outcome = asyncio.run(run())
        self.assertEqual(outcome.status, "given", outcome)
        self.assertEqual(bot.sent[0], "$givek <@{}> 2000".format(MAIN_ID))
        self.assertNotIn("$tu", bot.sent)

    def test_unknown_total_times_out(self):
        self.side.set_total(KAKERA, None, SOURCE_TU)
        giver, bot = self.make([])
        outcome = asyncio.run(self.press(giver, total_wait_seconds=0.05))
        self.assertEqual(outcome.status, "stopped")
        self.assertIn("unknown", outcome.reason)
        self.assertEqual(bot.sent, [])

    def test_busy_defers_then_runs(self):
        state = {"busy": "rolling"}
        giver, bot = self.make([[question(45132)], [success(45132)]])

        async def run():
            task = asyncio.ensure_future(self.press(giver, busy=lambda: state["busy"], busy_wait_seconds=2.0))
            await asyncio.sleep(0.05)
            self.assertEqual(bot.sent, [])
            self.assertIn("deferred while rolling", giver.manual_status)
            state["busy"] = None
            return await task

        self.assertEqual(asyncio.run(run()).status, "given")

    def test_refused_on_main_or_without_main(self):
        for overrides, words in (({"role": "main"}, "only a side"), ({"main_id": ""}, "not known"),
                                 ({"main_id": SIDE_ID}, "itself")):
            giver, bot = self.make([])
            outcome = asyncio.run(self.press(giver, **overrides))
            self.assertEqual(outcome.status, "refused")
            self.assertIn(words, outcome.reason)
            self.assertEqual(bot.sent, [])

    def test_double_press_ignored_and_cooldown(self):
        now = [0.0]
        giver, bot = self.make([[question(45132)], [success(45132)]])
        giver._monotonic = lambda: now[0]

        async def run():
            first = asyncio.ensure_future(self.press(giver))
            await asyncio.sleep(0)
            second = await self.press(giver)
            return await first, second

        first, second = asyncio.run(run())
        self.assertEqual(first.status, "given")
        self.assertEqual(second.status, "ignored")
        self.assertIn("already running", second.reason)
        self.assertEqual(asyncio.run(self.press(giver)).status, "ignored")  # within 60 s
        now[0] = 61.0
        self.side.set_total(KAKERA, 10, SOURCE_TU)
        self.assertEqual(asyncio.run(self.press(giver)).status, "skipped")  # pressed again after the cooldown

    def test_question_mismatch_answers_n(self):
        giver, bot = self.make([[question(4513)], None])
        outcome = asyncio.run(self.press(giver))
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(bot.sent[-1], "n")


if __name__ == "__main__":
    unittest.main()
