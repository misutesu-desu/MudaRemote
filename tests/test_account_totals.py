import datetime
import unittest

from mudae_core.totals import (
    KAKERA, SPHERES, SOURCE_GAME, SOURCE_TU, AccountTotals, TotalsBook, account_key,
    emoji_kind, parse_amount, parse_sphere_game_result, parse_tu_totals,
)

# The owner's $tu (SAMPLES.md), raw message content: custom emojis as <:name:id>.
TU_RAW = """Someone, you can't claim for another **48** min.
You have **57** rolls left. Next rolls reset in **48** min.
Next $daily reset in **7h 54** min.

You can't react to kakera for **27** min.
Power: **21%**
Each kakera button consumes 30% of your reaction power.
Your characters with 10+ keys consume half the power (15%)
Stock: **159,247** <:kakera:469835869059153940>

$rt is available!
Next $dk in **3h 48** min.
You may vote right now!

**0** $oh left for today, **0** $oc, **0** $oq and **0** $ot (+**1** stored).
**14h 42** min before the refill. **4/12** buttons clicked.
Stock: **905** <:spR:1080000000000000001>
(Perk 9) NOT rolled today: **103**/107
(Perk 8) Clicked today: **8**/40. Rolled today: **2**/12
(Perk 8) NOT clicked today: **32**/40. NOT rolled today: **10**/12
(Perk 9) Rolled today: **4**/107
**0** <:key:1000000000000000002>
Shop 6: not spawned."""

# The same reply as a client renders it (emoji names between colons, no bold).
TU_RENDERED = TU_RAW.replace("<:kakera:469835869059153940>", ":kakera:").replace(
    "<:spR:1080000000000000001>", ":spR:").replace("**", "")

WHEN = datetime.datetime(2026, 11, 28, 12, 0, tzinfo=datetime.timezone.utc)


def _lines_without(text, needle):
    return "\n".join(line for line in text.splitlines() if needle not in line)


class TuTotalsTests(unittest.TestCase):
    def test_raw_sample_reads_both_totals(self):
        totals = parse_tu_totals(TU_RAW)
        self.assertEqual(totals.kakera, 159247)
        self.assertEqual(totals.spheres, 905)

    def test_rendered_sample_reads_both_totals(self):
        totals = parse_tu_totals(TU_RENDERED)
        self.assertEqual((totals.kakera, totals.spheres), (159247, 905))

    def test_rearranged_order_uses_the_emoji_not_the_position(self):
        lines = TU_RAW.splitlines()
        kakera_line = next(line for line in lines if "kakera:4698" in line)
        sphere_line = next(line for line in lines if "spR" in line)
        swapped = [sphere_line if line == kakera_line else kakera_line if line == sphere_line else line
                   for line in lines]
        totals = parse_tu_totals("\n".join(swapped))
        self.assertEqual((totals.kakera, totals.spheres), (159247, 905))

    def test_missing_kakera_line_is_unknown_not_zero(self):
        totals = parse_tu_totals(_lines_without(TU_RAW, "kakera:4698"))
        self.assertIsNone(totals.kakera)
        self.assertEqual(totals.spheres, 905)

    def test_missing_sphere_line_is_unknown(self):
        totals = parse_tu_totals(_lines_without(TU_RAW, "spR"))
        self.assertEqual(totals.kakera, 159247)
        self.assertIsNone(totals.spheres)

    def test_stock_without_emoji_is_not_guessed(self):
        totals = parse_tu_totals("Stock: **159,247**\nStock: **905**")
        self.assertEqual((totals.kakera, totals.spheres), (None, None))

    def test_thousands_separators(self):
        for text, expected in (("159,247", 159247), ("159.247", 159247), ("159 247", 159247),
                               ("1 234 567", 1234567), ("1 000", 1000), ("905", 905)):
            with self.subTest(text=text):
                self.assertEqual(parse_tu_totals("Stock: **{}** <:kakera:1>".format(text)).kakera, expected)
        self.assertEqual(parse_amount("12,345,678"), 12345678)
        self.assertIsNone(parse_amount("abc"))

    def test_two_disagreeing_kakera_lines_are_unknown(self):
        text = "Stock: 10 <:kakera:1>\nStock: 20 <:kakeraP:2>"
        self.assertIsNone(parse_tu_totals(text).kakera)

    def test_emoji_kinds(self):
        for name in ("kakera", "kakeraP", ":kakeraY:", "KAKERA"):
            self.assertEqual(emoji_kind(name), KAKERA)
        for name in ("spR", "sp", "spB2", "sphere_red"):
            self.assertEqual(emoji_kind(name), SPHERES)
        for name in ("key", "", None, "spark"):
            self.assertIsNone(emoji_kind(name))

    def test_existing_tu_parsers_still_read_the_sample(self):
        # Adding totals leaves what the code already parses from $tu alone.
        from mudae_core.spheres import parse_sphere_game_status, parse_sphere_button_count
        status = parse_sphere_game_status(TU_RAW)
        self.assertIsNotNone(status)
        self.assertEqual(status.stored_for("ot"), 1)
        self.assertEqual(parse_sphere_button_count(TU_RAW), (4, 12))


GAME_FULL = ("<:spB:11> +28\n<:spB:11> +28\n<:spR:12> +168\n<:spG:13> +53\n"
             "<:spO:14> +108 (Stock: **8,635**)")
GAME_NO_STOCK = "<:spB:11> +292\n<:spY:15> +212\n<:spP:16> (Free) +92\n<:spR:12> +672"


class SphereGameResultTests(unittest.TestCase):
    def test_full_result_has_gains_and_stock(self):
        result = parse_sphere_game_result(GAME_FULL)
        self.assertEqual(result.gains, (28, 28, 168, 53, 108))
        self.assertEqual(result.stock, 8635)

    def test_free_line_counts(self):
        result = parse_sphere_game_result(GAME_NO_STOCK)
        self.assertEqual(sum(result.gains), 292 + 212 + 92 + 672)
        self.assertIsNone(result.stock)

    def test_rendered_emojis(self):
        rendered = GAME_FULL.replace("<:spB:11>", ":spB:").replace("<:spO:14>", ":spO:").replace(
            "<:spR:12>", ":spR:").replace("<:spG:13>", ":spG:").replace("**", "")
        self.assertEqual(parse_sphere_game_result(rendered).stock, 8635)
        self.assertEqual(len(parse_sphere_game_result(rendered).gains), 5)

    def test_other_plus_lines_are_not_spheres(self):
        result = parse_sphere_game_result("<:kakera:1> +500\n+3 rolls\nYou can click **5** times")
        self.assertFalse(result.is_result)

    def test_stock_sets_the_total(self):
        totals = AccountTotals(clock=lambda: WHEN)
        totals.apply_tu(TU_RAW)
        totals.apply_sphere_game_result(900, GAME_FULL)
        self.assertEqual(totals.spheres, 8635)
        self.assertEqual(totals.snapshot()["spheres_source"], SOURCE_GAME)

    def test_without_stock_adds_gains(self):
        totals = AccountTotals(clock=lambda: WHEN)
        totals.apply_tu(TU_RAW)
        totals.apply_sphere_game_result(901, GAME_NO_STOCK)
        self.assertEqual(totals.spheres, 905 + 292 + 212 + 92 + 672)

    def test_unknown_total_stays_unknown_without_stock(self):
        totals = AccountTotals(clock=lambda: WHEN)
        totals.apply_sphere_game_result(902, GAME_NO_STOCK)
        self.assertIsNone(totals.spheres)

    def test_same_message_edited_five_times_counts_each_line_once(self):
        totals = AccountTotals(clock=lambda: WHEN)
        totals.set_total(SPHERES, 1000, SOURCE_TU)
        lines = GAME_NO_STOCK.splitlines() + ["<:spB:11> +10"]
        for count in range(1, 6):  # the bot edits the message after each click
            totals.apply_sphere_game_result(903, "\n".join(lines[:count]))
            totals.apply_sphere_game_result(903, "\n".join(lines[:count]))  # duplicate edit event
        self.assertEqual(totals.spheres, 1000 + 292 + 212 + 92 + 672 + 10)

    def test_five_edits_ending_with_stock_is_authoritative(self):
        totals = AccountTotals(clock=lambda: WHEN)
        totals.set_total(SPHERES, 8000, SOURCE_TU)
        lines = GAME_FULL.splitlines()
        for count in range(1, 6):
            totals.apply_sphere_game_result(904, "\n".join(lines[:count]))
        self.assertEqual(totals.spheres, 8635)
        totals.apply_sphere_game_result(904, GAME_FULL)  # a later identical edit changes nothing
        self.assertEqual(totals.spheres, 8635)


class RunningTotalsTests(unittest.TestCase):
    def test_tu_updates_both_and_snapshot(self):
        totals = AccountTotals("Main", clock=lambda: WHEN)
        totals.apply_tu(TU_RAW)
        snap = totals.snapshot()
        self.assertEqual((snap["kakera"], snap["spheres"]), (159247, 905))
        self.assertEqual(snap["source"], SOURCE_TU)
        self.assertEqual(snap["as_of"], WHEN.isoformat())
        self.assertIn("159,247", totals.describe())

    def test_tu_missing_line_makes_total_unknown(self):
        totals = AccountTotals(clock=lambda: WHEN)
        totals.apply_tu(TU_RAW)
        totals.apply_tu(_lines_without(TU_RAW, "kakera:4698"))
        self.assertIsNone(totals.kakera)
        self.assertEqual(totals.spheres, 905)

    def test_at_least_needs_a_known_total(self):
        totals = AccountTotals(clock=lambda: WHEN)
        self.assertFalse(totals.spheres_at_least(2000))
        totals.set_total(SPHERES, 2000, SOURCE_TU)
        self.assertTrue(totals.spheres_at_least(2000))
        self.assertFalse(totals.kakera_at_least(1))

    def test_add_to_known_and_unknown(self):
        totals = AccountTotals(clock=lambda: WHEN)
        self.assertIsNone(totals.add(KAKERA, 500, "give"))
        totals.set_total(KAKERA, 1000, SOURCE_TU)
        self.assertEqual(totals.add(KAKERA, -400, "give"), 600)

    def test_book_keys_and_user_ids(self):
        book = TotalsBook(clock=lambda: WHEN)
        key = account_key("p123", 2)
        self.assertEqual(key, "p123#2")
        main = book.account(account_key("pmain"), "Main")
        book.note_user_id(account_key("pmain"), 111111111111111111)
        self.assertIs(book.by_user_id("111111111111111111"), main)
        self.assertIsNone(book.by_user_id("222"))
        self.assertIn("pmain#1", book.snapshot_all())


class TotalsActivityEventTests(unittest.TestCase):
    def test_totals_and_give_lines_become_events(self):
        from mudae_core.activity_events import ActivityClassifier
        totals = AccountTotals(clock=lambda: WHEN)
        totals.apply_tu(TU_RAW)
        events = ActivityClassifier().classify("INFO", "Totals: {} (from $tu)".format(totals.describe()))
        self.assertEqual(events[0][0], "totals")
        self.assertEqual((events[0][1]["kakera"], events[0][1]["spheres"]), (159247, 905))
        events = ActivityClassifier().classify("SUCCESS", "Auto-give: gave 45,132 kakera to the main (give 1 today).")
        self.assertEqual(events[0], ("kakera_give", {"kakera": 45132, "message": "Gave 45,132 kakera to the main"}))


if __name__ == "__main__":
    unittest.main()
