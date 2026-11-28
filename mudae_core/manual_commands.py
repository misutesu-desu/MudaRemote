"""Notice what the player does by hand with a running account.

Every text message the app sends goes through one helper (``guarded_send``),
which records it here first (``AppSendLedger.expect``) and then its id
(``confirm``). A message of the account's own Discord user in a watched
channel that matches no such record was typed by the player.

- ``classify_command`` names the command (``$tu``, a roll, ``$givek``, …).
- ``ManualCommandWatch`` keeps one manual command «in flight» from the
  player's message until the game bot's next reply in that channel or
  ``BUSY_SECONDS``; while it is in flight the app's conversational features
  (gives, perk 10, harem give, fast setup) treat the account as busy, so their
  questions and answers never interleave with the player's.
- A bare ``y``/``n`` (or ``yes``/``no``/``cancel``/``$exit``) is an answer:
  if the app asked a question, the app's flow stops cleanly (it was answered
  by the player) and sends nothing more for it.

The app only reads: it never repeats, completes or reacts to a manual
command, and never sends ``$tu`` because of one. Pure logic (no Discord);
``mudae_bot.py`` wires it.
"""

import re
import threading
import time
from collections import OrderedDict

BUSY_SECONDS = 8.0
# How long a recorded app send waits for its own message to come back.
APP_SEND_MATCH_SECONDS = 20.0

TU = "tu"
ROLL = "roll"
RT = "rt"
GIVEK = "givek"
GIVESP = "givesp"
GIVE = "give"
OI = "oi"
OIC = "oic"
SPHERE_GAME = "sphere game"
DK = "dk"
DAILY = "daily"
US = "us"
MK = "mk"
ANSWER = "answer"
OTHER = "other"

ROLL_COMMANDS = ("w", "h", "m", "wx", "mx", "hx", "wa", "ha", "ma", "wg", "hg", "mg", "rolls")
SPHERE_GAMES = ("oh", "oc", "oq", "ot")
ANSWERS = ("y", "n", "yes", "no", "cancel")
# Spheres change after these (spent or won): the stock is unknown until the next $tu.
SPHERE_CHANGING = (GIVESP, OI, OIC, SPHERE_GAME)
# Kakera changes after these.
KAKERA_CHANGING = (GIVEK,)

_MENTION_RE = re.compile(r"<@!?(\d+)>")


def normalize(text):
    return " ".join(str(text or "").split()).casefold()


def classify_command(content, prefix="$", roll_command="", extra_tu_aliases=()):
    """``(kind, word)`` of a message the player typed, or ``(None, "")`` when it is chat."""
    text = normalize(content)
    if not text:
        return None, ""
    if text in ANSWERS or text == "{}exit".format(normalize(prefix) or "$"):
        return ANSWER, text
    prefix = normalize(prefix) or "$"
    if not text.startswith(prefix):
        return None, ""
    body = text[len(prefix):].strip()
    if not body:
        return None, ""
    word = body.split(" ", 1)[0]
    if word == "exit":
        return ANSWER, "$exit"
    if word in ("tu",) or word in {normalize(alias) for alias in extra_tu_aliases if alias}:
        return TU, word
    rolls = set(ROLL_COMMANDS)
    if roll_command:
        rolls.add(normalize(roll_command))
    if word in rolls:
        return ROLL, word
    if word in SPHERE_GAMES:
        return SPHERE_GAME, word
    known = {"rt": RT, "givek": GIVEK, "givesp": GIVESP, "give": GIVE, "oi": OI, "oic": OIC,
             "dk": DK, "daily": DAILY, "us": US, "mk": MK}
    if word in known:
        return known[word], word
    return OTHER, word


def mentioned_ids(content):
    return [match.group(1) for match in _MENTION_RE.finditer(str(content or ""))]


_MARRIED_RE = re.compile(
    r"^\W*(?P<owner>[^\n]+?)\W*\s+and\s+\W*(?P<card>[^\n]+?)\W*\s+are now married", re.IGNORECASE)


def _plain(value):
    return re.sub(r"[*_~`]", "", str(value or "")).strip()


def parse_marriage(text):
    """``(owner, character)`` from «**user** and **Character** are now married!», else None."""
    for line in str(text or "").splitlines():
        match = _MARRIED_RE.search(_plain(line))
        if match:
            return match.group("owner").strip(" ,!:"), match.group("card").strip(" ,!:")
    return None


class AppSendLedger:
    """What the app itself sent, so the player's own messages can be told apart."""

    def __init__(self, *, monotonic=time.monotonic, limit=200):
        self._lock = threading.Lock()
        self._monotonic = monotonic
        self._pending = OrderedDict()   # token -> (channel_id, text, at)
        self._ids = OrderedDict()       # message id -> at
        self._next = 0
        self._limit = max(10, int(limit))

    def expect(self, channel_id, content):
        with self._lock:
            self._next += 1
            token = self._next
            self._pending[token] = (channel_id, normalize(content), self._monotonic())
            while len(self._pending) > self._limit:
                self._pending.popitem(last=False)
            return token

    def confirm(self, token, message_id):
        with self._lock:
            entry = self._pending.pop(token, None)
            if message_id is not None:
                self._ids[message_id] = self._monotonic()
                while len(self._ids) > self._limit:
                    self._ids.popitem(last=False)
            return entry is not None

    def cancel(self, token):
        with self._lock:
            self._pending.pop(token, None)

    def is_app_message(self, message_id, channel_id, content):
        """True when the app sent this message (its id, or a matching send still in flight)."""
        with self._lock:
            if message_id is not None and message_id in self._ids:
                return True
            now = self._monotonic()
            text = normalize(content)
            for token, (channel, expected, at) in list(self._pending.items()):
                if now - at > APP_SEND_MATCH_SECONDS:
                    self._pending.pop(token, None)
                    continue
                if channel == channel_id and expected == text:
                    # The gateway can deliver our own message before send() returns its id.
                    self._pending.pop(token, None)
                    if message_id is not None:
                        self._ids[message_id] = now
                    return True
            return False


class ManualCommand:
    __slots__ = ("kind", "word", "channel_id", "message_id", "started", "replied", "content")

    def __init__(self, kind, word, channel_id, message_id, started, content=""):
        self.kind = kind
        self.word = word
        self.channel_id = channel_id
        self.message_id = message_id
        self.started = started
        self.replied = False
        self.content = content


class ManualCommandWatch:
    """The player's manual command in flight on one account (one at a time: the latest wins)."""

    def __init__(self, *, monotonic=time.monotonic, busy_seconds=BUSY_SECONDS):
        self._lock = threading.Lock()
        self._monotonic = monotonic
        self.busy_seconds = float(busy_seconds)
        self._current = None
        self._tu_waiting = None   # the last manual $tu whose reply has not been read yet

    def begin(self, kind, word, channel_id, message_id, content=""):
        with self._lock:
            command = ManualCommand(kind, word, channel_id, message_id, self._monotonic(), content)
            self._current = command
            if kind == TU:
                self._tu_waiting = command
            return command

    def current(self):
        with self._lock:
            command = self._current
            if command is None:
                return None
            if command.replied or self._monotonic() - command.started >= self.busy_seconds:
                self._current = None
                return None
            return command

    def busy_reason(self):
        command = self.current()
        if command is None:
            return None
        if command.kind == ANSWER:
            return "you answered the game bot yourself"
        return "you are using ${} by hand".format(command.word) if command.word else "you are typing a command"

    def on_bot_reply(self, channel_id):
        """The game bot answered in that channel: the manual command is no longer in flight.

        Returns the command it answered (or None)."""
        with self._lock:
            command = self._current
            if command is None or command.channel_id != channel_id:
                return None
            if self._monotonic() - command.started >= self.busy_seconds:
                self._current = None
                return None
            command.replied = True
            self._current = None
            return command

    def take_tu(self, channel_id, window=30.0):
        """A $tu reply arrived in ``channel_id``: was it for the player's own $tu? (used once)."""
        with self._lock:
            command = self._tu_waiting
            if command is None or command.channel_id != channel_id:
                return False
            if self._monotonic() - command.started > window:
                self._tu_waiting = None
                return False
            self._tu_waiting = None
            return True


def saw_tu_line():
    return "saw your $tu — state refreshed"


def saw_command_line(word, effect=""):
    text = "saw your ${}".format(word)
    return text + (" — " + effect if effect else "")


def answered_line(feature):
    return "you answered the game bot yourself — {} stops here".format(feature)
