"""The $mmz-/$mm page buttons: layouts, verification of the turned page, retry, diagnostics (fakes only)."""
import asyncio
import unittest
from types import SimpleNamespace as NS

from mudae_core.harem_list import (
    LIST_MM, LIST_MMZ, HaremListReader, analyze_pager, describe_components, pager_buttons,
)

CHANNEL = NS(id=555)
OWNER = "SideUser"


def btn(label=None, emoji=None, custom_id=None, disabled=False):
    return NS(label=label, emoji=NS(name=emoji) if emoji else None, custom_id=custom_id, disabled=disabled)


def message(mid, page=1, pages=5, buttons=(), rows=None, names=None, reference=None, owner=OWNER, footer=True):
    embed = NS(author=NS(name="{}'s harem".format(owner)), title=None,
               description="\n".join(names or ["Name {} {}".format(page, i) for i in range(3)]),
               footer=NS(text="Page {} / {}".format(page, pages)) if footer else NS(text=""))
    components = rows if rows is not None else [NS(children=list(buttons))]
    return NS(id=mid, channel=CHANNEL, embeds=[embed], components=components,
              reference=NS(message_id=reference) if reference else None)


def ids(layout):
    return (layout.previous, layout.next)


class LayoutTests(unittest.TestCase):
    def check(self, buttons, previous_index, next_index, rows=None):
        found = analyze_pager(message(1, buttons=buttons, rows=rows))
        flat = [b for b in buttons]
        if previous_index is None:
            self.assertIsNone(found.previous)
        else:
            self.assertIs(found.previous, flat[previous_index])
        if next_index is None:
            self.assertIsNone(found.next)
        else:
            self.assertIs(found.next, flat[next_index])

    def test_two_buttons_by_position(self):
        self.check([btn("a"), btn("b")], 0, 1)

    def test_four_buttons_middle_two(self):
        self.check([btn(emoji="⏪"), btn(emoji="◀"), btn(emoji="▶"), btn(emoji="⏩")], 1, 2)

    def test_emoji_only(self):
        self.check([btn(emoji="arrow_backward"), btn(emoji="arrow_forward"), btn(emoji="x")], 0, 1)
        self.check([btn(emoji="➡"), btn(emoji="⬅")], 1, 0)  # marks beat position

    def test_label_only(self):
        self.check([btn("Close"), btn("Next"), btn("Previous")], 2, 1)

    def test_custom_id_only(self):
        self.check([btn(custom_id="mm:left:9"), btn(custom_id="mm:right:9"), btn(custom_id="mm:stop")], 0, 1)

    def test_all_rows_searched(self):
        buttons = [btn("Prev"), btn("Next")]
        found = analyze_pager(message(1, rows=[NS(children=[buttons[0]]), NS(children=[buttons[1]])]))
        self.assertEqual(ids(found), tuple(buttons))

    def test_disabled_next_is_flagged_and_not_returned(self):
        buttons = [btn("Prev"), btn("Next", disabled=True)]
        found = analyze_pager(message(1, buttons=buttons))
        self.assertTrue(found.next_disabled)
        self.assertEqual(pager_buttons(message(1, buttons=buttons))[1], None)
        self.assertIs(pager_buttons(message(1, buttons=buttons))[0], buttons[0])

    def test_no_buttons_and_select_menu(self):
        self.assertEqual(ids(analyze_pager(message(1, buttons=[]))), (None, None))
        menu = NS(options=[1, 2], custom_id="pick", disabled=False)
        found = analyze_pager(message(1, buttons=[menu]))
        self.assertEqual((found.buttons, found.selects, found.next), (0, 1, None))

    def test_description_has_no_long_ids(self):
        text = describe_components(message(1, buttons=[btn("Next", "➡", "x" * 40, True)]))
        self.assertIn("disabled=True", text)
        self.assertNotIn("x" * 40, text)


class Fake:
    """Sends the first page; on a click runs ``script(click_number, fake)`` (edit / new message / nothing)."""

    def __init__(self, reader_ref, first, script):
        self.ref, self.first, self.script = reader_ref, first, script
        self.clicks = 0
        self.sent = []
        self.message = first
        self.logs = []

    async def send(self, channel, text):
        self.sent.append(text)
        asyncio.get_running_loop().call_soon(self.ref[0].on_message, NS(**dict(vars(self.first), reference=NS(message_id=7))))
        return NS(id=7)

    async def click(self, button):
        self.clicks += 1
        asyncio.get_running_loop().call_soon(self.script, self.clicks, self)
        return True


def make(first, script):
    ref = [None]
    fake = Fake(ref, first, script)

    async def wait(seconds):
        return True

    reader = HaremListReader(send=fake.send, click=fake.click, wait=wait, reply_timeout=0.5, edit_timeout=0.3,
                             click_delay=(0, 0), retry_delay=(0, 0),
                             log=lambda text, level: fake.logs.append((level, text)))
    ref[0] = reader
    return reader, fake


def good_edit(number, fake, page=2, buttons=None):
    fake.message = message(fake.first.id, page=page, buttons=buttons or fake.first.components[0].children)
    fake.ref[0].on_edit(fake.message)


class TurnTests(unittest.TestCase):
    BUTTONS = [btn("Prev"), btn("Next")]

    def run_turn(self, script, buttons=None, pages=5):
        first = message(8, pages=pages, buttons=buttons if buttons is not None else self.BUTTONS)
        reader, fake = make(first, script)

        async def go():
            result = await reader.open(CHANNEL, LIST_MMZ, [OWNER])
            self.assertEqual(result.status, "ok", result.reason)
            return await result.pager.next()

        return asyncio.run(go()), reader, fake

    def test_edit_turns_the_page(self):
        page, reader, fake = self.run_turn(good_edit)
        self.assertEqual(page.page, 2)
        self.assertEqual(fake.clicks, 1)
        self.assertEqual(fake.sent, ["$mmz-"])
        self.assertTrue(any("Perk 10 list" in text and "opened" in text for _l, text in fake.logs))

    def test_edit_that_does_not_change_page_retries_once_then_gives_up(self):
        page, reader, fake = self.run_turn(lambda n, f: f.ref[0].on_edit(f.first))
        self.assertIsNone(page)
        self.assertEqual(fake.clicks, 2)
        errors = [text for level, text in fake.logs if level == "ERROR"]
        self.assertEqual(len(errors), 1)
        self.assertIn("could not turn the $mmz- page", errors[0])
        self.assertIn("seen:", errors[0])

    def test_first_click_ignored_second_works(self):
        def script(number, fake):
            if number == 2:
                good_edit(number, fake)
        page, reader, fake = self.run_turn(script)
        self.assertEqual((page.page, fake.clicks), (2, 2))
        self.assertEqual([l for l, _t in fake.logs if l == "ERROR"], [])

    def test_new_message_instead_of_edit(self):
        def script(number, fake):
            fake.ref[0].on_message(message(50, page=2, buttons=self.BUTTONS))
        page, reader, fake = self.run_turn(script)
        self.assertEqual((page.page, page.message_id, fake.clicks), (2, 50, 1))

    def test_new_message_of_another_user_ignored(self):
        def script(number, fake):
            fake.ref[0].on_message(message(50, page=2, buttons=self.BUTTONS, owner="Someone"))
        page, reader, fake = self.run_turn(script)
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
        self.assertEqual([l for l, _t in fake.logs if l == "ERROR"], [])

    def test_no_buttons_and_select_menu_say_so(self):
        page, reader, fake = self.run_turn(good_edit, buttons=[])
        self.assertIsNone(page)
        self.assertIn("no next button", reader.last_error)
        menu = NS(options=[1], custom_id="pick", disabled=False)
        page, reader, fake = self.run_turn(good_edit, buttons=[menu])
        self.assertIn("select menu", reader.last_error)
        self.assertEqual(fake.clicks, 0)

    def test_single_page_never_clicks(self):
        page, reader, fake = self.run_turn(good_edit, pages=1)
        self.assertIsNone(page)
        self.assertEqual(fake.clicks, 0)

    def test_four_button_layout_clicks_the_middle_next(self):
        clicked = []
        buttons = [btn("1", "⏪"), btn("2", "◀"), btn("3", "▶"), btn("4", "⏩")]
        first = message(8, buttons=buttons)
        reader, fake = make(first, lambda n, f: good_edit(n, f))
        original = fake.click

        async def click(button):
            clicked.append(button.label)
            return await original(button)

        reader._click = click

        async def go():
            result = await reader.open(CHANNEL, LIST_MM, [OWNER])
            return await result.pager.next()

        self.assertEqual(asyncio.run(go()).page, 2)
        self.assertEqual(clicked, ["3"])


if __name__ == "__main__":
    unittest.main()
