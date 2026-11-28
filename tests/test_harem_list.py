import asyncio
import unittest
from types import SimpleNamespace as NS

from mudae_core.harem_list import (
    LIST_MM, LIST_MMI, LIST_MMRK, LIST_MMZ, HaremListReader, pager_buttons, parse_harem_page,
    parse_mmi_footer, parse_page_footer,
)

KAKERA = "<:kakera:469835869059153940>"
CHANNEL = NS(id=555)
OTHER_CHANNEL = NS(id=556)

MM_NAMES = ["Satanichia McDowell Kurumizawa", "Senpai (TS)", "Hatsune Miku", "Rin Tōsaka", "D'Arby",
            "Mr. Satan", "ミク", "Jeanne d'Arc (Alter)", "A.I. Chan"]
MMRK_DESCRIPTION = "\n".join([
    "AVG: 4,541", "Top 15 value: 183", "", "Total value: 2,610,402 " + KAKERA, "",
    "#1 - Hatsune Miku 81,012 ka", "#2 - Senpai (TS) 60,500 ka", "#3 - Rin Tōsaka 55,000 ka",
    "#6 - Jeanne d'Arc (Alter) 40,001 ka", "#7 - Mr. Satan 9 ka", "#9 - **Satanichia McDowell Kurumizawa** 1,234 ka",
])
MMI_DESCRIPTION = "\n".join(["Gabriel DropOut", "Animanga roulette · 54,058 " + KAKERA + " · <:key:1> (822)",
                             "Claim Rank: #221", "Like Rank: #117", "Alias: Satania"])


def button(name):
    return NS(emoji=NS(name=name), label=None, custom_id=None, disabled=False)


def list_message(mid, owner="SideUser", page=1, pages=177, names=MM_NAMES, channel=CHANNEL, reference=None,
                 description=None, buttons=("⬅️", "➡️")):
    embed = NS(author=NS(name="{}'s harem".format(owner)), title=None,
               description=description if description is not None else "\n".join(names),
               footer=NS(text="Page {} / {}".format(page, pages)))
    return NS(id=mid, channel=channel, embeds=[embed], reference=NS(message_id=reference) if reference else None,
              components=[NS(children=[button(name) for name in buttons])])


def mmi_message(mid, owner="SideUser", index=1, total=2655, channel=CHANNEL):
    embed = NS(author=NS(name="Satanichia McDowell Kurumizawa"), title="Satanichia McDowell Kurumizawa",
               description=MMI_DESCRIPTION, footer=NS(text="Belongs to {} ~~ {} / {}".format(owner, index, total)))
    return NS(id=mid, channel=channel, embeds=[embed], reference=None, components=[])


class ParsingTests(unittest.TestCase):
    def test_footers(self):
        self.assertEqual(parse_page_footer("Page 1 / 158"), (1, 158))
        self.assertEqual(parse_mmi_footer("Belongs to Side User ~~ 1 / 2655"), ("Side User", 1, 2655))
        self.assertIsNone(parse_page_footer("no footer"))

    def test_mm_names_whole(self):
        page = parse_harem_page(list_message(10), LIST_MM)
        self.assertEqual(page.owner, "SideUser")
        self.assertEqual((page.page, page.pages), (1, 177))
        self.assertEqual(list(page.names), MM_NAMES)

    def test_mmz_with_emoji_and_markdown(self):
        description = "**Satanichia McDowell Kurumizawa** <:wish:12>\nSenpai (TS)\n\nMr\\. Satan"
        page = parse_harem_page(list_message(10, page=1, pages=158, description=description), LIST_MMZ)
        self.assertEqual(page.names, ("Satanichia McDowell Kurumizawa", "Senpai (TS)", "Mr. Satan"))
        self.assertEqual(page.pages, 158)

    def test_mmrk(self):
        page = parse_harem_page(list_message(10, description=MMRK_DESCRIPTION), LIST_MMRK)
        self.assertEqual(page.total_value, 2610402)
        self.assertEqual([item.rank for item in page.ranked], [1, 2, 3, 6, 7, 9])
        self.assertEqual(page.ranked[0].name, "Hatsune Miku")
        self.assertEqual(page.ranked[0].value, 81012)
        self.assertEqual(page.ranked[3].name, "Jeanne d'Arc (Alter)")
        self.assertEqual(page.ranked[5].name, "Satanichia McDowell Kurumizawa")
        self.assertEqual(page.ranked[4].value, 9)

    def test_mmi(self):
        page = parse_harem_page(mmi_message(10), LIST_MMI)
        self.assertEqual((page.owner, page.page, page.character_total), ("SideUser", 1, 2655))
        self.assertEqual(page.card_value, 54058)
        self.assertEqual(page.names, ("Satanichia McDowell Kurumizawa",))

    def test_not_a_list(self):
        self.assertIsNone(parse_harem_page(NS(id=1, channel=CHANNEL, embeds=[], components=[]), LIST_MM))
        plain = NS(id=1, channel=CHANNEL, components=[], embeds=[NS(author=NS(name="Hatsune Miku"), title="x",
                                                                    description="y", footer=NS(text="Page 1 / 2"))])
        self.assertIsNone(parse_harem_page(plain, LIST_MM))

    def test_pager_buttons(self):
        prev, nxt = pager_buttons(list_message(1))
        self.assertEqual((prev.emoji.name, nxt.emoji.name), ("⬅️", "➡️"))
        prev, nxt = pager_buttons(list_message(1, buttons=("a", "b")))
        self.assertEqual((prev.emoji.name, nxt.emoji.name), ("a", "b"))


class FakeDiscord:
    """Answers our list commands and edits the list message when a button is clicked."""

    def __init__(self, reader_ref, *, replies=None, edit=True, extra_before=()):
        self.reader_ref = reader_ref
        self.sent = []
        self.clicks = []
        self.next_id = 100
        self.replies = replies
        self.edit = edit
        self.extra_before = extra_before
        self.message = None

    async def send(self, channel, text):
        self.sent.append(text)
        self.next_id += 1
        my_id = self.next_id
        loop = asyncio.get_running_loop()
        for factory in self.extra_before:
            self.next_id += 1
            loop.call_soon(self.reader_ref[0].on_message, factory(self.next_id, my_id))
        self.next_id += 1
        self.message = (self.replies or (lambda mid, ref: list_message(mid, reference=ref)))(self.next_id, my_id)
        loop.call_soon(self.reader_ref[0].on_message, self.message)
        return NS(id=my_id)

    async def click(self, target):
        self.clicks.append(target.emoji.name)
        if not self.edit:
            return True
        page = parse_harem_page(self.message, LIST_MM)
        step = 1 if target.emoji.name == "➡️" else -1
        loop = asyncio.get_running_loop()
        loading = self.message  # an edit that does not turn the page yet
        loop.call_soon(self.reader_ref[0].on_edit, loading)
        self.message = list_message(self.message.id, page=page.page + step, pages=page.pages)
        loop.call_soon(self.reader_ref[0].on_edit, self.message)
        return True


class ReaderTests(unittest.TestCase):
    def make(self, **kwargs):
        ref = [None]
        fake = FakeDiscord(ref, **kwargs)

        async def wait(seconds):
            return True

        reader = HaremListReader(send=fake.send, click=fake.click, wait=wait, reply_timeout=0.4,
                                 edit_timeout=0.4, click_delay=(0, 0), retry_delay=(0, 0))
        ref[0] = reader
        return reader, fake

    def test_open_and_page_through(self):
        reader, fake = self.make()

        async def run():
            result = await reader.open(CHANNEL, LIST_MM, ["SideUser"])
            self.assertEqual(result.status, "ok", result.reason)
            pager = result.pager
            self.assertEqual((await pager.next()).page, 2)
            self.assertEqual((await pager.next()).page, 3)
            self.assertEqual((await pager.previous()).page, 2)
            return result

        asyncio.run(run())
        self.assertEqual(fake.sent, ["$mm"])  # one command; pages turned by buttons
        self.assertEqual(fake.clicks, ["➡️", "➡️", "⬅️"])

    def test_read_collects(self):
        reader, fake = self.make()
        result = asyncio.run(reader.read(CHANNEL, LIST_MM, ["SideUser"], max_pages=3))
        self.assertEqual([page.page for page in result.pages], [1, 2, 3])

    def test_edit_timeout(self):
        reader, fake = self.make(edit=False)

        async def run():
            result = await reader.open(CHANNEL, LIST_MM, ["SideUser"])
            return await result.pager.next()

        self.assertIsNone(asyncio.run(run()))
        self.assertIn("did not appear", reader.last_error)
        self.assertEqual(fake.clicks, ["➡️", "➡️"])  # one retry, no loop

    def test_foreign_list_ignored(self):
        foreign = [lambda mid, ref: list_message(mid, owner="OtherUser"),
                   lambda mid, ref: list_message(mid, channel=OTHER_CHANNEL),
                   lambda mid, ref: list_message(mid, reference=ref + 999)]
        reader, fake = self.make(extra_before=foreign,
                                 replies=lambda mid, ref: list_message(mid, pages=12, reference=ref))
        result = asyncio.run(reader.open(CHANNEL, LIST_MM, ["sideuser"]))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.page.pages, 12)

    def test_only_foreign_list_times_out(self):
        reader, fake = self.make(replies=lambda mid, ref: list_message(mid, owner="OtherUser"))
        result = asyncio.run(reader.open(CHANNEL, LIST_MM, ["SideUser"]))
        self.assertEqual(result.status, "failed")
        self.assertIn("in time", result.reason)

    def test_mmi_owner_from_footer(self):
        reader, fake = self.make(replies=lambda mid, ref: mmi_message(mid))
        result = asyncio.run(reader.open(CHANNEL, LIST_MMI, ["SideUser"]))
        self.assertEqual(result.page.character_total, 2655)
        self.assertEqual(fake.sent, ["$mmi"])


if __name__ == "__main__":
    unittest.main()
