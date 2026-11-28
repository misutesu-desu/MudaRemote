"""Automatic perk-10 upgrade: $mmz- names → $oic … $ 10 → Y (a fake game bot; made-up names and ids)."""
import asyncio
import datetime
import unittest
from types import SimpleNamespace as NS

from mudae_core.config import validate_preset
from mudae_core.perk_upgrade import (
    COMMAND_LENGTH_LIMIT, PERK10_DEFAULTS, Perk10Settings, PerkUpgrader, build_commands, command_for, normalize_name,
    parse_not_found, parse_oi_question, parse_oic_question, sphere_games_pending, upgrade_count,
    validate_perk10_settings,
)
from mudae_core.sphere_stock import SphereStock
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
        self.oic_id = None

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
            parts = [part.strip() for part in text.split(" ", 1)[1].split("$")]
            assert parts[-1] == "10", text
            names = parts[:-1]
            missing = [name for name in names if name.casefold() in self.unknown]
            count = len(names) - len(missing)
            reply = self._script("oic", question(count * 1000, count, missing) if count else
                                 "Characters not found: " + ", ".join(name.lower() for name in missing))
            if reply == "REFUSE":
                loop.call_soon(self.ref[0].on_refused, my_id)
            elif reply is not None:
                self._emit_text(reply)
        elif text == "Y":
            reply = self._script("y", "ACK_COMMAND")
            if reply == "ACK":  # ✅ on the Y
                loop.call_soon(self.ref[0].on_ack, my_id)
            elif reply == "ACK_COMMAND":  # the live run: ✅ on the $oic command message
                loop.call_soon(self.ref[0].on_ack, self.oic_id)
            elif reply is not None:
                self._emit_text(reply)
        return NS(id=my_id)

    async def click(self, button):
        self.clicks += 1
        self.current += 1
        asyncio.get_running_loop().call_soon(self.ref[0].on_edit, self._list(self.current))
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

    def test_amount(self):
        self.assertEqual(upgrade_count(10000, 2000, 100, amount=0), 10)
        self.assertEqual(upgrade_count(2000, 2000, 100, amount=3), 2)  # only what the stock affords
        self.assertEqual(upgrade_count(5000, 2000, 100, amount=3), 3)
        self.assertEqual(upgrade_count(1999, 2000, 100, amount=3), 0)  # below the minimum: nothing
        self.assertEqual(upgrade_count(2300, 2000, 0, amount=5), 2)  # never waits, never overspends
        self.assertEqual(upgrade_count(10000, 2000, 2, amount=5), 2)  # the maximum still caps

    def test_settings(self):
        settings = Perk10Settings.from_preset({})
        self.assertEqual((settings.enabled, settings.min_spheres, settings.max_characters, settings.amount,
                          settings.daily_cap), (False, 2000, 100, 0, 3))
        self.assertEqual(PERK10_DEFAULTS["perk10_min_spheres"], 2000)
        self.assertEqual(Perk10Settings.from_preset({"perk10_min_spheres": "5,000"}).min_spheres, 5000)
        self.assertEqual(Perk10Settings.from_preset({"perk10_min_spheres": 10}).min_spheres, 2000)
        self.assertEqual(Perk10Settings.from_preset({"perk10_amount": "7"}).amount, 7)
        self.assertEqual(validate_perk10_settings({}), [])
        self.assertEqual(len(validate_perk10_settings({"perk10_min_spheres": 999, "perk10_daily_cap": 0,
                                                       "perk10_max_characters": -1, "perk10_amount": "x"})), 4)

    def test_preset_validation_includes_perk10(self):
        base = {"token": "made-up", "prefix": "!", "mudae_prefix": "$", "roll_command": "wa", "channel_id": "1",
                "claim_interval": 180, "roll_interval": 60, "max_dk_power": 100}
        self.assertEqual(validate_preset(base), [])
        self.assertTrue(any("perk10_daily_cap" in error for error in validate_preset(dict(base, perk10_daily_cap=0))))

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
        self.assertIsNone(parse_oic_question("Do you really want to spend 2,000 <:kakera:1> for 2 characters? (y/n)"))
        self.assertEqual(parse_not_found("Perks upgraded:\nCharacters not found: made up one, made up two"),
                         ("made up one", "made up two"))
        self.assertEqual(normalize_name("  Rin  Tōsaka "), "rin tosaka")


class CommandTests(unittest.TestCase):
    def test_build_commands_split(self):
        names = ["Name Number {:03d} With Some Length".format(index) for index in range(120)]
        commands = build_commands(names, "$")
        self.assertGreater(len(commands), 1)
        joined = []
        for command, chunk in commands:
            self.assertLess(len(command), COMMAND_LENGTH_LIMIT)
            self.assertTrue(command.endswith(" $ 10"))
            self.assertEqual(command.startswith("$oi "), len(chunk) == 1)
            joined.extend(chunk)
        self.assertEqual(joined, names)
        self.assertEqual(build_commands(["A", "B"], "!")[0][0], "!oic A $ B $ 10")

    def test_one_name_uses_oi(self):
        self.assertEqual(build_commands(["Made Up Name"])[0][0], "$oi Made Up Name $ 10")
        self.assertEqual(build_commands(["A"], "!")[0][0], "!oi A $ 10")

    def test_empty_or_invisible_names_never_make_a_command(self):
        for bad in ([""], [" "], ["​"], ["⠀"], ["A", "‎"], ["A", ""], ["A $ B"]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                build_commands(bad, "$")
        with self.assertRaises(ValueError):
            command_for([], "$")
        self.assertEqual(build_commands([], "$"), [])

    def test_single_question_variants(self):
        ok = [
            "Do you really want to spend 1,000 <:spR:1> for 1 characters? (y/n/yes/no)",
            "Do you really want to spend **1,000** <:spR:1> for **1** character? (y/n/yes/no)",
            "TestUser, do you really want to spend 1,000 <:spR:1>? (y/n/yes/no)",
            "Do you really want to spend 1,000 <:spR:1> on **Made Up Name**? (y/n/yes/no)",
            "Do you really want to spend **1,000** <:spR:1> for **Made Up Name**? (y/n/yes/no)\nPerks upgraded:\n\n"
            "[10] The first $oh of the day generates **+20** spheres and has **+1%** chance to give 1 $oq",
        ]
        for text in ok:
            q = parse_oi_question(text, "Made Up Name", ("TestUser",))
            self.assertEqual((q.cost, q.count), (1000, 1), text)
        bad = [
            "Do you really want to spend 2,000 <:spR:1> for 2 characters? (y/n/yes/no)",
            "Do you really want to spend 1,000 <:spR:1> on **Another Made Up Name**? (y/n/yes/no)",
            "Do you really want to buy something? (y/n/yes/no)",
            "Do you really want to spend 1,000 <:spR:1> for 1 characters?",
        ]
        for text in bad:
            self.assertIsNone(parse_oi_question(text, "Made Up Name", ("TestUser",)), text)


class FlowBase(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.now = [WHEN]

    def make(self, pages=None, **kwargs):
        ref = [None]
        fake = FakeMudae(ref, pages, **kwargs)

        async def wait(seconds):
            return True

        upgrader = PerkUpgrader(send=fake.send, click=fake.click, wait=wait,
                                log=lambda message, level: self.logs.append((level, message)),
                                clock=lambda: self.now[0], question_timeout=0.3, ack_timeout=0.3,
                                followup_timeout=0.2, answer_delay=(0, 0), between_commands=(0, 0))
        upgrader.reader.reply_timeout = 0.3
        upgrader.reader.edit_timeout = 0.3
        upgrader.reader.click_delay = (0, 0)
        upgrader.reader.retry_delay = (0, 0)
        ref[0] = upgrader
        return upgrader, fake

    def stock(self, spheres):
        stock = SphereStock()
        stock.set(spheres)
        return stock

    def run_upgrade(self, upgrader, stock, settings=None, **overrides):
        options = dict(own_id=OWN_ID, own_names=("TestUser",), stock=stock)
        options.update(overrides)
        return asyncio.run(upgrader.maybe_upgrade(CHANNEL, settings or Perk10Settings(enabled=True), **options))

    def oi_commands(self, fake):
        return [text for text in fake.sent if text.startswith("$oi")]


class FlowTests(FlowBase):
    def test_happy_path_ten(self):
        upgrader, fake = self.make()
        stock = self.stock(10000)
        outcome = self.run_upgrade(upgrader, stock)
        self.assertEqual(outcome.status, "upgraded", outcome.reason)
        self.assertEqual((outcome.characters, outcome.cost), (10, 10000))
        self.assertEqual(fake.sent, ["$mmz-", "$oic " + " $ ".join(page_names(1)[:10]) + " $ 10", "Y"])
        self.assertEqual(fake.clicks, 0)  # page 1 held enough names
        self.assertEqual(stock.spheres, 0)
        self.assertEqual(upgrader.upgrades_today(), 1)
        self.assertTrue(any("upgraded 10 character(s) for 10,000 spheres" in message for _level, message in self.logs))

    def test_check_reaction_on_the_y_counts_too(self):
        upgrader, fake = self.make(script={"y": "ACK"})
        outcome = self.run_upgrade(upgrader, self.stock(10000))
        self.assertEqual(outcome.status, "upgraded", outcome.reason)

    def test_single_character_uses_oi(self):
        upgrader, fake = self.make()
        stock = self.stock(1000)
        outcome = self.run_upgrade(upgrader, stock, Perk10Settings(enabled=True, min_spheres=1000))
        self.assertEqual(outcome.status, "upgraded", outcome.reason)
        self.assertEqual(fake.sent[1:], ["$oi " + page_names(1)[0] + " $ 10", "Y"])
        self.assertEqual(stock.spheres, 0)

    def test_invisible_lines_never_make_an_empty_name(self):
        pages = [["​", "⠀ ", " ", "Made Up Name", "Second Made Up Name"]]
        upgrader, fake = self.make(pages=pages)
        outcome = self.run_upgrade(upgrader, self.stock(1225), Perk10Settings(enabled=True, min_spheres=1000))
        self.assertEqual(outcome.status, "upgraded", outcome.reason)
        self.assertEqual(self.oi_commands(fake), ["$oi Made Up Name $ 10"])

    def test_page_of_only_invisible_lines_sends_nothing(self):
        upgrader, fake = self.make(pages=[["​", "⠀"]])
        outcome = self.run_upgrade(upgrader, self.stock(5000))
        self.assertEqual(outcome.status, "empty")
        self.assertEqual(self.oi_commands(fake), [])

    def test_no_character_found_is_a_refusal_never_answered(self):
        upgrader, fake = self.make(script={"oic": "No character found!\nSyntax: $oi <character> $ <perk(s) number to upgrade>"})
        outcome = self.run_upgrade(upgrader, self.stock(1000), Perk10Settings(enabled=True, min_spheres=1000))
        self.assertEqual(outcome.status, "stopped")
        self.assertNotIn("Y", fake.sent)
        self.assertNotIn("n", fake.sent)
        self.assertTrue(any("No character found" in message for _level, message in self.logs))

    def test_unrecognised_single_question_is_answered_n(self):
        weird = "Do you really want to spend 1,500 <:spR:1> for this? (y/n/yes/no)"
        upgrader, fake = self.make(script={"oic": weird})
        outcome = self.run_upgrade(upgrader, self.stock(1000), Perk10Settings(enabled=True, min_spheres=1000))
        self.assertEqual(outcome.status, "stopped")
        self.assertNotIn("Y", fake.sent)
        self.assertEqual(fake.sent[-1], "n")
        self.assertTrue(any(level == "ERROR" and "1,500" in message for level, message in self.logs))

    def test_below_minimum_disabled_and_unknown_stock_send_nothing(self):
        upgrader, fake = self.make()
        self.assertIn("below", self.run_upgrade(upgrader, self.stock(1999)).reason)
        self.assertIn("below", self.run_upgrade(upgrader, self.stock(1225)).reason)
        self.assertEqual(self.run_upgrade(upgrader, self.stock(5000), Perk10Settings(enabled=False)).reason, "off")
        self.assertIn("unknown", self.run_upgrade(upgrader, self.stock(None)).reason)
        self.assertEqual(fake.sent, [])  # never a $tu (or anything else)

    def test_games_first_and_busy(self):
        upgrader, fake = self.make()
        outcome = self.run_upgrade(upgrader, self.stock(9000), games=lambda: "sphere games are still available ($oh 2)")
        self.assertIn("sphere games first", outcome.reason)
        outcome = self.run_upgrade(upgrader, self.stock(9000), busy=lambda: "rolling or claiming")
        self.assertIn("busy", outcome.reason)
        self.assertEqual(fake.sent, [])

    def test_page_turning_when_more_names_needed(self):
        upgrader, fake = self.make()
        outcome = self.run_upgrade(upgrader, self.stock(40000))
        self.assertEqual((outcome.status, outcome.characters), ("upgraded", 40), outcome.reason)
        self.assertEqual(fake.clicks, 2)  # 15 + 15 + 10 names
        sent_names = [name for command in self.oi_commands(fake) for name in command[5:].split(" $ ")[:-1]]
        self.assertEqual(sent_names, page_names(1) + page_names(2) + page_names(3)[:10])
        self.assertEqual(fake.sent.count("$mmz-"), 1)

    def test_page_flip_failure_uses_names_collected(self):
        upgrader, fake = self.make()

        async def dead_click(button):
            fake.clicks += 1
            return True  # the bot never edits the list

        upgrader.reader._click = dead_click
        outcome = self.run_upgrade(upgrader, self.stock(40000))
        self.assertEqual((outcome.status, outcome.characters), ("upgraded", 15), outcome.reason)
        self.assertEqual(fake.clicks, 2)  # one click and one retry, then stop
        self.assertEqual(fake.sent.count("$mmz-"), 1)

    def test_capped_by_names_maximum_and_amount(self):
        upgrader, fake = self.make(pages=[page_names(1, per_page=4)])
        self.assertEqual(self.run_upgrade(upgrader, self.stock(10000)).characters, 4)
        upgrader, fake = self.make()
        self.assertEqual(self.run_upgrade(upgrader, self.stock(10000), Perk10Settings(enabled=True, max_characters=3)).characters, 3)
        upgrader, fake = self.make()
        stock = self.stock(5000)
        outcome = self.run_upgrade(upgrader, stock, Perk10Settings(enabled=True, amount=3))
        self.assertEqual((outcome.characters, outcome.cost, stock.spheres), (3, 3000, 2000))

    def test_long_list_split_into_commands_each_answered(self):
        long_pages = [["A Rather Long Made Up Character Name Number {:03d} (Variant)".format(p * 15 + i)
                       for i in range(15)] for p in range(7)]
        upgrader, fake = self.make(pages=long_pages)
        stock = self.stock(100000)
        outcome = self.run_upgrade(upgrader, stock)
        self.assertEqual((outcome.status, outcome.characters), ("upgraded", 100), outcome.reason)
        commands = self.oi_commands(fake)
        self.assertGreater(len(commands), 1)
        for command in commands:
            self.assertLess(len(command), COMMAND_LENGTH_LIMIT)
        order = ["$oic" if text.startswith("$oi") else text for text in fake.sent if text != "$mmz-"]
        self.assertEqual(order, ["$oic", "Y"] * len(commands))
        self.assertEqual(stock.spheres, 0)
        self.assertEqual(upgrader.upgrades_today(), 1)

    def test_wrong_question_answers_n(self):
        for script, words in (({"oic": question(5000, 4)}, "asked about 4"), ({"oic": question(6000, 5)}, "asked 6,000")):
            upgrader, fake = self.make(script=script)
            stock = self.stock(5000)
            outcome = self.run_upgrade(upgrader, stock)
            self.assertEqual(outcome.status, "stopped")
            self.assertIn(words, outcome.reason)
            self.assertEqual(fake.sent[-1], "n")
            self.assertNotIn("Y", fake.sent)
            self.assertEqual(stock.spheres, 5000)

    def test_cost_above_stock_answers_n(self):
        upgrader, fake = self.make()
        stock = self.stock(5000)

        async def send(channel, text):
            receipt = await fake.send(channel, text)
            if text.startswith("$oic"):
                stock.set(3000)  # the stock fell meanwhile
            return receipt

        upgrader._send = send
        upgrader.reader._send = send
        outcome = self.run_upgrade(upgrader, stock)
        self.assertIn("above the known stock", outcome.reason)
        self.assertEqual(fake.sent[-1], "n")

    def test_not_found_remembered_and_skipped(self):
        bad = page_names(1)[1]
        upgrader, fake = self.make(unknown=[bad])
        stock = self.stock(3000)
        outcome = self.run_upgrade(upgrader, stock)
        self.assertEqual((outcome.status, outcome.characters, outcome.cost), ("upgraded", 2, 2000), outcome.reason)
        self.assertNotIn(bad, outcome.names)
        self.assertEqual(stock.spheres, 1000)
        self.assertIn(normalize_name(bad), upgrader.not_found_names())
        stock.set(3000)
        fake.sent.clear()
        outcome = self.run_upgrade(upgrader, stock)
        self.assertEqual(outcome.characters, 3)
        self.assertNotIn(bad, fake.sent[1])

    def test_all_not_found_without_question(self):
        names = page_names(1, per_page=2)
        upgrader, fake = self.make(pages=[names], unknown=names)
        stock = self.stock(2000)
        outcome = self.run_upgrade(upgrader, stock)
        self.assertIn("none of the names were found", outcome.reason)
        self.assertNotIn("Y", fake.sent)
        self.assertEqual(set(upgrader.not_found_names()), {normalize_name(name) for name in names})
        self.assertEqual(stock.spheres, 2000)

    def test_timeouts(self):
        upgrader, fake = self.make(script={"oic": None})
        stock = self.stock(2000)
        outcome = self.run_upgrade(upgrader, stock)
        self.assertIn("did not ask", outcome.reason)
        self.assertNotIn("Y", fake.sent)
        self.assertEqual(upgrader.upgrades_today(), 0)
        upgrader, fake = self.make(script={"y": None})
        outcome = self.run_upgrade(upgrader, stock)
        self.assertIn("no ✅", outcome.reason)
        self.assertIsNone(stock.spheres)  # may have happened: unknown until the next $tu
        self.assertEqual(upgrader.upgrades_today(), 1)

    def test_refused_and_backoff(self):
        upgrader, fake = self.make(script={"oic": "REFUSE"})
        stock = self.stock(2000)
        self.assertIn("⛔", self.run_upgrade(upgrader, stock).reason)
        outcome = self.run_upgrade(upgrader, stock)
        self.assertEqual(outcome.status, "skipped")
        self.assertIn("backing off", outcome.reason)

    def test_daily_cap(self):
        upgrader, fake = self.make()
        stock = self.stock(2000)
        for _ in range(3):
            stock.set(2000)
            self.assertEqual(self.run_upgrade(upgrader, stock).status, "upgraded")
        stock.set(2000)
        self.assertIn("daily limit", self.run_upgrade(upgrader, stock).reason)
        self.now[0] = WHEN + datetime.timedelta(days=1)
        self.assertEqual(self.run_upgrade(upgrader, stock).status, "upgraded")

    def test_empty_list_checked_once_per_six_hours(self):
        upgrader, fake = self.make(pages=[[]])
        stock = self.stock(5000)
        self.assertEqual(self.run_upgrade(upgrader, stock).status, "empty")
        self.now[0] = WHEN + datetime.timedelta(hours=5)
        outcome = self.run_upgrade(upgrader, stock)
        self.assertIn("listed nothing", outcome.reason)
        self.assertEqual(fake.sent, ["$mmz-"])
        self.now[0] = WHEN + datetime.timedelta(hours=6, minutes=1)
        self.run_upgrade(upgrader, stock)
        self.assertEqual(fake.sent, ["$mmz-", "$mmz-"])

    def test_foreign_list_and_foreign_question_ignored(self):
        upgrader, fake = self.make(owner="SomeoneElse")
        self.assertEqual(self.run_upgrade(upgrader, self.stock(2000)).status, "stopped")
        self.assertNotIn("Y", fake.sent)
        upgrader, fake = self.make(script={"oic": None})

        async def send(channel, text):
            receipt = await fake.send(channel, text)
            if text.startswith("$oic"):
                fake._emit_text(question(2000, 2), reference=1)  # replies to another user's message
            return receipt

        upgrader._send = send
        upgrader.reader._send = send
        self.assertEqual(self.run_upgrade(upgrader, self.stock(2000)).status, "stopped")
        self.assertNotIn("Y", fake.sent)

    def test_busy_between_commands_stops_after_first(self):
        long_pages = [["A Rather Long Made Up Character Name Number {:03d} (Variant)".format(p * 15 + i)
                       for i in range(15)] for p in range(7)]
        upgrader, fake = self.make(pages=long_pages)
        state = {"calls": 0}

        def busy():
            state["calls"] += 1
            return "rolling or claiming" if state["calls"] > 2 else None

        outcome = self.run_upgrade(upgrader, self.stock(100000), busy=busy)
        self.assertEqual(outcome.status, "upgraded")
        self.assertIn("stopped early", outcome.reason)
        self.assertEqual(len(self.oi_commands(fake)), 1)


class SettingsWiringTests(unittest.TestCase):
    def test_client_attributes_and_live_reload_keys(self):
        from mudae_core.bot_config import LIVE_CONFIG_ATTRIBUTES, configure_client

        client = NS()
        configure_client(client, "Test", {"auto_perk10": True, "perk10_amount": 4}, bot_name="Test",
                         claim_emojis=[], kakera_emojis=[], sphere_emojis=[], slash_available=False,
                         register_adaptive=False)
        self.assertEqual((client.auto_perk10, client.perk10_min_spheres, client.perk10_max_characters,
                          client.perk10_amount, client.perk10_daily_cap), (True, 2000, 100, 4, 3))
        for key in PERK10_DEFAULTS:
            self.assertIn(key, LIVE_CONFIG_ATTRIBUTES)


if __name__ == "__main__":
    unittest.main()
