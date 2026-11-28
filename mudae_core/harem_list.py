"""Read this account's own ``$mmz-`` list (the characters without the perk-10 upgrade).

Pure parsing plus a small pager; nothing here imports discord. Messages are
read duck-typed (``id``, ``channel.id``/``channel_id``, ``embeds``,
``components``, ``reference``), so the bot passes its message objects as-is and
the tests pass simple stand-ins.

Shape: an embed with author «<user>'s harem», one NAME per description line
and footer «Page i / N». Pages are turned with the BUTTONS under the list; the
bot then EDITS the same message in place. The pager clicks through an injected
``click(button)`` (the bot's ``guarded_click``) and waits for the edit of that
message id, fed through ``on_edit``; it never sends a new command per page.

Only a list whose owner is THIS account and that answers THIS account's own
command (same channel, after the command, in the time window, replying to it
when Discord says what it replies to) is accepted; another user's list is
ignored.
"""

import asyncio
import random
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

LIST_COMMAND = "mmz-"

REPLY_TIMEOUT_SECONDS = 15.0
EDIT_TIMEOUT_SECONDS = 10.0
CLICK_DELAY_SECONDS = (0.9, 1.8)
RETRY_DELAY_SECONDS = (1.5, 3.0)

_CUSTOM_EMOJI = re.compile(r"<a?:[A-Za-z0-9_~]+:\d+>")
_PAGE_FOOTER = re.compile(r"(?:page|p[aá]gina|seite)\s*(?P<i>\d+)\s*/\s*(?P<n>\d+)", re.IGNORECASE)
_AUTHOR = re.compile(r"^(?P<owner>.+?)(?:'|’)s\s+harem\b", re.IGNORECASE)
_HEADER_LINE = re.compile(r"^(?:avg|average|top\s*\d+\s*value|total value)\s*:", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Decision table for the page buttons (data: correct it here when the game bot differs)
# ---------------------------------------------------------------------------
# A button is «previous»/«next» when any mark below is found in its emoji name
# (a unicode emoji's name is the character itself), its label or its
# custom_id (case-folded). A button matching both directions is not used.
PAGER_MARKS = {
    "previous": ("⬅", "◀", "⏪", "arrow_backward", "arrow_left", "left", "previous", "prev", "back"),
    "next": ("➡", "▶", "⏩", "arrow_forward", "arrow_right", "right", "next", "forward"),
}
# When the marks are not enough: layout by the number of buttons in all rows
# → (index of previous, index of next). The live $mmz- list shows two buttons
# whose faces are custom character emojis (no arrows, no labels).
PAGER_POSITIONS = {
    2: (0, 1),  # previous, next
    4: (1, 2),  # first, previous, next, last: the two middle ones
}

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


# Characters that print as nothing (zero-width, directional marks, Braille blank, Hangul fillers, ...).
_BLANK_CHARS = {"⠀", "ㅤ", "ᅟ", "ᅠ", "ﾠ", "᠎", "͏"}


def is_invisible_char(ch) -> bool:
    return ch in _BLANK_CHARS or unicodedata.category(ch) in ("Cf", "Cc", "Cs", "Co", "Cn", "Zs", "Zl", "Zp")


def strip_invisible(text) -> str:
    """Whitespace and invisible characters removed from both ends (a line of only those becomes empty)."""
    text = str(text or "")
    start, end = 0, len(text)
    while start < end and is_invisible_char(text[start]):
        start += 1
    while end > start and is_invisible_char(text[end - 1]):
        end -= 1
    return text[start:end]


def has_visible_text(text) -> bool:
    """True when the text holds at least one letter or digit (a name that prints as nothing is not a name)."""
    return any(unicodedata.category(ch)[0] in ("L", "N") for ch in str(text or "") if not is_invisible_char(ch))


def clean_line(line) -> str:
    """A printed line: custom-emoji tokens and markdown wrappers removed, the rest kept whole."""
    text = _CUSTOM_EMOJI.sub("", _text(line))
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\\([\\*_~`|>()\[\].-])", r"\1", text)  # Discord's markdown escapes
    return strip_invisible(re.sub(r"[ \t ]+", " ", text))


def owner_from_author(author_text) -> Optional[str]:
    match = _AUTHOR.match(clean_line(author_text))
    return match.group("owner").strip() if match else None


def parse_page_footer(text) -> Optional[Tuple[int, int]]:
    match = _PAGE_FOOTER.search(_text(text))
    if not match:
        return None
    return int(match.group("i")), int(match.group("n"))


@dataclass(frozen=True)
class HaremPage:
    owner: Optional[str]
    page: int
    pages: int
    names: Tuple[str, ...] = ()
    message_id: object = None
    channel_id: object = None


def parse_harem_page(message) -> Optional[HaremPage]:
    """Parse one list page; None when the message is not a harem list page."""
    embed = first_embed(message)
    if embed is None:
        return None
    author = _get(embed, "author")
    footer = _get(embed, "footer")
    pages = parse_page_footer(_get(footer, "text") if footer is not None else "")
    owner = owner_from_author(_get(author, "name") if author is not None else "")
    if pages is None or owner is None:
        return None
    channel = _get(message, "channel")
    channel_id = _get(channel, "id") if channel is not None else _get(message, "channel_id")
    lines = [clean_line(line) for line in _text(_get(embed, "description")).splitlines()]
    names = tuple(line for line in lines if line and has_visible_text(line) and not _HEADER_LINE.match(line))
    return HaremPage(owner, pages[0], pages[1], names=names, message_id=_get(message, "id"), channel_id=channel_id)


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


def analyze_pager(message) -> PagerLayout:
    """Which buttons turn the pages (disabled ones are returned, flagged).

    Rules in order: 4 buttons → the two middle ones; else arrow/label/custom_id
    marks; else 2 buttons → first = previous, last = next.
    """
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
        layout.previous, layout.next = buttons[low], buttons[high]
        layout.rule = "{} buttons: first = previous, last = next".format(len(buttons))
    return layout


def describe_components(message) -> str:
    """What a list message holds, for the log: buttons with label, emoji NAME, short custom_id, disabled."""
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


def _snowflake_after(message_id, sent_id) -> bool:
    if isinstance(message_id, int) and isinstance(sent_id, int):
        return message_id > sent_id
    return True


class HaremPager:
    """Turns the pages of one list message by clicking its «next» button."""

    def __init__(self, reader, message, page: HaremPage):
        self._reader = reader
        self.message = message
        self.current = page

    @property
    def message_id(self):
        return self.current.message_id

    async def next(self) -> Optional[HaremPage]:
        """Click once; retry once after a short delay; never loop. None: stop (see ``reader.last_error``)."""
        reader = self._reader
        if self.current.page >= self.current.pages:
            return None
        want = self.current.page + 1
        seen = ""
        for attempt in (1, 2):
            layout = analyze_pager(self.message)
            if attempt == 1:
                reader.note("{}: turning to page {} — {}; {}; rule: {}".format(
                    reader.TAG, want, describe_components(self.message),
                    describe_page(self.current, self.message), layout.rule))
            button = layout.next
            if button is None:
                if layout.selects and not layout.buttons:
                    reader.fail("the list has a select menu and no buttons (cannot turn pages)",
                                describe_components(self.message))
                else:
                    reader.fail("the list has no next button", describe_components(self.message))
                return None
            if _is_disabled(button):
                # The last page: a clean stop, not a failure.
                reader.last_error = ""
                reader.note("{}: the next button is disabled; stopping at page {}.".format(
                    reader.TAG, self.current.page))
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
                reader.note("{}: page {} not shown ({}); trying the click once more.".format(reader.TAG, want, seen))
        reader.fail("page {} did not appear after two clicks".format(want), seen)
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
                reader.fail("the next button could not be clicked", describe_components(self.message))
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
                page = parse_harem_page(incoming)
                if page is not None and reader.own_names and not owner_matches(page.owner, reader.own_names):
                    continue  # another user's list
                seen = describe_page(page, incoming)
                if page is None or page.page == self.current.page:
                    continue  # the loading state, or an edit that did not turn the page
                if page.page != want:
                    reader.hard_stop = True
                    reader.fail("the list jumped to page {} instead of {}".format(page.page, want), seen)
                    return None, seen
                reader.note("{}: now on {}.".format(reader.TAG, seen))
                self.message = incoming
                self.current = page
                return page, seen
        finally:
            reader._unwatch(watched_id, queue)
            reader._unwatch_replacement(replacement)


class HaremListReader:
    """One per account.

    ``send(channel, text)`` returns the sent message (or None/False);
    ``click(button)`` returns truthy when the click went out; ``wait(seconds)``
    is the bot's interruptible delay (False when paused/stopping).
    """

    TAG = "Perk 10 list ($mmz-)"

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
    def note(self, message):
        try:
            self._log(message, "INFO")
        except Exception:
            pass

    def fail(self, reason, seen=""):
        self.last_error = reason
        try:
            self._log("could not turn the ${} page: {}{}".format(
                LIST_COMMAND, reason, "; seen: {}".format(seen) if seen else ""), "ERROR")
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
        if pending is None or channel_id != pending[0]:
            return
        pending[2].put_nowait(message)

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

    def _watch_replacement(self, channel_id, after_id):
        queue = asyncio.Queue()
        self._replacements.append((channel_id, after_id, queue))
        return queue

    def _unwatch_replacement(self, queue):
        self._replacements = [item for item in self._replacements if item[2] is not queue]

    # -- reading ---------------------------------------------------------
    async def open(self, channel, own_names, *, prefix="$") -> ListRead:
        """Send ``$mmz-`` and return its first page with a pager."""
        if self._pending is not None:
            return ListRead("failed", "another list is being read")
        channel_id = _get(channel, "id")
        self.own_names = tuple(str(name) for name in own_names or () if name)
        queue = asyncio.Queue()
        self._pending = (channel_id, None, queue)
        try:
            receipt = await self._send(channel, "{}{}".format(prefix or "$", LIST_COMMAND))
            if not receipt:
                return ListRead("failed", "the ${} command could not be sent".format(LIST_COMMAND))
            sent_id = _get(receipt, "id")
            self._pending = (channel_id, sent_id, queue)
            deadline = self._monotonic() + self.reply_timeout
            while True:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    return ListRead("failed", "no ${} list of this account arrived in time".format(LIST_COMMAND))
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
                page = parse_harem_page(message)
                if page is None or not owner_matches(page.owner, own_names):
                    continue  # not a list, or another user's list in the channel
                self.note("{}: opened — {}; {}; rule: {}{}".format(
                    self.TAG, describe_components(message), describe_page(page, message),
                    analyze_pager(message).rule, "; single page" if page.pages <= 1 else ""))
                return ListRead("ok", page=page, pager=HaremPager(self, message, page))
        finally:
            self._pending = None
