"""Read this account's own harem lists (``$mm``, ``$mmz-``, ``$mmrk``, ``$mmi``).

Pure parsing plus a small pager; nothing here imports discord. Messages are
read duck-typed (``id``, ``channel.id``/``channel_id``, ``embeds``,
``components``, ``reference``), so the bot passes its message objects as-is and
the tests pass simple stand-ins.

Shapes (the owner's screenshots):

* ``$mm`` / ``$mmz-``: author «<user>'s harem», one NAME per description line,
  footer «Page i / N».
* ``$mmrk``: header lines («AVG: 4,541», «Top 15 value: 183», «Total value:
  2,610,402 <kakera>»), then «#rank - Name 81,012 ka» lines (ranks are claim
  ranks, not consecutive), footer «Page i / N».
* ``$mmi``: one character card per page: title = name, a line «<type> · 54,058
  <kakera> · <key> (822)», footer «Belongs to <user> ~~ i / TOTAL».

Pages are turned with the two BUTTONS under the list; the bot then EDITS the
same message in place. The pager clicks through an injected ``click(button)``
(the bot's ``guarded_click``) and waits for the edit of that message id, fed
through ``on_edit``; it never sends a new command per page.

Only a list whose owner is THIS account and that answers THIS account's own
command (same channel, after the command, in the time window, replying to it
when Discord says what it replies to) is accepted; another user's list is
ignored.
"""

import asyncio
import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from .totals import NUMBER, parse_amount

LIST_MM = "mm"
LIST_MMZ = "mmz-"
LIST_MMRK = "mmrk"
LIST_MMI = "mmi"
LIST_KINDS = (LIST_MM, LIST_MMZ, LIST_MMRK, LIST_MMI)

REPLY_TIMEOUT_SECONDS = 15.0
EDIT_TIMEOUT_SECONDS = 10.0
CLICK_DELAY_SECONDS = (0.9, 1.8)
RETRY_DELAY_SECONDS = (1.5, 3.0)

_CUSTOM_EMOJI = re.compile(r"<a?:[A-Za-z0-9_~]+:\d+>")
_PAGE_FOOTER = re.compile(r"(?:page|p[aá]gina|seite)\s*(?P<i>\d+)\s*/\s*(?P<n>\d+)", re.IGNORECASE)
_MMI_FOOTER = re.compile(r"belongs to\s+(?P<owner>.+?)\s*~~\s*(?P<i>\d+)\s*/\s*(?P<n>\d+)", re.IGNORECASE)
_AUTHOR = re.compile(r"^(?P<owner>.+?)(?:'|’)s\s+harem\b", re.IGNORECASE)
_TOTAL_VALUE = re.compile(r"total value\s*:\s*\**\s*(?P<num>" + NUMBER + r")", re.IGNORECASE)
_RANK_LINE = re.compile(r"^#(?P<rank>\d+)\s*[-–—]\s*(?P<name>.+?)\s+(?P<num>" + NUMBER + r")\s*ka\s*$", re.IGNORECASE)
_HEADER_LINE = re.compile(r"^(?:avg|average|top\s*\d+\s*value|total value)\s*:", re.IGNORECASE)
_CARD_VALUE = re.compile(r"(?:^|·|\s)\s*\**(?P<num>" + NUMBER + r")\**\s*(?:<a?:kakera[A-Za-z0-9_~]*:\d+>|:kakera[A-Za-z0-9_~]*:|ka\b)",
                         re.IGNORECASE)

# ---------------------------------------------------------------------------
# Decision table for the page buttons (data: correct it here when the real bot differs)
# ---------------------------------------------------------------------------
# A button is «previous»/«next» when any mark below is found in its emoji name
# (a unicode emoji's name is the character itself), its label or its
# custom_id (case-folded). A button matching both directions is not used.
PAGER_MARKS = {
    "previous": ("⬅", "◀", "⏪", "arrow_backward", "arrow_left", "left", "previous", "prev", "back"),
    "next": ("➡", "▶", "⏩", "arrow_forward", "arrow_right", "right", "next", "forward"),
}
# When the marks are not enough: layout by the number of ENABLED+DISABLED
# buttons in all rows → (index of previous, index of next).
PAGER_POSITIONS = {
    2: (0, 1),  # previous, next
    4: (1, 2),  # first, previous, next, last: the two middle ones
}
# Order of the rules, shown in diagnostics: 4 buttons → middle two; else marks; else 2 buttons → first/last.

# ---------------------------------------------------------------------------
# Reading the embed
# ---------------------------------------------------------------------------

def _get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _text(value) -> str:
    return str(value or "")


def first_embed(message):
    embeds = _get(message, "embeds") or ()
    return embeds[0] if embeds else None


def clean_line(line) -> str:
    """A printed line: custom-emoji tokens and markdown wrappers removed, the rest kept whole."""
    text = _CUSTOM_EMOJI.sub("", _text(line))
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\\([\\*_~`|>()\[\].-])", r"\1", text)  # Discord's markdown escapes
    return re.sub(r"[ \t ]+", " ", text).strip()


def owner_from_author(author_text) -> Optional[str]:
    match = _AUTHOR.match(clean_line(author_text))
    return match.group("owner").strip() if match else None


def parse_page_footer(text) -> Optional[Tuple[int, int]]:
    match = _PAGE_FOOTER.search(_text(text))
    if not match:
        return None
    return int(match.group("i")), int(match.group("n"))


def parse_mmi_footer(text) -> Optional[Tuple[str, int, int]]:
    """«Belongs to <user> ~~ 1 / 2655» → (user, 1, 2655)."""
    match = _MMI_FOOTER.search(clean_line(text))
    if not match:
        return None
    return match.group("owner").strip(), int(match.group("i")), int(match.group("n"))


@dataclass(frozen=True)
class RankedCharacter:
    rank: int
    name: str
    value: int


@dataclass(frozen=True)
class HaremPage:
    kind: str
    owner: Optional[str]
    page: int
    pages: int  # for $mmi: the number of characters
    names: Tuple[str, ...] = ()
    ranked: Tuple[RankedCharacter, ...] = ()
    total_value: Optional[int] = None
    card_value: Optional[int] = None
    message_id: object = None
    channel_id: object = None

    @property
    def character_total(self) -> Optional[int]:
        return self.pages if self.kind == LIST_MMI else None


def _parts(message_or_embed):
    embed = first_embed(message_or_embed) if _get(message_or_embed, "embeds") is not None else message_or_embed
    if embed is None:
        return None
    author = _get(embed, "author")
    footer = _get(embed, "footer")
    return {
        "author": _text(_get(author, "name") if author is not None else ""),
        "title": _text(_get(embed, "title")),
        "description": _text(_get(embed, "description")),
        "footer": _text(_get(footer, "text") if footer is not None else ""),
    }


def parse_harem_page(message, kind) -> Optional[HaremPage]:
    """Parse one list page of ``kind``; None when the message is not that list."""
    parts = _parts(message)
    if parts is None:
        return None
    message_id = _get(message, "id")
    channel = _get(message, "channel")
    channel_id = _get(channel, "id") if channel is not None else _get(message, "channel_id")
    if kind == LIST_MMI:
        footer = parse_mmi_footer(parts["footer"])
        if footer is None:
            return None
        owner, index, total = footer
        value = None
        for line in parts["description"].splitlines():
            match = _CARD_VALUE.search(line)
            if match and "·" in line:
                value = parse_amount(match.group("num"))
                break
        name = clean_line(parts["title"])
        return HaremPage(kind, owner, index, total, names=(name,) if name else (), card_value=value,
                         message_id=message_id, channel_id=channel_id)

    footer = parse_page_footer(parts["footer"])
    owner = owner_from_author(parts["author"])
    if footer is None or owner is None:
        return None
    page, pages = footer
    lines = [clean_line(line) for line in parts["description"].splitlines()]
    if kind == LIST_MMRK:
        total = None
        ranked = []
        for raw, line in zip(parts["description"].splitlines(), lines):
            value_match = _TOTAL_VALUE.search(clean_line(raw.replace("**", "")))
            if value_match:
                total = parse_amount(value_match.group("num"))
                continue
            match = _RANK_LINE.match(line)
            if match:
                ranked.append(RankedCharacter(int(match.group("rank")), match.group("name").strip(),
                                              parse_amount(match.group("num")) or 0))
        if total is None and not ranked:
            return None
        return HaremPage(kind, owner, page, pages, names=tuple(item.name for item in ranked),
                         ranked=tuple(ranked), total_value=total, message_id=message_id, channel_id=channel_id)
    names = tuple(line for line in lines if line and not _HEADER_LINE.match(line))
    return HaremPage(kind, owner, page, pages, names=names, message_id=message_id, channel_id=channel_id)


def owner_matches(owner, own_names) -> bool:
    folded = clean_line(owner).casefold()
    return bool(folded) and any(folded == clean_line(name).casefold() for name in own_names or () if name)


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------

def _is_select(component) -> bool:
    return _get(component, "options") is not None or _text(_get(component, "type")).casefold().endswith(
        ("select", "string_select", "select_menu"))


def list_components(message):
    """Every component of every action row (buttons and select menus)."""
    found = []
    for row in _get(message, "components") or ():
        children = _get(row, "children")
        if children is None:
            found.append(row)  # a flat component list
        else:
            found.extend(children)
    return found


def list_buttons(message):
    return [item for item in list_components(message) if not _is_select(item)]


def _mark_text(button):
    emoji = _get(button, "emoji")
    name = _get(emoji, "name") if emoji is not None else ""
    return "{} {} {}".format(_text(name), _text(_get(button, "label")), _text(_get(button, "custom_id"))).casefold()


def _direction(button) -> Optional[str]:
    marks = _mark_text(button)
    found = {direction for direction, words in PAGER_MARKS.items() if any(word in marks for word in words)}
    return found.pop() if len(found) == 1 else None


def _is_disabled(button) -> bool:
    return bool(_get(button, "disabled", False))


@dataclass
class PagerLayout:
    previous: object = None
    next: object = None
    rule: str = "none"
    buttons: int = 0
    selects: int = 0

    @property
    def next_disabled(self) -> bool:
        return self.next is not None and _is_disabled(self.next)

    @property
    def previous_disabled(self) -> bool:
        return self.previous is not None and _is_disabled(self.previous)


def analyze_pager(message) -> PagerLayout:
    """Which buttons turn the pages (disabled ones are returned, flagged)."""
    components = list_components(message)
    selects = sum(1 for item in components if _is_select(item))
    buttons = [item for item in components if not _is_select(item)]
    layout = PagerLayout(buttons=len(buttons), selects=selects)
    if len(buttons) == 4:
        low, high = PAGER_POSITIONS[4]
        layout.previous, layout.next, layout.rule = buttons[low], buttons[high], "4 buttons: the two middle ones"
        return layout
    for button in buttons:
        direction = _direction(button)
        if direction == "next" and layout.next is None:
            layout.next = button
        elif direction == "previous" and layout.previous is None:
            layout.previous = button
    if layout.next is not None or layout.previous is not None:
        layout.rule = "arrow/label/custom_id marks"
        return layout
    if len(buttons) in PAGER_POSITIONS:
        low, high = PAGER_POSITIONS[len(buttons)]
        layout.previous, layout.next, layout.rule = buttons[low], buttons[high], "{} buttons: first = previous, last = next".format(len(buttons))
    return layout


def pager_buttons(message):
    """(previous, next) ENABLED buttons of a list message; either may be None."""
    layout = analyze_pager(message)
    return (None if layout.previous is None or _is_disabled(layout.previous) else layout.previous,
            None if layout.next is None or _is_disabled(layout.next) else layout.next)


def describe_components(message) -> str:
    """What a list message holds, for the log: rows/buttons with label, emoji NAME, short custom_id, disabled."""
    rows = _get(message, "components") or ()
    parts = []
    for item in list_components(message):
        if _is_select(item):
            parts.append("select-menu({} option(s))".format(len(_get(item, "options") or ())))
            continue
        emoji = _get(item, "emoji")
        custom = _text(_get(item, "custom_id"))
        if len(custom) > 24:
            custom = custom[:10] + "…" + custom[-8:]
        parts.append("[label={!r} emoji={!r} custom_id={!r} disabled={}]".format(
            _text(_get(item, "label")), _text(_get(emoji, "name")) if emoji is not None else "", custom,
            _is_disabled(item)))
    return "{} row(s): {}".format(len(rows), " ".join(parts) if parts else "no buttons")


def describe_page(page, message=None) -> str:
    footer = ""
    if message is not None:
        embed = first_embed(message)
        foot = _get(embed, "footer") if embed is not None else None
        footer = _text(_get(foot, "text") if foot is not None else "")
    if page is None:
        return "not a list page; footer {!r}".format(footer)
    return "page {}/{}, {} name(s), footer {!r}".format(page.page, page.pages, len(page.names), footer)


# ---------------------------------------------------------------------------
# Reader + pager
# ---------------------------------------------------------------------------

@dataclass
class ListRead:
    status: str  # "ok" or "failed"
    reason: str = ""
    page: Optional[HaremPage] = None
    pager: Optional["HaremPager"] = None
    pages: List[HaremPage] = field(default_factory=list)


def _snowflake_after(message_id, sent_id) -> bool:
    if isinstance(message_id, int) and isinstance(sent_id, int):
        return message_id > sent_id
    return True


class HaremPager:
    """Turns the pages of one list message by clicking its buttons."""

    def __init__(self, reader, message, page: HaremPage):
        self._reader = reader
        self.message = message
        self.current = page

    @property
    def message_id(self):
        return self.current.message_id

    async def next(self) -> Optional[HaremPage]:
        if self.current.page >= self.current.pages:
            return None
        return await self._turn(+1)

    async def previous(self) -> Optional[HaremPage]:
        if self.current.page <= 1:
            return None
        return await self._turn(-1)

    async def _turn(self, step) -> Optional[HaremPage]:
        """Click once; retry once after a short delay; never loop. None: stop turning (see ``reader.last_error``)."""
        reader = self._reader
        want = self.current.page + step
        direction = "next" if step > 0 else "previous"
        seen = ""
        for attempt in (1, 2):
            layout = analyze_pager(self.message)
            if attempt == 1:
                reader.note("{}: turning to page {} — {}; {}; rule: {}".format(
                    reader.tag(self.current.kind), want, describe_components(self.message),
                    describe_page(self.current, self.message), layout.rule))
            button = layout.next if step > 0 else layout.previous
            if button is None:
                if layout.selects and not layout.buttons:
                    reader.fail(self.current.kind, "the list has a select menu and no buttons (cannot turn pages)",
                                describe_components(self.message))
                else:
                    reader.fail(self.current.kind, "the list has no {} button".format(direction),
                                describe_components(self.message))
                return None
            if _is_disabled(button):
                # The last/first page: a clean stop, not a failure.
                reader.last_error = ""
                reader.note("{}: the {} button is disabled; stopping at page {}.".format(
                    reader.tag(self.current.kind), direction, self.current.page))
                return None
            low, high = reader.click_delay if attempt == 1 else reader.retry_delay
            if not await reader._wait(random.uniform(low, high)):
                reader.last_error = "paused or stopping"
                return None
            page, seen = await self._click_and_wait(button, want)
            if page is not None:
                return page
            if reader.last_error == "paused or stopping" or reader.hard_stop:
                return None
            if attempt == 1:
                reader.note("{}: page {} not shown ({}); trying the click once more.".format(
                    reader.tag(self.current.kind), want, seen))
        reader.fail(self.current.kind, "page {} did not appear after two clicks".format(want), seen)
        return None

    async def _click_and_wait(self, button, want):
        """Click and wait for page ``want`` (same message edited, or a new list message of this account)."""
        reader = self._reader
        reader.hard_stop = False
        watched_id = self.message_id
        queue = reader._watch(watched_id)
        replacement = reader._watch_replacement(self.current.channel_id, watched_id)
        seen = "nothing arrived"
        try:
            if not await reader._click(button):
                reader.hard_stop = True
                reader.fail(self.current.kind, "the {} button could not be clicked".format(
                    "next" if want > self.current.page else "previous"), describe_components(self.message))
                return None, "click failed"
            deadline = reader._monotonic() + reader.edit_timeout
            while True:
                remaining = deadline - reader._monotonic()
                if remaining <= 0:
                    return None, "no matching edit in {:.0f} s; last seen: {}".format(reader.edit_timeout, seen)
                incoming = None
                for source in (queue, replacement):
                    if not source.empty():
                        incoming = source.get_nowait()
                        break
                if incoming is None:
                    try:
                        incoming = await asyncio.wait_for(queue.get(), timeout=min(remaining, 0.25))
                    except asyncio.TimeoutError:
                        continue
                page = parse_harem_page(incoming, self.current.kind)
                if page is not None and page.owner is not None and reader.own_names \
                        and not owner_matches(page.owner, reader.own_names):
                    continue  # another user's list
                seen = describe_page(page, incoming)
                if page is None or page.page == self.current.page:
                    continue  # the loading state, or an edit that did not turn the page
                if page.page != want:
                    reader.hard_stop = True
                    reader.fail(self.current.kind, "the list jumped to page {} instead of {}".format(page.page, want), seen)
                    return None, seen
                reader.note("{}: now on {}.".format(reader.tag(self.current.kind), seen))
                self.message = incoming
                self.current = page
                return page, seen
        finally:
            reader._unwatch(watched_id, queue)
            reader._unwatch_replacement(replacement)

    async def collect(self, max_pages) -> List[HaremPage]:
        """This page and the following ones, up to ``max_pages`` pages in all."""
        pages = [self.current]
        while len(pages) < max(1, int(max_pages)):
            page = await self.next()
            if page is None:
                break
            pages.append(page)
        return pages


class HaremListReader:
    """One per account.

    ``send(channel, text)`` returns the sent message (or None/False);
    ``click(button)`` returns truthy when the click went out; ``wait(seconds)``
    is the bot's interruptible delay (False when paused/stopping).
    """

    def __init__(self, *, send, click, wait, log: Callable = lambda message, level: None,
                 monotonic=time.monotonic, reply_timeout=REPLY_TIMEOUT_SECONDS,
                 edit_timeout=EDIT_TIMEOUT_SECONDS, click_delay=CLICK_DELAY_SECONDS,
                 retry_delay=RETRY_DELAY_SECONDS):
        self._send = send
        self._click = click
        self._wait = wait
        self._log = log
        self._monotonic = monotonic
        self.reply_timeout = reply_timeout
        self.edit_timeout = edit_timeout
        self.click_delay = click_delay
        self.retry_delay = retry_delay
        self.last_error = ""
        self.hard_stop = False
        self.own_names: Tuple[str, ...] = ()
        self._pending = None  # (channel_id, sent_id, queue)
        self._watchers = {}
        self._replacements = []  # (channel_id, after_id, queue): a new list message instead of an edit

    # -- diagnostics -----------------------------------------------------
    @staticmethod
    def tag(kind) -> str:
        """The log label; «Perk 10» makes the $mmz- lines show under the PERK kind."""
        return "Perk 10 list (${})".format(kind) if kind == LIST_MMZ else "Harem list (${})".format(kind)

    def note(self, message):
        try:
            self._log(message, "INFO")
        except Exception:
            pass

    def fail(self, kind, reason, seen=""):
        self.last_error = reason
        try:
            self._log("could not turn the ${} page: {}{}".format(kind, reason, "; seen: {}".format(seen) if seen else ""),
                      "ERROR")
        except Exception:
            pass

    # -- feeding events --------------------------------------------------
    @property
    def active(self) -> bool:
        return self._pending is not None or bool(self._watchers) or bool(self._replacements)

    def watching(self, message_id) -> bool:
        return message_id in self._watchers

    def on_message(self, message):
        channel = _get(message, "channel")
        channel_id = _get(channel, "id") if channel is not None else _get(message, "channel_id")
        for target, after_id, queue in list(self._replacements):
            if channel_id == target and _snowflake_after(_get(message, "id"), after_id):
                queue.put_nowait(message)
        pending = self._pending
        if pending is None:
            return
        if channel_id != pending[0]:
            return
        pending[2].put_nowait(message)

    def _watch_replacement(self, channel_id, after_id):
        queue = asyncio.Queue()
        self._replacements.append((channel_id, after_id, queue))
        return queue

    def _unwatch_replacement(self, queue):
        self._replacements = [item for item in self._replacements if item[2] is not queue]

    def on_edit(self, message):
        for queue in self._watchers.get(_get(message, "id"), ()):
            queue.put_nowait(message)

    def _watch(self, message_id):
        queue = asyncio.Queue()
        self._watchers.setdefault(message_id, []).append(queue)
        return queue

    def _unwatch(self, message_id, queue):
        queues = self._watchers.get(message_id)
        if queues and queue in queues:
            queues.remove(queue)
            if not queues:
                self._watchers.pop(message_id, None)

    # -- reading ---------------------------------------------------------
    async def open(self, channel, kind, own_names, *, prefix="$") -> ListRead:
        """Send ``$<kind>`` and return its first page with a pager."""
        if kind not in LIST_KINDS:
            return ListRead("failed", "unknown list {}".format(kind))
        if self._pending is not None:
            return ListRead("failed", "another list is being read")
        channel_id = _get(channel, "id")
        self.own_names = tuple(str(name) for name in own_names or () if name)
        queue = asyncio.Queue()
        self._pending = (channel_id, None, queue)
        try:
            receipt = await self._send(channel, "{}{}".format(prefix or "$", kind))
            if not receipt:
                return ListRead("failed", "the ${} command could not be sent".format(kind))
            sent_id = _get(receipt, "id")
            self._pending = (channel_id, sent_id, queue)
            deadline = self._monotonic() + self.reply_timeout
            while True:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    return ListRead("failed", "no ${} list of this account arrived in time".format(kind))
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=min(remaining, 0.5))
                except asyncio.TimeoutError:
                    continue
                if not _snowflake_after(_get(message, "id"), sent_id):
                    continue
                reference = _get(message, "reference")
                replied_to = _get(reference, "message_id") if reference is not None else None
                if replied_to is not None and sent_id is not None and replied_to != sent_id:
                    continue  # answers someone else's command
                page = parse_harem_page(message, kind)
                if page is None:
                    continue
                if not owner_matches(page.owner, own_names):
                    continue  # another user's list in the channel
                layout = analyze_pager(message)
                self.note("{}: opened — {}; {}; rule: {}{}".format(
                    self.tag(kind), describe_components(message), describe_page(page, message), layout.rule,
                    "; single page" if page.pages <= 1 else ""))
                return ListRead("ok", page=page, pager=HaremPager(self, message, page), pages=[page])
        finally:
            self._pending = None

    async def read(self, channel, kind, own_names, *, prefix="$", max_pages=1) -> ListRead:
        """Open ``$<kind>`` and collect up to ``max_pages`` pages."""
        result = await self.open(channel, kind, own_names, prefix=prefix)
        if result.status != "ok" or max_pages <= 1:
            return result
        self.last_error = ""
        result.pages = await result.pager.collect(max_pages)
        if len(result.pages) < min(max_pages, result.page.pages) and self.last_error:
            result.reason = self.last_error
        return result
