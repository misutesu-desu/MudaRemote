"""Sphere stock read from the $tu reply and from sphere-game results (made-up text only)."""
import unittest

from mudae_core.sphere_stock import (
    KakeraStock, SphereStock, is_kakera_emoji, is_sphere_emoji, parse_amount, parse_sphere_game_result,
    parse_tu_kakera_stock, parse_tu_sphere_stock,
)

TU_REPLY = "\n".join([
    "Tester, you can't claim for another **48** min.",
    "You have **57** rolls left. Next rolls reset in **48** min.",
    "",
    "Power: **21%**",
    "Stock: **159,247** <:kakera:100>",
    "",
    "$rt is available!",
    "**0** $oh left for today, **0** $oc, **0** $oq and **0** $ot (+**1** stored).",
    "**14h 42** min before the refill. **4/12** buttons clicked.",
    "Stock: **905** <:spR:200>",
    "(Perk 9) NOT rolled today: **103**/107",
    "**0** <:key:300>",
])


class ParsingTests(unittest.TestCase):
    def test_amounts(self):
        self.assertEqual(parse_amount("159,247"), 159247)
        self.assertEqual(parse_amount("**1.225**"), 1225)
        self.assertEqual(parse_amount("8 635"), 8635)
        self.assertIsNone(parse_amount("x"))

    def test_sphere_emoji_names(self):
        for name in ("spR", "spB2", "sp", ":spO:", "redsphere"):
            self.assertTrue(is_sphere_emoji(name), name)
        for name in ("kakera", "kakeraP", "key", ""):
            self.assertFalse(is_sphere_emoji(name), name)

    def test_tu_takes_the_stock_line_with_the_sphere_emoji(self):
        self.assertEqual(parse_tu_sphere_stock(TU_REPLY), 905)
        swapped = "Stock: **1,225** <:spR:2>\nStock: **119,937** <:kakera:1>"
        self.assertEqual(parse_tu_sphere_stock(swapped), 1225)  # never by position
        self.assertEqual(parse_tu_sphere_stock("Stock: 7 :spR:"), 7)

    def test_tu_without_sphere_stock_or_disagreeing_lines(self):
        self.assertIsNone(parse_tu_sphere_stock("Stock: **159,247** <:kakera:100>"))
        self.assertIsNone(parse_tu_sphere_stock("Stock: 5 <:spR:1>\nStock: 6 <:spB:1>"))

    def test_tu_takes_the_stock_line_with_the_kakera_emoji(self):
        self.assertEqual(parse_tu_kakera_stock(TU_REPLY), 159247)
        self.assertEqual(parse_tu_kakera_stock("Stock: **1,225** <:spR:2>\nStock: **119,937** <:kakera:1>"), 119937)
        self.assertIsNone(parse_tu_kakera_stock("Stock: **905** <:spR:200>"))
        self.assertTrue(is_kakera_emoji(":kakeraP:"))
        self.assertFalse(is_kakera_emoji("spR"))

    def test_game_result(self):
        text = "<:spB:1> +28\n<:spB:1> +28\n<:spR:1> +168\n<:spP:1> (Free) +92\n<:spO:1> +108 (Stock: **8,635**)"
        self.assertEqual(parse_sphere_game_result(text), ((28, 28, 168, 92, 108), 8635))
        self.assertEqual(parse_sphere_game_result("<:kakeraP:1> +50"), ((), None))


class StockTests(unittest.TestCase):
    def test_tu_sets_and_missing_line_makes_it_unknown(self):
        stock = SphereStock()
        self.assertIsNone(stock.spheres)
        stock.apply_tu(TU_REPLY)
        self.assertEqual(stock.spheres, 905)
        stock.apply_tu("Stock: **159,247** <:kakera:100>")
        self.assertIsNone(stock.spheres)

    def test_game_stock_line_is_authoritative(self):
        stock = SphereStock()
        self.assertTrue(stock.apply_game_result(1, "<:spB:1> +28\n<:spO:1> +108 (Stock: **8,635**)"))
        self.assertEqual(stock.spheres, 8635)
        self.assertFalse(stock.apply_game_result(1, "<:spB:1> +28\n<:spO:1> +108\n<:spR:1> +5"))
        self.assertEqual(stock.spheres, 8635)

    def test_gain_lines_added_once_per_edit(self):
        stock = SphereStock()
        stock.set(1000)
        self.assertTrue(stock.apply_game_result(2, "<:spB:1> +28"))
        self.assertTrue(stock.apply_game_result(2, "<:spB:1> +28\n<:spR:1> +100"))
        self.assertFalse(stock.apply_game_result(2, "<:spB:1> +28\n<:spR:1> +100"))
        self.assertEqual(stock.spheres, 1128)

    def test_unknown_stock_stays_unknown_on_gains(self):
        stock = SphereStock()
        self.assertFalse(stock.apply_game_result(3, "<:spB:1> +28"))
        self.assertIsNone(stock.spheres)

    def test_spend(self):
        stock = SphereStock()
        self.assertIsNone(stock.spend(1000))
        stock.set(2500)
        self.assertEqual(stock.spend(2000), 500)


    def test_kakera_stock(self):
        stock = KakeraStock()
        self.assertIsNone(stock.kakera)
        self.assertEqual(stock.apply_tu(TU_REPLY), 159247)
        self.assertEqual(stock.spend(59247), 100000)
        stock.apply_tu("Stock: **905** <:spR:200>")
        self.assertIsNone(stock.kakera)


if __name__ == "__main__":
    unittest.main()
