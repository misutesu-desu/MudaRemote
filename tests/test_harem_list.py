"""The $mmz- list reader: parsing, page buttons, verified page turn with one retry (fakes only)."""
import asyncio
import unittest
from types import SimpleNamespace as NS

from mudae_core.harem_list import (
    HaremListReader, analyze_pager, describe_components, parse_harem_page, parse_page_footer,
)

CHANNEL = NS(id=555)
OTHER_CHANNEL = NS(id=556)
OWNER = "TestUser"
NAMES = ["Made Up Name One", "Senpai (TS)", "Rin Tōsaka", "D'Arby", "Mr. Satan", "ミク", "A.I. Chan"]


def btn(label=None, emoji=None, custom_id=None, disabled=False):
    return NS(label=label, emoji=NS(name=emoji) if emoji else None, custom_id=custom_id, disabled=disabled)


def list_message(mid, owner=OWNER, page=1, pages=5, names=None, description=None, buttons=None, rows=None,
                 reference=None, channel=CHANNEL):
    embed = NS(author=NS(name="{}'s harem".format(owner)), title=None,
               description=description if description is not None else "\n".join(
                   names or ["Name {} {}".format(page, index) for index in range(3)]),
               footer=NS(text="Page {} / {}".format(page, pages)))
    if rows is None:
        rows = [NS(children=list(buttons if buttons is not None else [btn(emoji="⬅️"), btn(emoji="➡️")]))]
    return NS(id=mid, channel=channel, embeds=[embed], components=rows,
              reference=NS(message_id=reference) if reference else None)


class ParsingTests(unittest.TestCase):
    def test_footer(self):
        self.assertEqual(parse_page_footer("Page 1 / 158"), (1, 158))
        self.assertIsNone(parse_page_footer("no footer"))

    def test_names_kept_whole(self):
        page = parse_harem_page(list_message(10, names=NAMES, pages=158))
        self.assertEqual(page.owner, OWNER)
        self.assertEqual((page.page, page.pages), (1, 158))
        self.assertEqual(list(page.names), NAMES)

    def test_emoji_markdown_and_invisible_lines(self):
        description = "**Made Up Name One** <:wish:12>\nSenpai (TS)\n\n​\n⠀ \nMr\\. Satan"
        page = parse_harem_page(list_message(10, description=description))
        self.assertEqual(page.names, ("Made Up Name One", "Senpai (TS)", "Mr. Satan"))

    def test_not_a_list(self):
        self.assertIsNone(parse_harem_page(NS(id=1, channel=CHANNEL, embeds=[], components=[])))
        card = NS(id=1, channel=CHANNEL, components=[], embeds=[NS(author=NS(name="Made Up Name One"), title="x",
                                                                   description="y", footer=NS(text="Page 1 / 2"))])
        self.assertIsNone(parse_harem_page(card))


class LayoutTests(unittest.TestCase):
    def check(self, buttons, previous_index, next_index):
        found = analyze_pager(list_message(1, buttons=buttons))
        self.assertIs(found.previous, None if previous_index is None else buttons[previous_index])
        self.assertIs(found.next, None if next_index is None else buttons[next_index])

    def test_two_buttons_by_position(self):
        # The live $mmz- list: two buttons whose faces are custom character emojis.
        self.check([btn(emoji="madeUpFaceA"), btn(emoji="madeUpFaceB")], 0, 1)

    def test_four_buttons_middle_two(self):
        self.check([btn(emoji="⏪"), btn(emoji="◀"), btn(emoji="▶"), btn(emoji="⏩")], 1, 2)

    def test_marks_beat_position(self):
        self.check([btn(emoji="➡"), btn(emoji="⬅")], 1, 0)
        self.check([btn("Close"), btn("Next"), btn("Previous")], 2, 1)
        self.check([btn(custom_id="mm:left:9"), btn(custom_id="mm:right:9"), btn(custom_id="mm:stop")], 0, 1)

    def test_all_rows_searched(self):
        buttons = [btn("Prev"), btn("Next")]
        found = analyze_pager(list_message(1, rows=[NS(children=[buttons[0]]), NS(children=[buttons[1]])]))
        self.assertEqual((found.previous, found.next), tuple(buttons))

    def test_disabled_next_is_flagged(self):
        self.assertTrue(analyze_pager(list_message(1, buttons=[btn("Prev"), btn("Next", disabled=True)])).next_disabled)

    def test_no_buttons_and_select_menu(self):
        found = analyze_pager(list_message(1, buttons=[]))
        self.assertEqual((found.previous, found.next), (None, None))
        found = analyze_pager(list_message(1, buttons=[NS(options=[1, 2], custom_id="pick", disabled=False)]))
        self.assertEqual((found.buttons, found.selects, found.next), (0, 1, None))

    def test_description_has_no_long_ids(self):
        text = describe_components(list_message(1, buttons=[btn("Next", "➡", "x" * 40, True)]))
        self.assertIn("disabled=True", text)
        self.assertNotIn("x" * 40, text)


class Fake:
    """Sends the first page; on a click runs ``script(click_number, fake)`` (edit / new message / nothing)."""

    def __init__(self, reader_ref, first, script, extra_before=()):
        self.ref, self.first, self.script = reader_ref, first, script
        self.extra_before = extra_before
        self.clicks = 0
        self.sent = []
        self.logs = []

    async def send(self, channel, text):
        self.sent.append(text)
        loop = asyncio.get_running_loop()
        for message in self.extra_before:
            loop.call_soon(self.ref[0].on_message, message)
        loop.call_soon(self.ref[0].on_message, self.first)
        return NS(id=7)

    async def click(self, button):
        self.clicks += 1
        asyncio.get_running_loop().call_soon(self.script, self.clicks, self)
        return True


def make(first, script, **kwargs):
    ref = [None]
    fake = Fake(ref, first, script, **kwargs)

    async def wait(seconds):
        return True

    reader = HaremListReader(send=fake.send, click=fake.click, wait=wait, reply_timeout=0.5, edit_timeout=0.3,
                             click_delay=(0, 0), retry_delay=(0, 0),
                             log=lambda text, level: fake.logs.append((level, text)))
    ref[0] = reader
    return reader, fake


def good_edit(number, fake, page=2):
    fake.ref[0].on_edit(list_message(fake.first.id, page=page, buttons=fake.first.components[0].children))


class ReaderTests(unittest.TestCase):
    BUTTONS = [btn("Prev"), btn("Next")]

    def run_turn(self, script, buttons=None, pages=5, **kwargs):
        first = list_message(8, pages=pages, buttons=buttons if buttons is not None else self.BUTTONS, reference=7)
        reader, fake = make(first, script, **kwargs)

        async def go():
            result = await reader.open(CHANNEL, [OWNER])
            self.assertEqual(result.status, "ok", result.reason)
            return await result.pager.next()

        return asyncio.run(go()), reader, fake

    def test_edit_turns_the_page_with_one_command(self):
        page, reader, fake = self.run_turn(good_edit)
        self.assertEqual(page.page, 2)
        self.assertEqual(fake.clicks, 1)
        self.assertEqual(fake.sent, ["$mmz-"])
        self.assertTrue(any("opened" in text for _level, text in fake.logs))

    def test_prefix(self):
        reader, fake = make(list_message(8), good_edit)
        asyncio.run(reader.open(CHANNEL, [OWNER], prefix="!"))
        self.assertEqual(fake.sent, ["!mmz-"])

    def test_edit_that_does_not_change_page_retries_once_then_gives_up(self):
        page, reader, fake = self.run_turn(lambda n, f: f.ref[0].on_edit(f.first))
        self.assertIsNone(page)
        self.assertEqual(fake.clicks, 2)
        errors = [text for level, text in fake.logs if level == "ERROR"]
        self.assertEqual(len(errors), 1)
        self.assertIn("could not turn the $mmz- page", errors[0])
        self.assertIn("did not appear", reader.last_error)

    def test_first_click_ignored_second_works(self):
        def script(number, fake):
            if number == 2:
                good_edit(number, fake)
        page, reader, fake = self.run_turn(script)
        self.assertEqual((page.page, fake.clicks), (2, 2))
        self.assertEqual([level for level, _text in fake.logs if level == "ERROR"], [])

    def test_new_message_instead_of_edit(self):
        page, reader, fake = self.run_turn(
            lambda n, f: f.ref[0].on_message(list_message(50, page=2, buttons=self.BUTTONS)))
        self.assertEqual((page.page, page.message_id, fake.clicks), (2, 50, 1))

    def test_new_message_of_another_user_ignored(self):
        page, reader, fake = self.run_turn(
            lambda n, f: f.ref[0].on_message(list_message(50, page=2, buttons=self.BUTTONS, owner="Someone")))
        self.assertIsNone(page)
        self.assertEqual(fake.clicks, 2)

    def test_wrong_page_stops_without_retry(self):
        page, reader, fake = self.run_turn(lambda n, f: good_edit(n, f, page=4))
        self.assertIsNone(page)
        self.assertEqual(fake.clicks, 1)
        self.assertIn("jumped to page 4", reader.last_error)

    def test_disabled_next_stops_cleanly_without_click(self):
        page, reader, fake = self.run_turn(good_edit, buttons=[btn("Prev"), btn("Next", disabled=True)])
        self.assertIsNone(page)
        self.assertEqual((fake.clicks, reader.last_error), (0, ""))

    def test_no_buttons_and_select_menu_say_so(self):
        page, reader, fake = self.run_turn(good_edit, buttons=[])
        self.assertIsNone(page)
        self.assertIn("no next button", reader.last_error)
        page, reader, fake = self.run_turn(good_edit, buttons=[NS(options=[1], custom_id="pick", disabled=False)])
        self.assertIn("select menu", reader.last_error)
        self.assertEqual(fake.clicks, 0)

    def test_single_page_never_clicks(self):
        page, reader, fake = self.run_turn(good_edit, pages=1)
        self.assertIsNone(page)
        self.assertEqual(fake.clicks, 0)

    def test_foreign_lists_ignored(self):
        foreign = [list_message(9, owner="OtherUser"), list_message(10, channel=OTHER_CHANNEL),
                   list_message(11, reference=999)]
        first = list_message(12, pages=12, reference=7)
        reader, fake = make(first, good_edit, extra_before=foreign)
        result = asyncio.run(reader.open(CHANNEL, ["testuser"]))
        self.assertEqual(result.status, "ok")
        self.assertEqual((result.page.message_id, result.page.pages), (12, 12))

    def test_only_foreign_list_times_out(self):
        reader, fake = make(list_message(8, owner="OtherUser"), good_edit)
        result = asyncio.run(reader.open(CHANNEL, [OWNER]))
        self.assertEqual(result.status, "failed")
        self.assertIn("in time", result.reason)


if __name__ == "__main__":
    unittest.main()
