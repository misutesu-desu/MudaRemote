"""A4.2: the app notices what the player does by hand (mudae_core.manual_commands).

A small model of mudae_bot.observe_manual_activity (same ledger/watch calls,
same order) plus the real KakeraGiver for «the player answered our question».
Names, ids and numbers are made up; nothing talks to Discord.
"""

import asyncio
import datetime
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mudae_core import manual_commands as mc
from mudae_core.account_state import AccountStateStore
from mudae_core.kakera_give import BotReply, GiveSettings, KakeraGiver
from mudae_core.totals import KAKERA, SOURCE_MANUAL, SOURCE_TU, SPHERES, AccountTotals, TotalsBook

ROOT = Path(__file__).resolve().parents[1]
OWN_ID = 300000000000000003
MAIN_ID = "100000000000000001"
CHANNEL = 555
WHEN = datetime.datetime(2026, 11, 28, 12, 0, tzinfo=datetime.timezone.utc)
TU_REPLY = (
    "**SideUser**, you can't claim for another **28** min.\n"
    "You have **0** rolls left. Next rolls reset in **28** min.\n"
    "Power: **30%**\n"
    "Stock: **119,937** <:kakera:469835869059153940>\n"
    "$rt is available!\n"
    "**0** $oh left for today, **0** $oc, **0** $oq and **0** $ot.\n"
    "Stock: **1,225** <:spR:1234567890>\n"
)


class Clock:
    def __init__(self):
        self.now = 50.0

    def __call__(self):
        return self.now


class Account:
    """The bot's own-message / bot-reply handling for one account (model)."""

    def __init__(self):
        self.clock = Clock()
        self.sends = mc.AppSendLedger(monotonic=self.clock)
        self.watch = mc.ManualCommandWatch(monotonic=self.clock)
        self.totals = AccountTotals("Side", clock=lambda: WHEN)
        self.tu_applied = 0
        self.logs = []
        self.next_id = 1

    def app_send(self, text, echo_first=False):
        """guarded_send: record, send, confirm. ``echo_first``: the gateway echo beats the reply of send()."""
        token = self.sends.expect(CHANNEL, text)
        self.next_id += 1
        message_id = self.next_id
        if echo_first:
            self.own_message(text, message_id)
        self.sends.confirm(token, message_id)
        if not echo_first:
            self.own_message(text, message_id)
        return message_id

    def own_message(self, text, message_id=None):
        if message_id is None:
            self.next_id += 1
            message_id = self.next_id
        if self.sends.is_app_message(message_id, CHANNEL, text):
            return None
        kind, word = mc.classify_command(text, "$", "m")
        if kind is None:
            return None
        self.watch.begin(kind, word, CHANNEL, message_id, text)
        if kind in mc.KAKERA_CHANGING:
            self.totals.set_total(KAKERA, None, SOURCE_MANUAL)
        if kind in mc.SPHERE_CHANGING:
            self.totals.set_total(SPHERES, None, SOURCE_MANUAL)
        return kind

    def bot_reply(self, text, captured_by_app=False):
        self.watch.on_bot_reply(CHANNEL)
        if not captured_by_app and "Stock:" in text and self.watch.take_tu(CHANNEL):
            self.totals.apply_tu(text)
            self.tu_applied += 1
            self.logs.append(mc.saw_tu_line())


class LedgerTests(unittest.TestCase):
    def test_app_sent_message_is_not_manual(self):
        account = Account()
        self.assertIsNone(account.own_message("chat") or None)
        account.app_send("$tu")
        account.app_send("$tu", echo_first=True)
        self.assertIsNone(account.watch.current())
        self.assertEqual(account.own_message("$tu"), mc.TU)  # typed by the player

    def test_expectation_expires(self):
        clock = Clock()
        ledger = mc.AppSendLedger(monotonic=clock)
        ledger.expect(CHANNEL, "$tu")
        clock.now += mc.APP_SEND_MATCH_SECONDS + 1
        self.assertFalse(ledger.is_app_message(9, CHANNEL, "$tu"))
        ledger.expect(CHANNEL, "$tu")
        self.assertFalse(ledger.is_app_message(9, 777, "$tu"))  # another channel
        self.assertTrue(ledger.is_app_message(10, CHANNEL, "  $TU "))
        self.assertTrue(ledger.is_app_message(10, CHANNEL, "anything"))  # by id from now on

    def test_classify(self):
        cases = {
            "$tu": mc.TU, "$TU": mc.TU, "$m": mc.ROLL, "$wa": mc.ROLL, "$rt": mc.RT,
            "$givek <@1> 500": mc.GIVEK, "$givesp <@1> 100": mc.GIVESP, "$give <@1>": mc.GIVE,
            "$oi Name $ 10": mc.OI, "$oic A $ B $ 10": mc.OIC, "$oh": mc.SPHERE_GAME, "$oc 1": mc.SPHERE_GAME,
            "$dk": mc.DK, "$daily": mc.DAILY, "$us 5": mc.US, "$mk": mc.MK, "$im Rem": mc.OTHER,
            "y": mc.ANSWER, "N": mc.ANSWER, "yes": mc.ANSWER, "cancel": mc.ANSWER, "$exit": mc.ANSWER,
        }
        for text, kind in cases.items():
            self.assertEqual(mc.classify_command(text, "$", "m")[0], kind, text)
        self.assertEqual(mc.classify_command("hello there", "$")[0], None)
        self.assertEqual(mc.classify_command("!tu", "!")[0], mc.TU)
        self.assertEqual(mc.mentioned_ids("$givek <@123> 5"), ["123"])

    def test_parse_marriage(self):
        self.assertEqual(mc.parse_marriage("💖 **SideUser** and **Rem** are now married! 💖"), ("SideUser", "Rem"))
        self.assertIsNone(mc.parse_marriage("Rem belongs to someone"))


class ManualTuTests(unittest.TestCase):
    def test_manual_tu_refreshes_state_and_totals(self):
        account = Account()
        self.assertEqual(account.own_message("$tu"), mc.TU)
        self.assertEqual(account.watch.busy_reason(), "you are using $tu by hand")
        account.bot_reply(TU_REPLY)
        self.assertEqual((account.totals.kakera, account.totals.spheres), (119937, 1225))
        self.assertEqual(account.tu_applied, 1)
        self.assertEqual(account.logs, ["saw your $tu — state refreshed"])
        self.assertIsNone(account.watch.current())  # the reply ends the busy window

    def test_app_sent_tu_is_not_double_counted(self):
        account = Account()
        account.app_send("$tu")
        account.bot_reply(TU_REPLY, captured_by_app=True)
        account.bot_reply(TU_REPLY)  # a second copy/edit: still not the player's
        self.assertEqual(account.tu_applied, 0)
        # the player's $tu is read once
        account.own_message("$tu")
        account.bot_reply(TU_REPLY)
        account.bot_reply(TU_REPLY)
        self.assertEqual(account.tu_applied, 1)

    def test_bot_wiring_reads_only(self):
        source = (ROOT / "mudae_bot.py").read_text(encoding="utf-8")
        start = source.index("    def apply_observed_tu(content):")
        body = source[start:source.index("    def observe_manual_claim(")]
        for forbidden in ("guarded_send", "send_tu_command", "claim_character", "start_roll_commands",
                          "request_status_refresh", "mark_status_dirty"):
            self.assertNotIn(forbidden, body)
        self.assertIn("note_tu_totals(content)", body)
        self.assertIn("tokens.append(client.app_sends.expect(", source)
        self.assertIn("observe_manual_activity(message, tu_captured)", source)


class ManualGiveTests(unittest.TestCase):
    def test_manual_give_marks_stock_unknown(self):
        account = Account()
        account.totals.set_total(KAKERA, 50000, SOURCE_TU)
        account.totals.set_total(SPHERES, 900, SOURCE_TU)
        account.own_message("$givek <@{}> 500".format(MAIN_ID))
        self.assertIsNone(account.totals.kakera)
        self.assertEqual(account.totals.spheres, 900)
        account.own_message("$oic A $ B $ 10")
        self.assertIsNone(account.totals.spheres)

    def test_receiver_of_ours_is_marked_unknown_too(self):
        book = TotalsBook()
        main = book.account("p#1", "Main")
        book.note_user_id("p#1", MAIN_ID)
        main.set_total(KAKERA, 10, SOURCE_TU)
        receiver = book.by_user_id(mc.mentioned_ids("$givek <@{}> 5".format(MAIN_ID))[0])
        self.assertIs(receiver, main)


class BusyWindowTests(unittest.TestCase):
    def test_busy_until_reply_or_eight_seconds(self):
        clock = Clock()
        watch = mc.ManualCommandWatch(monotonic=clock)
        watch.begin(mc.GIVEK, "givek", CHANNEL, 1)
        self.assertIn("givek", watch.busy_reason())
        clock.now += 7.9
        self.assertIsNotNone(watch.busy_reason())
        clock.now += 0.2
        self.assertIsNone(watch.busy_reason())
        watch.begin(mc.DK, "dk", CHANNEL, 2)
        self.assertIsNone(watch.on_bot_reply(777))  # another channel
        self.assertIsNotNone(watch.busy_reason())
        self.assertIsNotNone(watch.on_bot_reply(CHANNEL))
        self.assertIsNone(watch.busy_reason())


class UserAnswersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AccountStateStore(os.path.join(self.tmp.name, "state.json"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_player_answers_the_apps_question(self):
        totals = AccountTotals("Side", clock=lambda: WHEN)
        totals.set_total(KAKERA, 45132, SOURCE_TU)
        sent = []
        watch = mc.ManualCommandWatch()
        state = {"answered": None}
        holder = []

        async def send(channel, text):
            sent.append(text)
            message_id = 1000 + len(sent)
            if text.startswith("$givek"):
                asyncio.get_running_loop().call_soon(holder[0].on_reply, BotReply(
                    message_id + 50, channel.id,
                    "SideUser, do you really want to give 45132 <:kakera:469835869059153940> ? (y/n/yes/no)"))
            return SimpleNamespace(id=message_id)

        async def wait(seconds):
            # While the app waits to answer, the player types «n» (mudae_bot.answer_open_question).
            if holder[0].state == "answering" and state["answered"] is None:
                state["answered"] = holder[0].user_answered()
                watch.begin(mc.ANSWER, "n", CHANNEL, 9)
            await asyncio.sleep(0)
            return True

        giver = KakeraGiver(key="p#2", store=self.store, send=send, wait=wait, log=lambda *a: None,
                            clock=lambda: WHEN, question_timeout=0.5, result_timeout=0.5, answer_delay=(0, 0))
        holder.append(giver)
        outcome = asyncio.run(giver.maybe_give(
            SimpleNamespace(id=CHANNEL), GiveSettings(enabled=True, threshold=45000, give_extra=True, daily_cap=3),
            role="side", own_id=str(OWN_ID), own_names=("SideUser",), main_id=MAIN_ID,
            totals=totals, main_totals=None, busy=watch.busy_reason,
        ))
        self.assertTrue(state["answered"])
        self.assertEqual(outcome.status, "stopped")
        self.assertIn("answered the game bot yourself", outcome.reason)
        self.assertEqual(len(sent), 1)  # only the $givek: no «y», no «n» after the player's answer
        self.assertEqual(self.store.gives_today("p#2", WHEN.date()), 0)  # never counted toward the cap
        self.assertFalse(giver.user_answered())  # nothing open any more

    def test_user_answered_without_open_question(self):
        giver = KakeraGiver(key="p#3", store=self.store, send=None, wait=None, log=lambda *a: None)
        self.assertFalse(giver.user_answered())


if __name__ == "__main__":
    unittest.main()
