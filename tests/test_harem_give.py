import asyncio
import datetime
import os
import tempfile
import unittest
from types import SimpleNamespace as NS

from mudae_core.account_state import AccountStateStore
from mudae_core.harem_give import (
    HaremGiveSettings, HaremGiver, PageSelection, check_gift_question, parse_gift_done, parse_gift_question,
    parse_page_selection, parse_who_question, renumber_after_give, resolve_pages, round_message, split_rounds,
    validate_harem_give_settings,
)
from tests.test_harem_list import MMRK_DESCRIPTION, list_message, mmi_message

SIDE_ID = "300000000000000003"
MAIN_ID = "100000000000000001"
WHEN = datetime.datetime(2026, 11, 28, 12, 0, tzinfo=datetime.timezone.utc)
CHANNEL = NS(id=555)
FREE = "(Enhanced multitrade: this gift is free)"


def who():
    return "<@{}>, Who do you want to give to <@{}> ?".format(SIDE_ID, MAIN_ID)


def confirm(pages, giver="SideUser", extra=FREE):
    text = "<@{}>, {} wants to give you Harem page(s) n°{}. Do you confirm? (y/n/yes/no)".format(
        MAIN_ID, giver, ", ".join(map(str, pages)))
    return text + ("\n" + extra if extra else "")


def done(pages):
    return "Harem page(s) n°{} given to <@{}>".format(", ".join(map(str, pages)), MAIN_ID)


class FakeMudae:
    """Plays the game bot for both accounts. ``pages`` is the side's current page count."""

    def __init__(self, giver_ref, pages=10, *, mm_owner="SideUser", script=None, total_value=None):
        self.giver_ref = giver_ref
        self.pages = pages
        self.mm_owner = mm_owner
        self.script = script or {}
        self.side_sent = []
        self.main_sent = []
        self.next_id = 1000
        self.pending_pages = None
        self.total_value = total_value
        self.main_fails = False

    def _emit(self, text=None, message=None):
        self.next_id += 1
        loop = asyncio.get_running_loop()
        giver = self.giver_ref[0]
        if message is None:
            message = NS(id=self.next_id, channel=CHANNEL, embeds=[], reference=None, components=[], content=text)
        else:
            message.id = self.next_id
        loop.call_soon(giver.on_message, message, text if text is not None else "")

    def _reply(self, key, default):
        value = self.script.get(key, "DEFAULT")
        if isinstance(value, list):
            value = value.pop(0) if value else "DEFAULT"
        if value == "DEFAULT":
            value = default
        if value is None:
            return
        if value == "REFUSE":
            asyncio.get_running_loop().call_soon(self.giver_ref[0].on_refused, self.next_id)
            return
        self._emit(value)

    async def send(self, channel, text):
        self.side_sent.append(text)
        self.next_id += 1
        my_id = self.next_id
        if text == "$mm":
            self._emit(message=list_message(0, owner=self.mm_owner, pages=self.pages))
        elif text == "$mmi":
            self._emit(message=mmi_message(0, total=self.pages * 15))
        elif text == "$mmrk":
            self._emit(message=list_message(0, description=MMRK_DESCRIPTION, pages=self.pages))
        elif text.startswith("$give"):
            self._reply("give", who())
        elif text.startswith("Page "):
            self.pending_pages = [int(value) for value in text.split()[1:]]
            self._reply("page", confirm(self.pending_pages))
        elif text == "$exit":
            self._reply("exit", "The procedure has been stopped.")
        return NS(id=my_id)

    async def answer(self, channel_id, text):
        if self.main_fails:
            return None
        self.main_sent.append(text)
        self.next_id += 1
        my_id = self.next_id
        if text == "y":
            pages = self.pending_pages
            self.pages -= len(pages)
            self._reply("y", done(pages))
        return NS(id=my_id)


class Partner:
    def __init__(self, fake, busy=None):
        self.fake = fake
        self.key = "pmain#1"
        self.name = "MainUser"
        self.user_id = int(MAIN_ID)
        self.busy = busy

    def busy_reason(self):
        return self.busy

    async def answer(self, channel_id, text):
        return await self.fake.answer(channel_id, text)


class SelectionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_page_selection("").kind, "default")
        self.assertEqual(parse_page_selection("3"), PageSelection("first", count=3))
        self.assertEqual(parse_page_selection("1-3").pages, (1, 2, 3))
        self.assertEqual(parse_page_selection("2 4 5").pages, (2, 4, 5))
        self.assertEqual(parse_page_selection("2,4-6").pages, (2, 4, 5, 6))
        for bad in ("0", "3-1", "x", "1-a"):
            with self.assertRaises(ValueError):
                parse_page_selection(bad)

    def test_resolve(self):
        self.assertEqual(resolve_pages(PageSelection("default"), 12, up_to=10), list(range(1, 11)))
        self.assertEqual(resolve_pages(PageSelection("default"), 4), [1, 2, 3, 4])
        self.assertEqual(resolve_pages(PageSelection("default"), 10, up_to=10, keep_first=2), list(range(3, 11)))
        self.assertEqual(resolve_pages(parse_page_selection("2 4 50"), 10), [2, 4])
        self.assertEqual(resolve_pages(parse_page_selection("3"), 2), [1, 2])
        self.assertEqual(resolve_pages(parse_page_selection("1-2"), 10, keep_first=2), [])

    def test_rounds_and_renumber(self):
        pages = list(range(1, 1001))
        rounds = split_rounds(pages, max_length=1900)
        self.assertGreater(len(rounds), 1)
        self.assertTrue(all(len(round_message(r)) <= 1900 for r in rounds))
        self.assertEqual(sum(rounds, []), pages)
        self.assertEqual(renumber_after_give([4, 6, 9], [1, 2, 3]), [1, 3, 6])
        self.assertEqual(renumber_after_give([2, 5], [3]), [2, 4])

    def test_settings(self):
        settings = HaremGiveSettings.from_preset({})
        self.assertFalse(settings.enabled)
        self.assertEqual((settings.trigger, settings.check_hours, settings.daily_cap, settings.keep_first),
                         ("pages", 6, 1, 0))
        self.assertEqual(HaremGiveSettings.from_preset({"harem_give_trigger": "value"}).check_command, "mmrk")
        self.assertEqual(HaremGiveSettings.from_preset({"harem_give_trigger": "characters"}).check_command, "mmi")
        self.assertEqual(validate_harem_give_settings({}), [])
        self.assertTrue(validate_harem_give_settings({"harem_check_hours": 0}))
        self.assertTrue(validate_harem_give_settings({"harem_give_pages_text": "a-b"}))
        self.assertTrue(validate_harem_give_settings({"harem_give_trigger": "kakera"}))


class ParserTests(unittest.TestCase):
    def test_bot_texts(self):
        self.assertEqual(parse_who_question(who()), (SIDE_ID, MAIN_ID))
        question = parse_gift_question(confirm([1]))
        self.assertEqual((question.receiver_id, question.giver_name, question.pages, question.free, question.extra),
                         (MAIN_ID, "SideUser", (1,), True, ""))
        self.assertEqual(parse_gift_question(confirm([1, 2, 3], extra="")).pages, (1, 2, 3))
        self.assertEqual(parse_gift_done(done([1, 2])), ((1, 2), MAIN_ID))
        costly = parse_gift_question(confirm([1], extra="This trade costs 500 kakera."))
        self.assertIn("costs", check_gift_question(costly, main_id=MAIN_ID, giver_names=["SideUser"], pages=[1]))
        self.assertIsNone(check_gift_question(question, main_id=MAIN_ID, giver_names=["sideuser"], pages=[1]))
        self.assertIn("giver", check_gift_question(question, main_id=MAIN_ID, giver_names=["Other"], pages=[1]))
        self.assertIn("instead of", check_gift_question(question, main_id=MAIN_ID, giver_names=["SideUser"], pages=[2]))


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AccountStateStore(os.path.join(self.tmp.name, "state.json"))
        self.logs = []
        self.now = [WHEN]

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, pages=10, **kwargs):
        ref = [None]
        fake = FakeMudae(ref, pages, **kwargs)
        self.store = AccountStateStore(os.path.join(self.tmp.name, "state{}.json".format(len(self.logs) + id(fake))))

        async def wait(seconds):
            return True

        async def click(button):
            return True

        giver = HaremGiver(key="pside#1", store=self.store, send=fake.send, click=click, wait=wait,
                           log=lambda message, level: self.logs.append((level, message)),
                           clock=lambda: self.now[0], step_timeout=0.3, answer_delay=(0, 0))
        giver.reader.reply_timeout = 0.3
        ref[0] = giver
        return giver, fake

    def give(self, giver, fake, settings=None, partner="DEFAULT", **overrides):
        options = dict(role="side", own_id=SIDE_ID, own_names=("SideUser",), main_id=MAIN_ID,
                       partner=Partner(fake) if partner == "DEFAULT" else partner)
        options.update(overrides)
        settings = settings or HaremGiveSettings(enabled=True, pages=10)
        return asyncio.run(giver.maybe_give(CHANNEL, settings, **options))

    def test_happy_path_pages(self):
        giver, fake = self.make(pages=10)
        outcome = self.give(giver, fake)
        self.assertEqual(outcome.status, "given", outcome)
        self.assertEqual(fake.side_sent, ["$mm", "$give <@{}>".format(MAIN_ID), "Page " + " ".join(map(str, range(1, 11)))])
        self.assertEqual(fake.main_sent, ["y"])
        self.assertEqual(giver.gives_today(), 1)
        self.assertTrue(any("given to the main" in message for _level, message in self.logs))

    def test_below_trigger_and_check_interval(self):
        giver, fake = self.make(pages=8)
        outcome = self.give(giver, fake)
        self.assertEqual(outcome.status, "skipped")
        self.assertIn("below 10", outcome.reason)
        again = self.give(giver, fake)
        self.assertIn("next harem check", again.reason)
        self.assertEqual(fake.side_sent, ["$mm"])  # never more than once per interval
        self.now[0] = WHEN + datetime.timedelta(hours=6, minutes=1)
        self.give(giver, fake)
        self.assertEqual(fake.side_sent, ["$mm", "$mm"])

    def test_trigger_characters_and_value(self):
        giver, fake = self.make(pages=10)  # $mmi says 150 characters
        settings = HaremGiveSettings(enabled=True, trigger="characters", characters=150)
        self.assertEqual(self.give(giver, fake, settings).status, "given")
        self.assertEqual(fake.side_sent[:3], ["$mmi", "$mm", "$give <@{}>".format(MAIN_ID)])
        giver, fake = self.make(pages=3)
        settings = HaremGiveSettings(enabled=True, trigger="value", value=3_000_000)
        outcome = self.give(giver, fake, settings)
        self.assertIn("harem value 2,610,402 is below", outcome.reason)
        giver, fake = self.make(pages=3)
        settings = HaremGiveSettings(enabled=True, trigger="value", value=2_000_000, keep_first=1)
        self.assertEqual(self.give(giver, fake, settings).status, "given")
        self.assertEqual(fake.side_sent[-1], "Page 2 3")

    def test_main_not_running(self):
        giver, fake = self.make()
        outcome = self.give(giver, fake, partner=None)
        self.assertEqual(outcome.status, "skipped")
        self.assertIn("not running", outcome.reason)
        self.assertEqual(fake.side_sent, [])

    def test_main_busy_defers(self):
        giver, fake = self.make()
        outcome = self.give(giver, fake, partner=Partner(fake, busy="rolling"))
        self.assertEqual(outcome.status, "skipped")
        self.assertIn("main is busy", outcome.reason)
        self.assertEqual(fake.side_sent, ["$mm"])
        self.assertIsNone(giver.last_check())  # checks again soon

    def test_side_busy_defers(self):
        giver, fake = self.make()
        outcome = self.give(giver, fake, busy=lambda: "claiming")
        self.assertEqual((outcome.status, fake.side_sent), ("skipped", []))

    def test_wrong_giver_or_pages_answers_n(self):
        for reply in (confirm([1], giver="SomeoneElse"), confirm([2, 3])):
            giver, fake = self.make(pages=10, script={"page": reply})
            outcome = self.give(giver, fake)
            self.assertEqual(outcome.status, "stopped")
            self.assertEqual(fake.main_sent, ["n"])
            self.assertNotIn("$exit", fake.side_sent)
            self.assertEqual(outcome.bot_text, reply)

    def test_cost_stated_answers_n(self):
        reply = confirm(list(range(1, 11)), extra="This gift costs 2,000 kakera.")
        giver, fake = self.make(pages=10, script={"page": reply})
        outcome = self.give(giver, fake)
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(fake.main_sent, ["n"])
        self.assertIn("free shape", outcome.reason)

    def test_main_cannot_answer_then_giver_exits(self):
        giver, fake = self.make(pages=10, script={"page": confirm([1], giver="SomeoneElse")})
        fake.main_fails = True
        outcome = self.give(giver, fake)
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(fake.side_sent[-1], "$exit")

    def test_timeouts_cancel_cleanly(self):
        for step in ("give", "page", "y"):
            giver, fake = self.make(pages=10, script={step: None})
            outcome = self.give(giver, fake)
            self.assertEqual(outcome.status, "stopped", step)
            if step == "give":
                self.assertEqual(fake.side_sent[-1], "$exit")
                self.assertEqual(fake.main_sent, [])
            elif step == "page":
                self.assertEqual(fake.side_sent[-1], "$exit")
                self.assertEqual(fake.main_sent, [])
            else:
                self.assertEqual(fake.main_sent, ["y"])
                self.assertEqual(fake.side_sent[-1], "$exit")
                self.assertEqual(giver.gives_today(), 1)  # may have happened: counts

    def test_bot_stops_procedure(self):
        giver, fake = self.make(pages=10, script={"give": "<@{}>, The procedure has been stopped.".format(SIDE_ID)})
        outcome = self.give(giver, fake)
        self.assertEqual(outcome.status, "stopped")
        self.assertNotIn("$exit", fake.side_sent)

    def test_refused_command(self):
        giver, fake = self.make(pages=10, script={"give": "REFUSE"})
        outcome = self.give(giver, fake)
        self.assertIn("refused", outcome.reason)

    def test_daily_cap_and_backoff(self):
        giver, fake = self.make(pages=10)
        self.assertEqual(self.give(giver, fake).status, "given")
        self.now[0] = WHEN + datetime.timedelta(hours=7)
        outcome = self.give(giver, fake)
        self.assertIn("daily limit", outcome.reason)
        giver, fake = self.make(pages=10, script={"give": None})
        self.give(giver, fake)
        self.store.put("pside#1", "harem_check", None)
        self.assertIn("backing off", self.give(giver, fake).reason)

    def test_long_list_split_into_rounds_rereads_list(self):
        giver, fake = self.make(pages=1200)
        settings = HaremGiveSettings(enabled=True, pages=1000)
        outcome = self.give(giver, fake, settings)
        self.assertEqual(outcome.status, "given", outcome)
        page_messages = [text for text in fake.side_sent if text.startswith("Page ")]
        self.assertGreater(len(page_messages), 1)
        self.assertEqual(fake.main_sent, ["y"] * len(page_messages))
        # $mm re-read between rounds; the next round starts again at page 1 (pages shifted).
        self.assertEqual(fake.side_sent.count("$mm"), len(page_messages))
        self.assertTrue(page_messages[1].startswith("Page 1 2 "))
        given = sum(len(text.split()) - 1 for text in page_messages)
        self.assertEqual(given, 1000)
        self.assertEqual(fake.pages, 200)
        self.assertEqual(giver.gives_today(), 1)

    def test_unexpected_count_between_rounds_stops(self):
        giver, fake = self.make(pages=1200)
        original = fake.answer

        async def answer(channel_id, text):
            receipt = await original(channel_id, text)
            fake.pages += 1  # someone else changed the harem meanwhile
            return receipt

        fake.answer = answer
        outcome = self.give(giver, fake, HaremGiveSettings(enabled=True, pages=1000))
        self.assertEqual(outcome.status, "stopped")
        self.assertIn("expected", outcome.reason)
        self.assertIn("after 1 round", outcome.reason)

    def test_off_role_main_unknown(self):
        for settings, overrides, words in (
                (HaremGiveSettings(enabled=False), {}, "off"),
                (None, {"role": "main"}, "only a side"),
                (None, {"main_id": ""}, "not known"),
                (None, {"main_id": SIDE_ID}, "itself")):
            giver, fake = self.make()
            outcome = self.give(giver, fake, settings, **overrides)
            self.assertIn(words, outcome.reason)
            self.assertEqual(fake.side_sent, [])

    def test_foreign_list_is_not_used(self):
        giver, fake = self.make(pages=10, mm_owner="OtherUser")
        outcome = self.give(giver, fake)
        self.assertEqual(outcome.status, "stopped")
        self.assertIn("harem check failed", outcome.reason)
        self.assertNotIn("$give <@{}>".format(MAIN_ID), fake.side_sent)


class ActivityEventTests(unittest.TestCase):
    def test_log_lines_become_events(self):
        from mudae_core.activity_events import ActivityClassifier
        classify = ActivityClassifier().classify
        self.assertEqual(classify("SUCCESS", "Harem give: gave 10 harem page(s) to the main in 1 round(s) (give 1 today).")[0][0],
                         "harem_give")
        self.assertEqual(classify("WARN", "Harem give stopped: no «given to» confirmation in time. Next try in 10 min.")[0][0],
                         "harem_give_stopped")
        events = classify("SUCCESS", "Give all kakera: gave 45,132 kakera to the main.")
        self.assertEqual(events[0], ("kakera_give_now", {"kakera": 45132, "message": "Give all kakera: gave 45,132 kakera to the main"}))
        self.assertEqual(classify("INFO", "Give all kakera: not given — Only 500 kakera — the minimum is 1,000.")[0][0],
                         "kakera_give_now")


if __name__ == "__main__":
    unittest.main()
