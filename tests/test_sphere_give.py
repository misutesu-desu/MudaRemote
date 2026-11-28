import asyncio
import datetime
import os
import tempfile
import unittest
from types import SimpleNamespace

from mudae_core.account_state import AccountStateStore
from mudae_core.kakera_give import BotReply
from mudae_core.sphere_give import (
    SphereGiveSettings, SphereGiver, log_reply_text, parse_sphere_question, parse_sphere_success,
    spheres_to_give, validate_sphere_give_settings,
)
from mudae_core.totals import KAKERA, SPHERES, SOURCE_TU, AccountTotals

SIDE_ID = "300000000000000003"
MAIN_ID = "100000000000000001"
OTHER_ID = "200000000000000002"
SPHERE_EMOJI = "<:spR:469835869059153941>"
KAKERA_EMOJI = "<:kakera:469835869059153940>"
WHEN = datetime.datetime(2026, 11, 28, 12, 0, tzinfo=datetime.timezone.utc)
CHANNEL = SimpleNamespace(id=555)


def question(amount, extra=""):
    return "SideUser, do you really want to give {} {} {}? (y/n/yes/no)".format(amount, SPHERE_EMOJI, extra)


def success(amount, sender=SIDE_ID, receiver=MAIN_ID):
    return "<@{}> just gifted {} {} to <@{}>".format(sender, amount, SPHERE_EMOJI, receiver)


class FakeBot:
    """Plays the game bot: one script entry per message we send (texts, "REFUSE" or "ACK")."""

    def __init__(self, ref, script):
        self.ref = ref
        self.script = list(script)
        self.sent = []
        self.next_id = 1000

    async def send(self, channel, text):
        self.sent.append(text)
        self.next_id += 1
        my_id = self.next_id
        replies = self.script.pop(0) if self.script else None
        loop = asyncio.get_running_loop()
        for reply in replies or ():
            if reply == "REFUSE":
                loop.call_soon(self.ref[0].on_refused, my_id)
            elif reply == "ACK":
                loop.call_soon(self.ref[0].on_ack, my_id)
            else:
                self.next_id += 1
                loop.call_soon(self.ref[0].on_reply, BotReply(self.next_id, channel.id, reply))
        return SimpleNamespace(id=my_id)


class SphereGiveBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AccountStateStore(os.path.join(self.tmp.name, "state.json"))
        self.logs = []
        self.now = [WHEN]
        self.side = AccountTotals("Side", clock=lambda: WHEN)
        self.main = AccountTotals("Main", clock=lambda: WHEN)
        self.side.set_total(SPHERES, 1250, SOURCE_TU)
        self.main.set_total(SPHERES, 100, SOURCE_TU)

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, script, timeout=0.3):
        ref = [None]
        bot = FakeBot(ref, script)

        async def wait(seconds):
            await asyncio.sleep(min(seconds, 0.01))
            return True

        giver = SphereGiver(
            key="pside#1", store=self.store, send=bot.send, wait=wait,
            log=lambda message, level: self.logs.append((level, message)),
            clock=lambda: self.now[0], question_timeout=timeout, result_timeout=timeout, answer_delay=(0, 0),
        )
        ref[0] = giver
        return giver, bot

    def give(self, giver, settings=None, **overrides):
        options = dict(role="side", own_id=SIDE_ID, own_names=("SideUser",), main_id=MAIN_ID,
                       totals=self.side, main_totals=self.main)
        options.update(overrides)
        settings = settings or SphereGiveSettings(enabled=True)
        return asyncio.run(giver.maybe_give(CHANNEL, settings, **options))


class ParserTests(unittest.TestCase):
    def test_amounts(self):
        self.assertEqual(spheres_to_give(1, 0), 1)
        self.assertIsNone(spheres_to_give(0, 0))
        self.assertIsNone(spheres_to_give(None, 0))
        self.assertEqual(spheres_to_give(1250, 250), 1000)
        self.assertIsNone(spheres_to_give(250, 250))

    def test_question(self):
        asked = parse_sphere_question(question("1,250"))
        self.assertEqual(asked.amount, 1250)
        self.assertFalse(asked.kakera)
        self.assertTrue(parse_sphere_question("A, do you really want to give 5 {} ? (y/n)".format(KAKERA_EMOJI)).kakera)
        self.assertIsNone(parse_sphere_question("A, how many spheres do you want to give?"))
        self.assertIsNone(parse_sphere_question("do you really want to give 5 spheres"))
        self.assertEqual(parse_sphere_question("A, do you really want to give 5 spheres ? (y/n)").amount, 5)

    def test_success(self):
        gift = parse_sphere_success(success(1250))
        self.assertEqual((gift.amount, gift.sender_id, gift.receiver_id), (1250, SIDE_ID, MAIN_ID))
        self.assertEqual(parse_sphere_success("1,250 spheres have been given to <@{}>".format(MAIN_ID)).amount, 1250)
        self.assertIsNone(parse_sphere_success("<@1> just gifted 500 {} to <@2>".format(KAKERA_EMOJI)))
        self.assertIsNone(parse_sphere_success("hello"))

    def test_settings_and_log_text(self):
        self.assertEqual(SphereGiveSettings.from_preset({}), SphereGiveSettings(False, 30, 0))
        self.assertEqual(SphereGiveSettings.from_preset({"auto_give_spheres": True, "sphere_give_interval_min": "5",
                                                         "spheres_keep": 100}), SphereGiveSettings(True, 5, 100))
        self.assertEqual(SphereGiveSettings.from_preset({"sphere_give_interval_min": 0}).interval_min, 30)
        self.assertEqual(validate_sphere_give_settings({}), [])
        self.assertEqual(len(validate_sphere_give_settings({"sphere_give_interval_min": 0, "spheres_keep": -1})), 2)
        shown = log_reply_text("hi <@{}>\n{}".format(MAIN_ID, "x" * 500), 100)
        self.assertNotIn(MAIN_ID, shown)
        self.assertLessEqual(len(shown), 100)
        self.assertNotIn("\n", shown)


class ActivityLineTests(unittest.TestCase):
    def test_log_lines_become_events_and_the_give_kind(self):
        from mudae_core.activity_events import ActivityClassifier
        from mudae_core.logs import classify_kind
        c = ActivityClassifier()
        kind, data = c.classify("SUCCESS", "Sphere give: gave 1,250 spheres to the main.")[0]
        self.assertEqual((kind, data["spheres"]), ("sphere_give", 1250))
        kind, _ = c.classify("WARN", "Sphere give stopped: no «gifted» line or ✅ in time. Next try in 10 min.")[0]
        self.assertEqual(kind, "sphere_give_stopped")
        kind, data = c.classify("SUCCESS", "Give all spheres: gave 40 spheres to the main.")[0]
        self.assertEqual((kind, data["spheres"]), ("sphere_give_now", 40))
        self.assertEqual(classify_kind("Sphere give: gave 1,250 spheres to the main.", "SUCCESS"), "GIVE")
        self.assertEqual(classify_kind("Give all spheres: not given \u2014 busy.", "INFO"), "GIVE")


class TriggerTests(SphereGiveBase):
    def test_trigger_at_stock_one_gives_exact_amount(self):
        self.side.set_total(SPHERES, 1, SOURCE_TU)
        giver, bot = self.make([[question(1)], [success(1)]])
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "given", outcome)
        self.assertEqual(bot.sent, ["$givesp <@{}> 1".format(MAIN_ID), "Y"])
        self.assertEqual((self.side.spheres, self.main.spheres), (0, 101))

    def test_no_trigger_at_zero_or_unknown(self):
        for value in (0, None):
            self.side.set_total(SPHERES, value, SOURCE_TU)
            giver, bot = self.make([])
            outcome = self.give(giver)
            self.assertEqual(outcome.status, "skipped")
            self.assertEqual(bot.sent, [])

    def test_keep_is_left_on_the_account(self):
        giver, bot = self.make([[question(1000)], [success(1000)]])
        outcome = self.give(giver, SphereGiveSettings(enabled=True, keep=250))
        self.assertEqual(outcome.status, "given")
        self.assertEqual(bot.sent[0], "$givesp <@{}> 1000".format(MAIN_ID))
        self.assertEqual(self.side.spheres, 250)

    def test_stock_at_or_below_keep_does_nothing(self):
        giver, bot = self.make([])
        self.assertEqual(self.give(giver, SphereGiveSettings(enabled=True, keep=1250)).status, "skipped")
        self.assertEqual(bot.sent, [])

    def test_off_by_default(self):
        giver, bot = self.make([])
        self.assertEqual(self.give(giver, SphereGiveSettings()).reason, "off")
        self.assertEqual(bot.sent, [])

    def test_games_first(self):
        giver, bot = self.make([[question(1250)], [success(1250)]])
        outcome = self.give(giver, games=lambda: "sphere games are still available ($oh 1)")
        self.assertEqual(outcome.status, "skipped")
        self.assertIn("sphere games first", outcome.reason)
        self.assertEqual(bot.sent, [])
        self.assertEqual(self.give(giver, games=lambda: None).status, "given")

    def test_perk10_first_then_remainder_only(self):
        giver, bot = self.make([[question(250)], [success(250)]])
        outcome = self.give(giver, perk_first=lambda: "perk 10 upgrade comes first")
        self.assertEqual(outcome.status, "skipped")
        self.assertEqual(bot.sent, [])
        self.side.set_total(SPHERES, 250, SOURCE_TU)  # the upgrade spent 1,000
        self.assertEqual(self.give(giver).status, "given")
        self.assertEqual(bot.sent[0], "$givesp <@{}> 250".format(MAIN_ID))

    def test_busy_defers(self):
        giver, bot = self.make([])
        outcome = self.give(giver, busy=lambda: "rolling or claiming")
        self.assertEqual(outcome.status, "skipped")
        self.assertIn("busy", outcome.reason)
        self.assertEqual(bot.sent, [])

    def test_interval_gate(self):
        giver, bot = self.make([[question(1250)], [success(1250)]])
        self.assertEqual(self.give(giver).status, "given")
        self.side.set_total(SPHERES, 40, SOURCE_TU)
        self.now[0] = WHEN + datetime.timedelta(minutes=29)
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "skipped")
        self.assertIn("30 min", outcome.reason)
        self.assertEqual(len(bot.sent), 2)
        giver2, bot2 = self.make([[question(40)], [success(40)]])  # a new object: the gate survives (persisted)
        self.assertEqual(self.give(giver2).status, "skipped")
        self.now[0] = WHEN + datetime.timedelta(minutes=31)
        self.assertEqual(self.give(giver2).status, "given")
        self.assertEqual(bot2.sent[0], "$givesp <@{}> 40".format(MAIN_ID))

    def test_refuses_on_main_or_without_main_id_or_self(self):
        giver, bot = self.make([])
        self.assertIn("only a side", self.give(giver, role="main").reason)
        self.assertIn("not known", self.give(giver, main_id=None).reason)
        self.assertIn("itself", self.give(giver, main_id=SIDE_ID).reason)
        self.assertEqual(bot.sent, [])


class FlowTests(SphereGiveBase):
    def test_question_with_main_mentioned_is_answered(self):
        giver, bot = self.make([[question(1250, "to <@{}> ".format(MAIN_ID))], [success(1250)]])
        self.assertEqual(self.give(giver).status, "given")
        self.assertEqual(bot.sent[-1], "Y")

    def test_wrong_receiver_answers_n(self):
        giver, bot = self.make([[question(1250, "to <@{}> ".format(OTHER_ID))], None])
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(bot.sent[-1], "n")
        self.assertNotIn("Y", bot.sent)
        self.assertEqual(self.side.spheres, 1250)

    def test_amount_other_than_sent_answers_n(self):
        for asked in (1251, 1249, 5000):
            self.store.put("pside#1", "sphere_gives", None)
            giver, bot = self.make([[question(asked)], None])
            outcome = self.give(giver)
            self.assertEqual(outcome.status, "stopped", asked)
            self.assertEqual(bot.sent[-1], "n")
            self.assertNotIn("Y", bot.sent)

    def test_question_without_amount_answers_n(self):
        giver, bot = self.make([["SideUser, do you really want to give spheres ? (y/n/yes/no)"], None])
        self.assertEqual(self.give(giver).status, "stopped")
        self.assertNotIn("Y", bot.sent)

    def test_kakera_question_answers_n(self):
        giver, bot = self.make([["SideUser, do you really want to give 1250 {} ? (y/n/yes/no)".format(KAKERA_EMOJI)], None])
        self.assertEqual(self.give(giver).status, "stopped")
        self.assertNotIn("Y", bot.sent)

    def test_success_by_line(self):
        giver, bot = self.make([[question(1250)], [success(1250)]])
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "given")
        self.assertEqual(self.side.spheres, 0)
        self.assertEqual(self.main.spheres, 1350)
        self.assertTrue(any("Sphere give: gave 1,250 spheres" in text for _, text in self.logs))

    def test_success_by_check_reaction_on_our_Y(self):
        giver, bot = self.make([[question(1250)], ["ACK"]])
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "given", outcome)
        self.assertEqual(self.side.spheres, 0)
        self.assertEqual(bot.sent, ["$givesp <@{}> 1250".format(MAIN_ID), "Y"])

    def test_check_reaction_on_the_command_alone_is_not_success(self):
        giver, bot = self.make([["ACK"], None])
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "stopped")
        self.assertNotIn("Y", bot.sent)

    def test_unknown_reply_no_Y_and_logged_as_error_text(self):
        giver, bot = self.make([["SideUser, something unexpected happened with <@{}>".format(OTHER_ID)]])
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(bot.sent, ["$givesp <@{}> 1250".format(MAIN_ID)])
        level, text = self.logs[-1]
        self.assertEqual(level, "WARN")
        self.assertIn("Bot said:", text)
        self.assertIn("something unexpected", text)
        self.assertNotIn(OTHER_ID, text)  # ids masked
        from mudae_core.logs import classify_kind
        self.assertEqual(classify_kind(text, level), "ERROR")
        self.assertEqual(self.side.spheres, 1250)

    def test_asks_for_amount_is_not_answered(self):
        giver, bot = self.make([["SideUser, how many spheres do you want to give?"]])
        self.assertEqual(self.give(giver).status, "stopped")
        self.assertEqual(len(bot.sent), 1)

    def test_stop_sign_reaction_stops(self):
        giver, bot = self.make([["REFUSE"]])
        self.assertEqual(self.give(giver).status, "stopped")
        self.assertEqual(len(bot.sent), 1)

    def test_question_timeout(self):
        giver, bot = self.make([None], timeout=0.1)
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "stopped")
        self.assertIn("did not ask", outcome.reason)
        self.assertEqual(self.side.spheres, 1250)

    def test_result_timeout_makes_stock_unknown(self):
        giver, bot = self.make([[question(1250)], None], timeout=0.1)
        outcome = self.give(giver)
        self.assertEqual(outcome.status, "stopped")
        self.assertIsNone(self.side.spheres)
        self.assertEqual(bot.sent[-1], "Y")

    def test_backoff_grows_and_blocks_retry(self):
        giver, bot = self.make([None, None], timeout=0.05)
        self.give(giver)
        first = giver._retry_at - giver._monotonic()
        self.assertIn("backing off", giver.blocker(SphereGiveSettings(enabled=True), role="side", own_id=SIDE_ID,
                                                   main_id=MAIN_ID, stock=5))
        self.assertGreater(first, 500)

    def test_unrelated_messages_are_ignored(self):
        other = "OtherUser, do you really want to give 1250 {} ? (y/n/yes/no)".format(SPHERE_EMOJI)
        stray = "<@{}> just gifted 7 {} to <@1>".format(OTHER_ID, SPHERE_EMOJI)
        giver, bot = self.make([[other, stray, question(1250)], [success(1250)]])
        self.assertEqual(self.give(giver).status, "given")


class ButtonTests(SphereGiveBase):
    def press(self, giver, keep=0, **overrides):
        options = dict(role="side", own_id=SIDE_ID, own_names=("SideUser",), main_id=MAIN_ID,
                       totals=self.side, main_totals=self.main, total_wait_seconds=0.5, busy_wait_seconds=0.5,
                       poll_seconds=0.01)
        options.update(overrides)
        return giver.give_all_now(CHANNEL, keep=keep, **options)

    def test_happy_path_ignores_interval(self):
        self.store.put("pside#1", "sphere_gives", {"last_at": WHEN.isoformat()})
        giver, bot = self.make([[question(1250)], [success(1250)]])
        outcome = asyncio.run(self.press(giver))
        self.assertEqual(outcome.status, "given", outcome)
        self.assertEqual(bot.sent, ["$givesp <@{}> 1250".format(MAIN_ID), "Y"])
        self.assertIn("gave 1,250", giver.manual_status)

    def test_unknown_stock_waits_never_sends_tu_and_times_out(self):
        self.side.set_total(SPHERES, None, SOURCE_TU)
        giver, bot = self.make([])
        outcome = asyncio.run(self.press(giver))
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(bot.sent, [])

    def test_unknown_stock_then_tu_arrives(self):
        self.side.set_total(SPHERES, None, SOURCE_TU)
        giver, bot = self.make([[question(1250)], [success(1250)]])

        async def scenario():
            task = asyncio.ensure_future(self.press(giver))
            await asyncio.sleep(0.05)
            self.side.set_total(SPHERES, 1250, SOURCE_TU)
            return await task

        self.assertEqual(asyncio.run(scenario()).status, "given")

    def test_busy_defers_then_runs(self):
        state = {"n": 0}

        def busy():
            state["n"] += 1
            return "rolling" if state["n"] < 4 else None

        giver, bot = self.make([[question(1250)], [success(1250)]])
        self.assertEqual(asyncio.run(self.press(giver, busy=busy)).status, "given")
        self.assertIn("deferred", " ".join(text for _, text in self.logs))

    def test_games_wait(self):
        giver, bot = self.make([])
        outcome = asyncio.run(self.press(giver, games=lambda: "a sphere game is being played"))
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(bot.sent, [])

    def test_refuses_on_main_and_without_main(self):
        giver, bot = self.make([])
        self.assertEqual(asyncio.run(self.press(giver, role="main")).status, "refused")
        giver2, _ = self.make([])
        self.assertEqual(asyncio.run(self.press(giver2, main_id=None)).status, "refused")
        self.assertEqual(bot.sent, [])

    def test_keep_respected_and_nothing_to_give(self):
        giver, bot = self.make([[question(1000)], [success(1000)]])
        self.assertEqual(asyncio.run(self.press(giver, keep=250)).status, "given")
        giver2, bot2 = self.make([])
        self.side.set_total(SPHERES, 100, SOURCE_TU)
        self.assertEqual(asyncio.run(self.press(giver2, keep=250)).status, "skipped")
        self.assertEqual(bot2.sent, [])

    def test_cooldown_and_double_press(self):
        giver, bot = self.make([[question(1250)], [success(1250)]])
        self.assertEqual(asyncio.run(self.press(giver)).status, "given")
        self.side.set_total(SPHERES, 10, SOURCE_TU)
        outcome = asyncio.run(self.press(giver))
        self.assertEqual(outcome.status, "ignored")
        self.assertEqual(len(bot.sent), 2)

    def test_wrong_amount_answers_n(self):
        giver, bot = self.make([[question(99)], None])
        self.assertEqual(asyncio.run(self.press(giver)).status, "stopped")
        self.assertEqual(bot.sent[-1], "n")


if __name__ == "__main__":
    unittest.main()
