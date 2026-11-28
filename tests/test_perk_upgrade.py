import asyncio
import datetime
import os
import tempfile
import unittest
from types import SimpleNamespace as NS

from mudae_core.account_state import AccountStateStore
from mudae_core.perk_upgrade import (
    COMMAND_LENGTH_LIMIT, PERK10_DEFAULTS, Perk10Settings, PerkUpgrader, build_commands, normalize_name,
    parse_not_found, parse_oic_question, parse_oi_question, command_for, sphere_games_pending, upgrade_count, validate_perk10_settings,
)
from mudae_core.totals import SPHERES, AccountTotals
from tests.test_harem_list import list_message

OWN_ID = "200000000000000002"
WHEN = datetime.datetime(2026, 11, 28, 12, 0, tzinfo=datetime.timezone.utc)
CHANNEL = NS(id=555)
SPHERE = "<:spR:1>"


def page_names(page, per_page=15):
    return ["Made Up Character {}-{}".format(page, index) for index in range(1, per_page + 1)]


def question(cost, count, not_found=()):
    text = "Do you really want to spend {:,} {} for {} characters? (y/n/yes/no)\nPerks upgraded:\n\n" \
           "[10] (x{})  The first $oh of the day generates +4 spheres".format(cost, SPHERE, count, count)
    if not_found:
        text += "\nCharacters not found: " + ", ".join(name.lower() for name in not_found)
    return text


class FakeMudae:
    """Plays the game bot: $mmz- pages, the $oic question and the ✅ on Y."""

    def __init__(self, ref, pages=None, *, unknown=(), script=None, owner="TestUser"):
        self.ref = ref
        self.pages = pages if pages is not None else [page_names(1), page_names(2), page_names(3)]
        self.unknown = {name.casefold() for name in unknown}
        self.script = script or {}
        self.sent = []
        self.clicks = 0
        self.next_id = 1000
        self.list_id = None
        self.current = 1
        self.owner = owner
        self.pending = None

    def _emit_text(self, text, reference=None):
        self.next_id += 1
        message = NS(id=self.next_id, channel=CHANNEL, embeds=[], components=[], content=text,
                     reference=NS(message_id=reference) if reference else None)
        asyncio.get_running_loop().call_soon(self.ref[0].on_message, message, text)

    def _list(self, page):
        names = self.pages[page - 1] if self.pages else []
        return list_message(self.list_id, owner=self.owner, page=page, pages=max(1, len(self.pages)),
                            description="\n".join(names))

    def _script(self, key, default):
        value = self.script.get(key, "DEFAULT")
        if isinstance(value, list):
            value = value.pop(0) if value else "DEFAULT"
        return default if value == "DEFAULT" else value

    async def send(self, channel, text):
        self.sent.append(text)
        self.next_id += 1
        my_id = self.next_id
        loop = asyncio.get_running_loop()
        if text == "$mmz-":
            self.next_id += 1
            self.list_id = self.next_id
            self.current = 1
            loop.call_soon(self.ref[0].on_message, self._list(1), "")
        elif text.startswith("$oic ") or text.startswith("$oi "):
            self.oic_id = my_id
            body = text.split(" ", 1)[1]
            parts = [part.strip() for part in body.split("$")]
            assert parts[-1] == "10", text
            names = parts[:-1]
            missing = [name for name in names if name.casefold() in self.unknown]
            count = len(names) - len(missing)
            self.pending = count
            reply = self._script("oic", question(count * 1000, count, missing) if count else
                                 "Characters not found: " + ", ".join(name.lower() for name in missing))
            if reply == "REFUSE":
                loop.call_soon(self.ref[0].on_refused, my_id)
            elif reply is not None:
                self._emit_text(reply)
        elif text == "Y":
            reply = self._script("y", "ACK")
            if reply == "ACK":
                loop.call_soon(self.ref[0].on_ack, my_id)
            elif reply == "ACK_COMMAND":  # the live run: ✅ on the $oic command message
                loop.call_soon(self.ref[0].on_ack, self.oic_id)
            elif reply is not None:
                self._emit_text(reply)
        return NS(id=my_id)

    async def click(self, button):
        self.clicks += 1
        self.current += 1
        loop = asyncio.get_running_loop()
        loop.call_soon(self.ref[0].on_edit, self._list(self.current))
        return True


class MathTests(unittest.TestCase):
    def test_count(self):
        self.assertEqual(upgrade_count(1999, 2000), 0)
        self.assertEqual(upgrade_count(2000, 2000), 2)
        self.assertEqual(upgrade_count(2999, 2000), 2)
        self.assertEqual(upgrade_count(10000, 2000), 10)
        self.assertEqual(upgrade_count(None, 2000), 0)
        self.assertEqual(upgrade_count(250000, 2000, 100), 100)
        self.assertEqual(upgrade_count(250000, 2000, 0), 250)
        self.assertEqual(upgrade_count(10000, 2000, 100, names_available=4), 4)

    def test_settings(self):
        settings = Perk10Settings.from_preset({})
        self.assertEqual((settings.enabled, settings.min_spheres, settings.max_characters, settings.daily_cap),
                         (False, 2000, 100, 3))
        self.assertEqual(PERK10_DEFAULTS["perk10_min_spheres"], 2000)
        self.assertEqual(Perk10Settings.from_preset({"perk10_min_spheres": "5,000", "perk10_max_characters": 0}).min_spheres, 5000)
        self.assertEqual(Perk10Settings.from_preset({"perk10_min_spheres": 10}).min_spheres, 2000)
        self.assertEqual(validate_perk10_settings({}), [])
        self.assertEqual(len(validate_perk10_settings({"perk10_min_spheres": 999, "perk10_daily_cap": 0,
                                                       "perk10_max_characters": -1})), 3)

    def test_games_gate(self):
        enabled = {"oh": True, "oc": True, "oq": False, "ot": False}
        self.assertIsNone(sphere_games_pending({"oh": 0, "oc": 0, "oq": 3}, enabled))
        self.assertIn("$oc 1", sphere_games_pending({"oh": 0, "oc": 1}, enabled))
        self.assertIn("being played", sphere_games_pending({}, enabled, running=True))
        self.assertIn("not known", sphere_games_pending({}, enabled, status_seen=False))
        self.assertIsNone(sphere_games_pending({}, {}, status_seen=False))

    def test_parsers(self):
        q = parse_oic_question("Do you really want to spend 10,000 <:spR:1> for 10 characters? (y/n/yes/no)")
        self.assertEqual((q.cost, q.count), (10000, 10))
        q = parse_oic_question("Do you really want to spend **2,000** :spR: for **2** characters? (y/n/yes/no)")
        self.assertEqual((q.cost, q.count), (2000, 2))
        self.assertIsNone(parse_oic_question("Do you really want to spend 1,000 for 1 characters?"))
        self.assertEqual(parse_not_found("Perks upgraded:\nCharacters not found: satanichia mcdowell, kurumizawa"),
                         ("satanichia mcdowell", "kurumizawa"))
        self.assertEqual(normalize_name("  Rin  Tōsaka "), "rin tosaka")

    def test_build_commands_split(self):
        names = ["Name Number {:03d} With Some Length".format(index) for index in range(120)]
        commands = build_commands(names, "$")
        self.assertGreater(len(commands), 1)
        joined = []
        for command, chunk in commands:
            self.assertLess(len(command), COMMAND_LENGTH_LIMIT)
            self.assertTrue(command.startswith("$oic "))
            self.assertTrue(command.endswith(" $ 10"))
            joined.extend(chunk)
        self.assertEqual(joined, names)
        self.assertEqual(build_commands(["A", "B"], "!")[0][0], "!oic A $ B $ 10")


class EmptyNameGuardTests(unittest.TestCase):
    def test_empty_or_invisible_names_never_make_a_command(self):
        for bad in ([""], [" "], ["\u200b"], ["\u2800"], ["A", "\u200e"], ["A", ""]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                build_commands(bad, "$")
        with self.assertRaises(ValueError):
            command_for([], "$")
        self.assertEqual(build_commands([], "$"), [])

    def test_one_name_uses_oi_two_or_more_oic(self):
        self.assertEqual(build_commands(["Sonia Nevermind"])[0][0], "$oi Sonia Nevermind $ 10")
        self.assertEqual(build_commands(["A", "B"])[0][0], "$oic A $ B $ 10")
        self.assertEqual(build_commands(["A"], "!")[0][0], "!oi A $ 10")
        names = ["Name Number {:03d} With Some Length".format(index) for index in range(61)]
        commands = build_commands(names)
        self.assertTrue(commands[-1][0].startswith("$oi ") or commands[-1][0].startswith("$oic "))
        for command, chunk in commands:
            self.assertEqual(command.startswith("$oi "), len(chunk) == 1)

    def test_single_question_variants(self):
        ok = [
            "Do you really want to spend 1,000 <:spR:1> for 1 characters? (y/n/yes/no)",
            "Do you really want to spend **1,000** <:spR:1> for **1** character? (y/n/yes/no)",
            "TestUser, do you really want to spend 1,000 <:spR:1>? (y/n/yes/no)",
            "Do you really want to spend 1,000 <:spR:1> on **Sonia Nevermind**? (y/n/yes/no)",
        ]
        for text in ok:
            q = parse_oi_question(text, "Sonia Nevermind", ("TestUser",))
            self.assertEqual((q.cost, q.count), (1000, 1), text)
        bad = [
            "Do you really want to spend 2,000 <:spR:1> for 2 characters? (y/n/yes/no)",
            "Do you really want to spend 1,000 <:spR:1> on **Claire Redfield**? (y/n/yes/no)",
            "Do you really want to spend 1,000 <:spR:1> for 3 characters? (y/n/yes/no)",
            "Do you really want to buy something? (y/n/yes/no)",
            "Do you really want to spend 1,000 <:spR:1> for 1 characters?",
        ]
        for text in bad:
            self.assertIsNone(parse_oi_question(text, "Sonia Nevermind", ("TestUser",)), text)


class FlowBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.logs = []
        self.now = [WHEN]
        self.clock = [0.0]
        self.counter = 0

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, pages=None, store=None, **kwargs):
        ref = [None]
        fake = FakeMudae(ref, pages, **kwargs)
        self.counter += 1
        store = store or AccountStateStore(os.path.join(self.tmp.name, "state{}.json".format(self.counter)))

        async def wait(seconds):
            return True

        upgrader = PerkUpgrader(key="ptest#1", store=store, send=fake.send, click=fake.click, wait=wait,
                                log=lambda message, level: self.logs.append((level, message)),
                                clock=lambda: self.now[0], question_timeout=0.3, ack_timeout=0.3,
                                followup_timeout=0.2, answer_delay=(0, 0), between_commands=(0, 0))
        upgrader.reader.reply_timeout = 0.3
        upgrader.reader.edit_timeout = 0.3
        upgrader.reader.click_delay = (0, 0)
        upgrader.reader.retry_delay = (0, 0)
        ref[0] = upgrader
        return upgrader, fake

    def totals(self, spheres):
        totals = AccountTotals("TestUser", clock=lambda: self.now[0])
        if spheres is not None:
            totals.set_total(SPHERES, spheres, "$tu")
        return totals

    def run_upgrade(self, upgrader, totals, settings=None, **overrides):
        options = dict(own_id=OWN_ID, own_names=("TestUser",), totals=totals)
        options.update(overrides)
        settings = settings or Perk10Settings(enabled=True)
        return asyncio.run(upgrader.maybe_upgrade(CHANNEL, settings, **options))


class FlowTests(FlowBase):
    def test_happy_path_ten(self):
        upgrader, fake = self.make()
        totals = self.totals(10000)
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "upgraded", outcome.reason)
        self.assertEqual(outcome.characters, 10)
        self.assertEqual(outcome.cost, 10000)
        self.assertEqual(fake.sent[0], "$mmz-")
        self.assertEqual(fake.sent[1], "$oic " + " $ ".join(page_names(1)[:10]) + " $ 10")
        self.assertEqual(fake.sent[2], "Y")
        self.assertEqual(fake.clicks, 0)  # page 1 held enough names
        self.assertEqual(totals.spheres, 0)
        self.assertEqual(upgrader.upgrades_today(), 1)
        self.assertTrue(any(level == "SUCCESS" and "upgraded 10 character(s) for 10,000 spheres" in message
                            for level, message in self.logs))

    def test_check_reaction_on_the_command_counts(self):
        upgrader, fake = self.make(script={"y": "ACK_COMMAND"})
        totals = self.totals(10000)
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "upgraded", outcome.reason)
        self.assertEqual(totals.spheres, 0)

    def test_owner_page_with_an_invisible_first_line_never_sends_an_empty_name(self):
        # The 16:41 run on 6.0.1 sent «$oic  $ 10». A line that prints as nothing (zero-width space,
        # Braille blank) in the description must be skipped; the first real name goes out, with $oi.
        names = ["Sonia Nevermind", "Claire Redfield", "Kitasan Black"]
        pages = [["\u200b", "\u2800 ", " "] + names]
        upgrader, fake = self.make(pages=pages)
        totals = self.totals(1225)
        settings = Perk10Settings(enabled=True, min_spheres=1000)  # a minimum at or under his stock: allowed by setting
        outcome = self.run_upgrade(upgrader, totals, settings)
        self.assertEqual(outcome.status, "upgraded", outcome.reason)
        commands = [text for text in fake.sent if text.startswith("$oi")]
        self.assertEqual(commands, ["$oi Sonia Nevermind $ 10"])
        for text in fake.sent:
            self.assertNotIn("$oic  $", text)
            self.assertNotIn("$oi  $", text)

    def test_page_of_only_invisible_lines_sends_nothing(self):
        upgrader, fake = self.make(pages=[["\u200b", "\u2800"]])
        outcome = self.run_upgrade(upgrader, self.totals(5000))
        self.assertEqual(outcome.status, "empty")
        self.assertEqual([t for t in fake.sent if t.startswith("$oi")], [])

    def test_stock_1225_with_default_minimum_sends_nothing(self):
        upgrader, fake = self.make()
        outcome = self.run_upgrade(upgrader, self.totals(1225))
        self.assertEqual(outcome.status, "skipped")
        self.assertEqual(fake.sent, [])

    def test_tu_layout_of_the_owner_gives_the_sphere_stock(self):
        from mudae_core.totals import parse_tu_totals
        raw = ("Tester, you can't claim for another **48** min.\nStock: **159,247** <:kakera:1>\n\n"
               "**0** $oh left for today, **0** $oc, **0** $oq and **0** $ot (+**1** stored).\n"
               "**14h 42** min before the refill. **4/12** buttons clicked.\nStock: **1,225** <:spR:2>\n")
        self.assertEqual(parse_tu_totals(raw).spheres, 1225)

    def test_no_character_found_is_a_refusal_never_answered(self):
        upgrader, fake = self.make(script={"oic": "No character found!\nSyntax: $oi <character> $ <perk(s) number to upgrade>"})
        outcome = self.run_upgrade(upgrader, self.totals(1000), Perk10Settings(enabled=True, min_spheres=1000))
        self.assertEqual(outcome.status, "stopped")
        self.assertNotIn("Y", fake.sent)
        self.assertNotIn("n", fake.sent)
        self.assertTrue(any("No character found" in message for _level, message in self.logs))
        self.assertIsNotNone(upgrader._retry_at)

    def test_single_character_uses_oi_and_the_same_flow(self):
        upgrader, fake = self.make()
        totals = self.totals(1000)
        outcome = self.run_upgrade(upgrader, totals, Perk10Settings(enabled=True, min_spheres=1000))
        self.assertEqual(outcome.status, "upgraded", outcome.reason)
        self.assertEqual(fake.sent[1], "$oi " + page_names(1)[0] + " $ 10")
        self.assertEqual(fake.sent[2], "Y")
        self.assertEqual(totals.spheres, 0)

    def test_unrecognised_single_question_is_answered_n_and_logged_as_error(self):
        weird = "Do you really want to spend 1,500 <:spR:1> for this? (y/n/yes/no)"
        upgrader, fake = self.make(script={"oic": weird})
        outcome = self.run_upgrade(upgrader, self.totals(1000), Perk10Settings(enabled=True, min_spheres=1000))
        self.assertEqual(outcome.status, "stopped")
        self.assertNotIn("Y", fake.sent)
        self.assertEqual(fake.sent[-1], "n")
        self.assertTrue(any(level == "ERROR" and "1,500" in message for level, message in self.logs))

    def test_below_minimum_and_disabled(self):
        upgrader, fake = self.make()
        outcome = self.run_upgrade(upgrader, self.totals(1999))
        self.assertEqual(outcome.status, "skipped")
        self.assertIn("below", outcome.reason)
        outcome = self.run_upgrade(upgrader, self.totals(5000), settings=Perk10Settings(enabled=False))
        self.assertEqual(outcome.reason, "off")
        self.assertEqual(fake.sent, [])

    def test_unknown_stock_waits_without_tu(self):
        upgrader, fake = self.make()
        outcome = self.run_upgrade(upgrader, self.totals(None))
        self.assertEqual(outcome.status, "skipped")
        self.assertIn("unknown", outcome.reason)
        self.assertEqual(fake.sent, [])  # never a $tu (or anything else)

    def test_games_first_and_busy(self):
        upgrader, fake = self.make()
        outcome = self.run_upgrade(upgrader, self.totals(9000), games=lambda: "sphere games are still available ($oh 2)")
        self.assertIn("sphere games first", outcome.reason)
        outcome = self.run_upgrade(upgrader, self.totals(9000), busy=lambda: "rolling or claiming")
        self.assertIn("busy", outcome.reason)
        self.assertEqual(fake.sent, [])

    def test_page_turning_when_more_names_needed(self):
        upgrader, fake = self.make()
        totals = self.totals(40000)
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "upgraded", outcome.reason)
        self.assertEqual(outcome.characters, 40)
        self.assertEqual(fake.clicks, 2)  # 15 + 15 + 10 names
        sent_names = [name for command in fake.sent if command.startswith("$oic") for name in
                      command[5:].split(" $ ")[:-1]]
        self.assertEqual(sent_names, page_names(1) + page_names(2) + page_names(3)[:10])

    def test_page_flip_failure_uses_names_collected_and_never_resends_list(self):
        upgrader, fake = self.make()

        async def dead_click(button):
            fake.clicks += 1
            return True  # the bot never edits the list

        upgrader.reader._click = dead_click
        outcome = self.run_upgrade(upgrader, self.totals(40000))
        self.assertEqual(outcome.status, "upgraded", outcome.reason)
        self.assertEqual(outcome.characters, 15)  # page 1 only
        self.assertEqual(fake.clicks, 2)  # one click and one retry, then stop
        self.assertEqual(fake.sent.count("$mmz-"), 1)
        self.assertTrue(any(level == "ERROR" and "could not turn the $mmz- page" in text for level, text in self.logs))

    def test_capped_by_names_available(self):
        upgrader, fake = self.make(pages=[page_names(1, per_page=4)])
        outcome = self.run_upgrade(upgrader, self.totals(10000))
        self.assertEqual(outcome.characters, 4)
        self.assertEqual(fake.clicks, 0)

    def test_capped_by_maximum(self):
        upgrader, fake = self.make()
        outcome = self.run_upgrade(upgrader, self.totals(10000), settings=Perk10Settings(enabled=True, max_characters=3))
        self.assertEqual(outcome.characters, 3)

    def test_long_command_split(self):
        long_pages = [["A Rather Long Made Up Character Name Number {:03d} (Variant)".format(p * 15 + i)
                       for i in range(15)] for p in range(7)]
        upgrader, fake = self.make(pages=long_pages)
        totals = self.totals(100000)
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "upgraded", outcome.reason)
        self.assertEqual(outcome.characters, 100)
        commands = [text for text in fake.sent if text.startswith("$oic")]
        self.assertGreater(len(commands), 1)
        for command in commands:
            self.assertLess(len(command), COMMAND_LENGTH_LIMIT)
            self.assertTrue(command.endswith(" $ 10"))
        # each command was answered before the next went out
        order = [text if not text.startswith("$oic") else "$oic" for text in fake.sent if text != "$mmz-"]
        self.assertEqual(order, ["$oic", "Y"] * len(commands))
        self.assertEqual(totals.spheres, 0)
        self.assertEqual(upgrader.upgrades_today(), 1)

    def test_wrong_question_answers_n(self):
        for script, words in (({"oic": question(5000, 4)}, "asked about 4"),
                              ({"oic": question(6000, 5)}, "asked 6,000"),):
            totals = self.totals(5000)
            upgrader, fake = self.make(script=script)
            outcome = self.run_upgrade(upgrader, totals)
            self.assertEqual(outcome.status, "stopped")
            self.assertIn(words, outcome.reason)
            self.assertEqual(fake.sent[-1], "n")
            self.assertNotIn("Y", fake.sent)
            self.assertEqual(totals.spheres, 5000)

    def test_cost_above_stock_answers_n(self):
        upgrader, fake = self.make()
        totals = self.totals(5000)

        async def send(channel, text):
            receipt = await fake.send(channel, text)
            if text.startswith("$oic"):
                totals.set_total(SPHERES, 3000, "game result")  # stock fell meanwhile
            return receipt

        upgrader._send = send
        upgrader.reader._send = send
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "stopped")
        self.assertIn("above the known stock", outcome.reason)
        self.assertEqual(fake.sent[-1], "n")

    def test_not_found_remembered_and_skipped(self):
        bad = page_names(1)[1]
        upgrader, fake = self.make(unknown=[bad])
        totals = self.totals(3000)
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "upgraded", outcome.reason)
        self.assertEqual(outcome.characters, 2)
        self.assertEqual(outcome.cost, 2000)
        self.assertNotIn(bad, outcome.names)
        self.assertEqual(totals.spheres, 1000)
        self.assertIn(normalize_name(bad), upgrader.not_found_names())
        # next time the bad name is skipped (memory persisted in the store)
        again, fake2 = self.make(store=upgrader.store, unknown=[bad])
        totals.set_total(SPHERES, 3000, "$tu")
        outcome = self.run_upgrade(again, totals)
        self.assertEqual(outcome.characters, 3)
        self.assertNotIn(bad, fake2.sent[1])

    def test_all_not_found_without_question(self):
        names = page_names(1, per_page=2)
        upgrader, fake = self.make(pages=[names], unknown=names)
        totals = self.totals(2000)
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "stopped")
        self.assertIn("none of the names were found", outcome.reason)
        self.assertNotIn("Y", fake.sent)
        self.assertEqual(set(upgrader.not_found_names()), {normalize_name(name) for name in names})
        self.assertEqual(totals.spheres, 2000)

    def test_timeouts(self):
        upgrader, fake = self.make(script={"oic": None})
        totals = self.totals(2000)
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "stopped")
        self.assertIn("did not ask", outcome.reason)
        self.assertNotIn("Y", fake.sent)
        self.assertEqual(upgrader.upgrades_today(), 0)
        upgrader, fake = self.make(script={"y": None})
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "stopped")
        self.assertIn("no ✅", outcome.reason)
        self.assertIsNone(totals.spheres)  # may have happened: unknown until the next $tu
        self.assertEqual(upgrader.upgrades_today(), 1)

    def test_refused_and_backoff(self):
        upgrader, fake = self.make(script={"oic": "REFUSE"})
        totals = self.totals(2000)
        outcome = self.run_upgrade(upgrader, totals)
        self.assertIn("⛔", outcome.reason)
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "skipped")
        self.assertIn("backing off", outcome.reason)

    def test_daily_cap(self):
        upgrader, fake = self.make()
        totals = self.totals(2000)
        for _ in range(3):
            totals.set_total(SPHERES, 2000, "$tu")
            self.assertEqual(self.run_upgrade(upgrader, totals).status, "upgraded")
        totals.set_total(SPHERES, 2000, "$tu")
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "skipped")
        self.assertIn("daily limit", outcome.reason)
        self.now[0] = WHEN + datetime.timedelta(days=1)
        self.assertEqual(self.run_upgrade(upgrader, totals).status, "upgraded")

    def test_empty_list_checked_once_per_six_hours(self):
        upgrader, fake = self.make(pages=[[]])
        totals = self.totals(5000)
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "empty")
        self.assertEqual(sum(1 for level, message in self.logs if "checked again in 6 hours" in message), 1)
        self.now[0] = WHEN + datetime.timedelta(hours=5)
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "skipped")
        self.assertIn("listed nothing", outcome.reason)
        self.assertEqual(fake.sent, ["$mmz-"])
        self.now[0] = WHEN + datetime.timedelta(hours=6, minutes=1)
        self.run_upgrade(upgrader, totals)
        self.assertEqual(fake.sent, ["$mmz-", "$mmz-"])

    def test_foreign_list_and_foreign_question_ignored(self):
        upgrader, fake = self.make(owner="SomeoneElse")
        outcome = self.run_upgrade(upgrader, self.totals(2000))
        self.assertEqual(outcome.status, "stopped")
        self.assertNotIn("Y", fake.sent)
        # a question replying to another user's message is not ours
        upgrader, fake = self.make(script={"oic": None})
        totals = self.totals(2000)

        async def send(channel, text):
            receipt = await fake.send(channel, text)
            if text.startswith("$oic"):
                fake._emit_text(question(2000, 2), reference=1)
            return receipt

        upgrader._send = send
        upgrader.reader._send = send
        outcome = self.run_upgrade(upgrader, totals)
        self.assertEqual(outcome.status, "stopped")
        self.assertNotIn("Y", fake.sent)

    def test_busy_between_commands_stops_after_first(self):
        long_pages = [["A Rather Long Made Up Character Name Number {:03d} (Variant)".format(p * 15 + i)
                       for i in range(15)] for p in range(7)]
        upgrader, fake = self.make(pages=long_pages)
        totals = self.totals(100000)
        state = {"calls": 0}

        def busy():
            state["calls"] += 1
            return "rolling or claiming" if state["calls"] > 2 else None

        outcome = self.run_upgrade(upgrader, totals, busy=busy)
        self.assertEqual(outcome.status, "upgraded")
        self.assertIn("stopped early", outcome.reason)
        self.assertEqual(len([text for text in fake.sent if text.startswith("$oic")]), 1)


class AmountTests(unittest.TestCase):
    def test_amount_zero_is_unchanged(self):
        self.assertEqual(upgrade_count(10000, 2000, 100, amount=0), 10)
        self.assertEqual(upgrade_count(250000, 2000, 100, amount=0), 100)

    def test_amount_three_at_each_stock(self):
        self.assertEqual(upgrade_count(2000, 2000, 100, amount=3), 2)   # affordable only
        self.assertEqual(upgrade_count(2300, 2000, 100, amount=3), 2)
        self.assertEqual(upgrade_count(5000, 2000, 100, amount=3), 3)
        self.assertEqual(upgrade_count(10000, 2000, 100, amount=3), 3)
        self.assertEqual(upgrade_count(1999, 2000, 100, amount=3), 0)   # below the minimum: nothing

    def test_amount_above_affordable_and_with_maximum(self):
        self.assertEqual(upgrade_count(2300, 2000, 0, amount=5), 2)     # never waits, never overspends
        self.assertEqual(upgrade_count(10000, 2000, 2, amount=5), 2)    # the maximum still caps
        self.assertEqual(upgrade_count(10000, 2000, 0, amount=5), 5)
        self.assertEqual(upgrade_count(10000, 2000, 100, amount=5, names_available=1), 1)

    def test_settings_and_validation(self):
        self.assertEqual(Perk10Settings.from_preset({}).amount, 0)
        self.assertEqual(Perk10Settings.from_preset({"perk10_amount": "7"}).amount, 7)
        self.assertEqual(Perk10Settings.from_preset({"perk10_amount": -1}).amount, 0)
        self.assertEqual(validate_perk10_settings({"perk10_amount": 0}), [])
        self.assertEqual(len(validate_perk10_settings({"perk10_amount": -2})), 1)
        self.assertEqual(len(validate_perk10_settings({"perk10_amount": "x"})), 1)


class AmountFlowTests(FlowBase):
    def test_amount_three_with_stock_5000_sends_three_names(self):
        upgrader, fake = self.make()
        totals = self.totals(5000)
        outcome = self.run_upgrade(upgrader, totals, Perk10Settings(enabled=True, amount=3))
        self.assertEqual((outcome.status, outcome.characters, outcome.cost), ("upgraded", 3, 3000))
        self.assertEqual(fake.sent[1], "$oic " + " $ ".join(page_names(1)[:3]) + " $ 10")
        self.assertEqual(totals.spheres, 2000)

    def test_amount_five_with_stock_2300_upgrades_two(self):
        upgrader, fake = self.make()
        totals = self.totals(2300)
        outcome = self.run_upgrade(upgrader, totals, Perk10Settings(enabled=True, amount=5))
        self.assertEqual((outcome.characters, outcome.cost), (2, 2000))
        self.assertEqual(totals.spheres, 300)


class UpgradeNowTests(FlowBase):
    def run_now(self, upgrader, totals, settings=None, **overrides):
        options = dict(own_id=OWN_ID, own_names=("TestUser",), totals=totals, poll_seconds=0.01,
                       total_wait_seconds=0.2, busy_wait_seconds=0.2)
        options.update(overrides)
        return asyncio.run(upgrader.upgrade_now(CHANNEL, settings or Perk10Settings(enabled=False), **options))

    def test_happy_path_with_switch_off_ignores_minimum_and_daily_cap(self):
        upgrader, fake = self.make()
        upgrader.store.put(upgrader.key, "perk10_upgrades", {"day": WHEN.date().isoformat(), "count": 99})
        totals = self.totals(1500)  # below the 2,000 minimum, daily cap long reached
        outcome = self.run_now(upgrader, totals, Perk10Settings(enabled=False, min_spheres=2000, daily_cap=1))
        self.assertEqual((outcome.status, outcome.characters, outcome.cost), ("upgraded", 1, 1000))
        self.assertEqual(fake.sent[0], "$mmz-")
        self.assertEqual(totals.spheres, 500)
        self.assertTrue(any("Perk 10: upgraded 1 character(s)" in text for _l, text in self.logs))

    def test_uses_amount_and_maximum(self):
        upgrader, fake = self.make()
        outcome = self.run_now(upgrader, self.totals(10000), Perk10Settings(amount=4, max_characters=3))
        self.assertEqual(outcome.characters, 3)

    def test_below_1000_does_nothing(self):
        upgrader, fake = self.make()
        outcome = self.run_now(upgrader, self.totals(999))
        self.assertEqual(outcome.status, "skipped")
        self.assertEqual(fake.sent, [])
        self.assertIn("needs at least 1,000", upgrader.status)

    def test_unknown_stock_waits_then_arriving_tu_lets_it_run(self):
        upgrader, fake = self.make()
        totals = self.totals(None)
        calls = []

        async def wait(seconds):
            calls.append(seconds)
            if len(calls) == 3:
                totals.set_total(SPHERES, 3000, "$tu")  # the next $tu the program sends
            await asyncio.sleep(0)
            return True

        upgrader._wait = wait
        upgrader.reader._wait = wait
        outcome = self.run_now(upgrader, totals, total_wait_seconds=60)
        self.assertEqual((outcome.status, outcome.characters), ("upgraded", 3))
        self.assertNotIn("$tu", fake.sent)

    def test_unknown_stock_gives_up_without_sending(self):
        upgrader, fake = self.make()

        async def wait(seconds):
            await asyncio.sleep(0.02)
            return True

        upgrader._wait = wait
        outcome = self.run_now(upgrader, self.totals(None), total_wait_seconds=0.05)
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(fake.sent, [])

    def test_games_and_busy_work_are_waited_for(self):
        upgrader, fake = self.make()
        state = {"calls": 0}

        def games():
            state["calls"] += 1
            return "sphere games are still available ($oh 1)" if state["calls"] < 3 else None

        outcome = self.run_now(upgrader, self.totals(3000), games=games, busy_wait_seconds=5)
        self.assertEqual(outcome.status, "upgraded")
        self.assertGreaterEqual(state["calls"], 3)
        always = self.run_now(self.make()[0], self.totals(3000), busy=lambda: "rolling or claiming")
        self.assertEqual(always.status, "stopped")
        self.assertIn("still busy", always.reason)

    def test_cooldown_and_one_at_a_time(self):
        upgrader, fake = self.make()
        totals = self.totals(5000)
        first = self.run_now(upgrader, totals)
        self.assertEqual(first.status, "upgraded")
        second = self.run_now(upgrader, totals)
        self.assertEqual(second.status, "ignored")
        self.assertIn("too soon", second.reason)
        upgrader._manual_pressed_at -= 61
        upgrader._manual_in_flight = True
        self.assertEqual(self.run_now(upgrader, totals).status, "ignored")

    def test_alt_without_side_perk10_is_refused_with_reason(self):
        upgrader, fake = self.make()
        outcome = self.run_now(upgrader, self.totals(5000),
                               allowed_reason="this alt does not upgrade perk 10 (turn on «Let side accounts upgrade too»)")
        self.assertEqual(outcome.status, "skipped")
        self.assertEqual(fake.sent, [])
        self.assertIn("Let side accounts upgrade too", upgrader.status)
        self.assertTrue(any("not run" in text for _l, text in self.logs))

    def test_failed_upgrade_is_logged_like_the_automatic_path(self):
        upgrader, fake = self.make(script={"y": None})
        outcome = self.run_now(upgrader, self.totals(5000))
        self.assertEqual(outcome.status, "stopped")
        self.assertIn("Perk 10 stopped", upgrader.status)

    def test_account_role_rule_for_the_button(self):
        from mudae_core.account_roles import ROLE_SIDE, perk10_enabled
        self.assertTrue(perk10_enabled("main", None, True, False))
        self.assertFalse(perk10_enabled(ROLE_SIDE, "alt", True, False))
        self.assertTrue(perk10_enabled(ROLE_SIDE, "alt", True, True))


class ActivityEventTests(unittest.TestCase):
    def test_log_lines_become_events(self):
        from mudae_core.activity_events import ActivityClassifier
        classify = ActivityClassifier().classify
        events = classify("SUCCESS", "Perk 10: upgraded 10 character(s) for 10,000 spheres (1 today): A, B.")
        self.assertEqual(events[0][0], "perk10_upgrade")
        self.assertEqual(events[0][1]["characters"], 10)
        self.assertEqual(classify("WARN", "Perk 10 stopped: no ✅ on the Y in time. Next try in 10 min.")[0][0],
                         "perk10_stopped")


if __name__ == "__main__":
    unittest.main()
