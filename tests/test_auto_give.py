"""Automatic gives to the main account: $givek / $givesp → Y (a fake game bot; made-up names and ids)."""
import asyncio
import datetime
import unittest
from types import SimpleNamespace as NS

from mudae_core.auto_give import (
    AUTO_GIVE_DEFAULTS, KAKERA, MODE_AMOUNT, MODE_EVERYTHING, SPHERES, AutoGiveSettings, MainAccountGiver,
    kakera_to_give, parse_give_question, parse_give_success, receiver_problem, spheres_to_give,
    validate_auto_give_settings,
)
from mudae_core.config import validate_preset
from mudae_core.sphere_stock import KakeraStock, SphereStock

OWN_ID = "200000000000000002"
MAIN_ID = "300000000000000003"
OTHER_ID = "400000000000000004"
OWN_NAME = "TestUser"
CHANNEL = NS(id=555)
KAKERA_EMOJI = "<:kakera:1>"
SPHERE_EMOJI = "<:spR:2>"
WHEN = datetime.datetime(2026, 11, 28, 12, 0, tzinfo=datetime.timezone.utc)


def question(amount, emoji=KAKERA_EMOJI):
    return "{}, do you really want to give {} {} ? (y/n/yes/no)".format(OWN_NAME, amount, emoji)


def gifted(amount, emoji=KAKERA_EMOJI, sender=OWN_ID, receiver=MAIN_ID):
    return "<@{}> just gifted {} {} to <@{}>".format(sender, amount, emoji, receiver)


class FakeMudae:
    """Plays the game bot. ``script`` maps «command»/«y» to a reply text, "ACK" (✅ on the Y),
    "ACK_COMMAND" (✅ on the command), "REFUSE" (⛔ on the command) or None (silence)."""

    def __init__(self, ref, script=None, emoji=KAKERA_EMOJI):
        self.ref = ref
        self.script = script or {}
        self.emoji = emoji
        self.sent = []
        self.next_id = 1000
        self.command_id = None

    def _emit(self, text):
        self.next_id += 1
        message = NS(id=self.next_id, channel=CHANNEL, content=text, embeds=[], reference=None)
        asyncio.get_running_loop().call_soon(self.ref[0].on_message, message, text)

    def _react(self, kind, message_id):
        handler = self.ref[0].on_ack if kind == "ack" else self.ref[0].on_refused
        asyncio.get_running_loop().call_soon(handler, message_id)

    def _play(self, value, my_id):
        for item in value if isinstance(value, (list, tuple)) else [value]:
            if item is None:
                continue
            if item == "ACK":
                self._react("ack", my_id)
            elif item == "ACK_COMMAND":
                self._react("ack", self.command_id)
            elif item == "REFUSE":
                self._react("refused", my_id)
            else:
                self._emit(item)

    async def send(self, channel, text):
        self.sent.append(text)
        self.next_id += 1
        my_id = self.next_id
        if text.startswith("$givek ") or text.startswith("$givesp "):
            self.command_id = my_id
            amount = text.rsplit(" ", 1)[1]
            self._play(self.script.get("command", question(amount, self.emoji)), my_id)
        elif text == "Y":
            amount = self.sent[-2].rsplit(" ", 1)[1] if len(self.sent) > 1 else "0"
            self._play(self.script.get("y", gifted(amount, self.emoji)), my_id)
        return NS(id=my_id)


class Clock:
    def __init__(self, when=WHEN):
        self.now = when

    def __call__(self):
        return self.now


def make_giver(kind=KAKERA, script=None, clock=None, emoji=None, **kwargs):
    ref = [None]
    fake = FakeMudae(ref, script, emoji or (KAKERA_EMOJI if kind == KAKERA else SPHERE_EMOJI))
    logs = []

    async def wait(seconds):
        return True

    giver = MainAccountGiver(
        kind, send=fake.send, wait=wait, log=lambda message, level: logs.append((level, message)),
        clock=clock or Clock(), question_timeout=kwargs.pop("question_timeout", 0.3),
        result_timeout=kwargs.pop("result_timeout", 0.3), answer_delay=(0, 0), **kwargs,
    )
    ref[0] = giver
    return giver, fake, logs


def kakera_stock(value):
    stock = KakeraStock()
    stock.set(value)
    return stock


def sphere_stock(value):
    stock = SphereStock()
    stock.set(value)
    return stock


def settings(**values):
    data = {"auto_give_kakera": True, "auto_give_spheres": True}
    data.update(values)
    return AutoGiveSettings.from_preset(data)


def run(giver, stock, chosen=None, main_id=MAIN_ID, own_id=OWN_ID, **kwargs):
    return asyncio.run(giver.maybe_give(CHANNEL, chosen or settings(), own_id=own_id, own_names=[OWN_NAME],
                                        main_id=main_id, stock=stock, **kwargs))


class MathAndSettingsTests(unittest.TestCase):
    def test_kakera_amount(self):
        self.assertIsNone(kakera_to_give(44999, 45000))
        self.assertEqual(kakera_to_give(45000, 45000), 45000)
        self.assertEqual(kakera_to_give(45132, 45000, MODE_EVERYTHING), 45132)
        self.assertEqual(kakera_to_give(45132, 45000, MODE_AMOUNT), 45000)
        self.assertIsNone(kakera_to_give(None, 45000))

    def test_sphere_amount(self):
        self.assertEqual(spheres_to_give(1250), 1250)
        self.assertEqual(spheres_to_give(1250, 250), 1000)
        self.assertIsNone(spheres_to_give(250, 250))
        self.assertIsNone(spheres_to_give(0))
        self.assertIsNone(spheres_to_give(None))

    def test_settings(self):
        chosen = AutoGiveSettings.from_preset({})
        self.assertEqual((chosen.give_kakera, chosen.kakera_threshold, chosen.kakera_mode, chosen.kakera_daily_cap,
                          chosen.give_spheres, chosen.sphere_interval_min, chosen.spheres_keep),
                         (False, 45000, MODE_EVERYTHING, 3, False, 30, 0))
        self.assertEqual(AUTO_GIVE_DEFAULTS["give_kakera_threshold"], 45000)
        self.assertEqual(AutoGiveSettings.from_preset({"give_kakera_threshold": "50,000"}).kakera_threshold, 50000)
        self.assertEqual(AutoGiveSettings.from_preset({"give_kakera_amount_mode": "Amount"}).kakera_mode, MODE_AMOUNT)
        self.assertTrue(AutoGiveSettings.from_preset({"auto_perk10": True}).perk10_on)
        self.assertEqual(validate_auto_give_settings({}), [])
        self.assertEqual(len(validate_auto_give_settings({
            "give_kakera_threshold": 0, "give_kakera_daily_cap": 0, "sphere_give_interval_min": "x",
            "spheres_keep": -1, "give_kakera_amount_mode": "half"})), 5)

    def test_preset_validation_includes_auto_give(self):
        base = {"token": "made-up", "prefix": "!", "mudae_prefix": "$", "roll_command": "wa", "channel_id": "1",
                "claim_interval": 180, "roll_interval": 60, "max_dk_power": 100}
        self.assertEqual(validate_preset(base), [])
        self.assertTrue(any("give_kakera_daily_cap" in error
                            for error in validate_preset(dict(base, give_kakera_daily_cap=0))))

    def test_receiver(self):
        self.assertIsNone(receiver_problem(OWN_ID, MAIN_ID))
        self.assertIn("no Main Account ID", receiver_problem(OWN_ID, ""))
        self.assertIn("itself", receiver_problem(OWN_ID, " " + OWN_ID))


class ParsingTests(unittest.TestCase):
    def test_question(self):
        found = parse_give_question("Tester, do you really want to give 500 <:kakera:9> ? (y/n/yes/no)")
        self.assertEqual((found.amount, found.kind, found.mentions), (500, KAKERA, ()))
        found = parse_give_question("Tester, do you really want to give **1,250** <:spR:9> ? (y/n/yes/no)")
        self.assertEqual((found.amount, found.kind), (1250, SPHERES))
        self.assertIsNone(parse_give_question("Tester, do you really want to give 500 <:kakera:9> ?"))
        self.assertIsNone(parse_give_question("Do you really want to spend 5,000 <:spR:9> for 5 characters? (y/n)"))

    def test_success(self):
        gift = parse_give_success("<@11> just gifted 500 <:kakera:9> to <@22>")
        self.assertEqual((gift.amount, gift.sender_id, gift.receiver_id, gift.kind), (500, "11", "22", KAKERA))
        self.assertIsNone(parse_give_success("<@11> gave nothing"))


class KakeraGiveTests(unittest.TestCase):
    def test_gives_everything_and_answers_y(self):
        giver, fake, _ = make_giver()
        stock = kakera_stock(45132)
        outcome = run(giver, stock)
        self.assertEqual(outcome.status, "given", outcome)
        self.assertEqual(fake.sent, ["$givek <@{}> 45132".format(MAIN_ID), "Y"])
        self.assertEqual(stock.kakera, 0)
        self.assertEqual(giver.gives_today(), 1)

    def test_gives_only_the_amount(self):
        giver, fake, _ = make_giver()
        stock = kakera_stock(45132)
        outcome = run(giver, stock, settings(give_kakera_amount_mode="amount"))
        self.assertEqual(outcome.status, "given")
        self.assertEqual(fake.sent[0], "$givek <@{}> 45000".format(MAIN_ID))
        self.assertEqual(stock.kakera, 132)

    def test_below_threshold_or_unknown_sends_nothing(self):
        giver, fake, _ = make_giver()
        self.assertEqual(run(giver, kakera_stock(44999)).status, "skipped")
        self.assertEqual(run(giver, KakeraStock()).status, "skipped")
        self.assertEqual(run(giver, kakera_stock(50000), settings(auto_give_kakera=False)).reason, "off")
        self.assertEqual(fake.sent, [])

    def test_wrong_amount_answers_n(self):
        giver, fake, _ = make_giver(script={"command": question(4500)})
        outcome = run(giver, kakera_stock(45000))
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(fake.sent[-1], "n")
        self.assertNotIn("Y", fake.sent)

    def test_another_receiver_answers_n(self):
        text = "{}, do you really want to give 45000 {} to <@{}> ? (y/n/yes/no)".format(OWN_NAME, KAKERA_EMOJI, OTHER_ID)
        giver, fake, _ = make_giver(script={"command": text})
        self.assertEqual(run(giver, kakera_stock(45000)).status, "stopped")
        self.assertEqual(fake.sent[-1], "n")
        self.assertNotIn("Y", fake.sent)

    def test_question_about_spheres_answers_n(self):
        giver, fake, _ = make_giver(script={"command": question(45000, SPHERE_EMOJI)})
        self.assertEqual(run(giver, kakera_stock(45000)).status, "stopped")
        self.assertEqual(fake.sent[-1], "n")

    def test_success_by_check_mark_after_y(self):
        for reaction in ("ACK", "ACK_COMMAND"):
            with self.subTest(reaction=reaction):
                giver, fake, _ = make_giver(script={"y": reaction})
                stock = kakera_stock(46000)
                self.assertEqual(run(giver, stock).status, "given")
                self.assertEqual(stock.kakera, 0)

    def test_check_mark_or_gift_line_before_y_proves_nothing(self):
        early = ["ACK_COMMAND", gifted(45000), question(45000)]
        giver, fake, _ = make_giver(script={"command": early, "y": None})
        stock = kakera_stock(45000)
        outcome = run(giver, stock)
        self.assertEqual(outcome.status, "stopped")
        self.assertIn("Y", fake.sent)  # the real question was still answered
        self.assertIsNone(stock.kakera)  # unknown until the next $tu
        self.assertEqual(giver.gives_today(), 1)  # an unconfirmed give counts toward the cap

    def test_gift_line_of_another_sender_is_ignored(self):
        giver, fake, _ = make_giver(script={"y": gifted(45000, sender=OTHER_ID)})
        self.assertEqual(run(giver, kakera_stock(45000)).status, "stopped")

    def test_timeout_sends_no_y(self):
        giver, fake, logs = make_giver(script={"command": None})
        outcome = run(giver, kakera_stock(45000))
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(fake.sent, ["$givek <@{}> 45000".format(MAIN_ID)])
        self.assertTrue(any(level == "WARN" for level, _ in logs))

    def test_unknown_reply_sends_no_y(self):
        giver, fake, _ = make_giver(script={"command": "{}, something new happened.".format(OWN_NAME)})
        outcome = run(giver, kakera_stock(45000))
        self.assertEqual((outcome.status, outcome.reason), ("stopped", "unexpected reply"))
        self.assertEqual(len(fake.sent), 1)

    def test_refusal_and_back_off(self):
        giver, fake, _ = make_giver(script={"command": "{}, you don't have enough kakera.".format(OWN_NAME)})
        outcome = run(giver, kakera_stock(45000))
        self.assertEqual(outcome.reason, "the game bot refused the give")
        again = run(giver, kakera_stock(45000))
        self.assertEqual(again.status, "skipped")
        self.assertIn("backing off", again.reason)
        self.assertEqual(len(fake.sent), 1)

    def test_refused_command_reaction(self):
        giver, fake, _ = make_giver(script={"command": "REFUSE"})
        self.assertIn("⛔", run(giver, kakera_stock(45000)).reason)

    def test_daily_cap(self):
        clock = Clock()
        giver, fake, _ = make_giver(clock=clock)
        chosen = settings(give_kakera_daily_cap=1)
        self.assertEqual(run(giver, kakera_stock(45000), chosen).status, "given")
        capped = run(giver, kakera_stock(45000), chosen)
        self.assertIn("daily limit", capped.reason)
        clock.now = WHEN + datetime.timedelta(days=1)
        self.assertEqual(run(giver, kakera_stock(45000), chosen).status, "given")

    def test_never_to_itself_or_without_main(self):
        giver, fake, logs = make_giver()
        self.assertIn("itself", run(giver, kakera_stock(90000), main_id=OWN_ID).reason)
        self.assertIn("itself", run(giver, kakera_stock(90000), main_id=OWN_ID).reason)
        self.assertIn("no Main Account ID", run(giver, kakera_stock(90000), main_id="").reason)
        self.assertEqual(fake.sent, [])
        notes = [message for level, message in logs if "not giving" in message]
        self.assertEqual(len(notes), 2)  # once per reason, not once per pass

    def test_busy_defers(self):
        giver, fake, _ = make_giver()
        outcome = run(giver, kakera_stock(45000), busy=lambda: "rolling or claiming")
        self.assertIn("busy", outcome.reason)
        self.assertEqual(fake.sent, [])

    def test_becoming_busy_before_y_answers_n(self):
        giver, fake, _ = make_giver()
        calls = iter([None, "rolling or claiming"])
        outcome = run(giver, kakera_stock(45000), busy=lambda: next(calls))
        self.assertEqual(outcome.status, "stopped")
        self.assertEqual(fake.sent[-1], "n")


class SphereGiveTests(unittest.TestCase):
    def test_gives_stock_minus_keep(self):
        giver, fake, _ = make_giver(SPHERES)
        stock = sphere_stock(1250)
        outcome = run(giver, stock, settings(spheres_keep=250))
        self.assertEqual(outcome.status, "given", outcome)
        self.assertEqual(fake.sent, ["$givesp <@{}> 1000".format(MAIN_ID), "Y"])
        self.assertEqual(stock.spheres, 250)

    def test_nothing_above_keep(self):
        giver, fake, _ = make_giver(SPHERES)
        self.assertEqual(run(giver, sphere_stock(100), settings(spheres_keep=100)).status, "skipped")
        self.assertEqual(fake.sent, [])

    def test_perk10_on_does_nothing(self):
        giver, fake, logs = make_giver(SPHERES)
        outcome = run(giver, sphere_stock(5000), settings(auto_perk10=True))
        self.assertIn("perk-10", outcome.reason)
        self.assertEqual(fake.sent, [])
        self.assertTrue(any("perk-10" in message for _, message in logs))

    def test_sphere_games_first(self):
        giver, fake, _ = make_giver(SPHERES)
        outcome = run(giver, sphere_stock(5000), games=lambda: "sphere games are still available ($oh 1)")
        self.assertIn("sphere games first", outcome.reason)
        self.assertEqual(fake.sent, [])

    def test_interval(self):
        clock = Clock()
        giver, fake, _ = make_giver(SPHERES, clock=clock)
        self.assertEqual(run(giver, sphere_stock(900)).status, "given")
        clock.now = WHEN + datetime.timedelta(minutes=29)
        self.assertIn("less than 30 min", run(giver, sphere_stock(900)).reason)
        clock.now = WHEN + datetime.timedelta(minutes=31)
        self.assertEqual(run(giver, sphere_stock(900)).status, "given")
        self.assertEqual(sum(1 for text in fake.sent if text.startswith("$givesp")), 2)

    def test_kakera_question_for_spheres_answers_n(self):
        giver, fake, _ = make_giver(SPHERES, script={"command": question(900, KAKERA_EMOJI)})
        self.assertEqual(run(giver, sphere_stock(900)).status, "stopped")
        self.assertEqual(fake.sent[-1], "n")

    def test_success_by_check_mark_on_command_after_y(self):
        giver, fake, _ = make_giver(SPHERES, script={"y": "ACK_COMMAND"})
        stock = sphere_stock(900)
        self.assertEqual(run(giver, stock).status, "given")
        self.assertEqual(stock.spheres, 0)


if __name__ == "__main__":
    unittest.main()
