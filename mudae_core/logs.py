"""Readable log lines, redaction, daily TXT files and filters (pure logic).

One line shape everywhere::

    YYYY-MM-DD HH:MM:SS | profile name | KIND | message

Nothing here imports discord or tkinter. Tokens and long ids are removed in
``redact_text`` before a line is shown, stored or written; the file writer
never raises and never blocks the bot for more than a small append.
"""

import atexit
import datetime
import os
import re
import threading
import time
from typing import Callable, Iterable, List, NamedTuple, Optional, Sequence

KINDS = (
    "ROLL", "CLAIM", "KAKERA", "GIVE", "PERK", "SIDE", "SETUP", "SPHERE",
    "STATUS", "SYSTEM", "WARN", "ERROR",
)
LINE_SEPARATOR = " | "
SEPARATOR_REPLACEMENT = " / "
MAX_LINE_CHARS = 1200

LOG_DEFAULTS = {
    "save_logs_txt": True,
    "logs_keep_days": 14,
    "logs_max_mb": 50,
}
LOGS_FOLDER_NAME = "logs"
KEEP_DAYS_MAX = 3650
MAX_MB_MAX = 10000

_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (.*?) \| ([A-Z]+) \| (.*)$"
)
_FILE_RE = re.compile(r"^(?P<name>.+)_(?P<day>\d{4}-\d{2}-\d{2})\.txt$")

# ------------------------------------------------------------------ redaction

# Discord tokens: three dot-separated URL-safe parts (also the older mfa. form).
_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:mfa\.[A-Za-z0-9_-]{20,}|[A-Za-z0-9_-]{18,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{20,})(?![A-Za-z0-9_-])"
)
_MENTION_RE = re.compile(r"<(@[!&]?|#)(\d{5,})>")
_LONG_ID_RE = re.compile(r"(?<!\d)(\d{15,22})(?!\d)")
TOKEN_REMOVED = "[token removed]"


def shorten_id(digits) -> str:
    """«…1234»: the last four digits only."""
    text = str(digits)
    return "…" + text[-4:]


def redact_text(text, secrets: Iterable[str] = ()) -> str:
    """Remove tokens, shorten ids and mentions. Safe to run twice."""
    clean = str(text if text is not None else "")
    for secret in sorted({str(s) for s in secrets if s}, key=len, reverse=True):
        if len(secret) >= 6:
            clean = clean.replace(secret, TOKEN_REMOVED)
    clean = _TOKEN_RE.sub(TOKEN_REMOVED, clean)
    clean = _MENTION_RE.sub(lambda m: "<{}{}>".format(m.group(1), shorten_id(m.group(2))), clean)
    clean = _LONG_ID_RE.sub(lambda m: shorten_id(m.group(1)), clean)
    return clean


def single_line(text, limit=MAX_LINE_CHARS) -> str:
    clean = re.sub(r"\s*[\r\n]+\s*", SEPARATOR_REPLACEMENT, str(text or "")).strip()
    if len(clean) > limit:
        clean = clean[: limit - 1].rstrip() + "…"
    return clean


def shorten_reply(text, limit=200) -> str:
    """The game bot's reply, on one line and cut to ``limit`` characters."""
    return single_line(text, limit)


# ------------------------------------------------------------------ classifying

_TOPIC_RULES = (
    ("SETUP", re.compile(r"fast setup|setup command")),
    ("PERK", re.compile(r"\bperk[ -]?(?:10|\d+b?)\b|\bperk\b")),
    ("GIVE", re.compile(r"\bgiv(?:e|es|ing|en)\b|auto-give|\$give\b")),
    ("SIDE", re.compile(r"\bside\b|\balt account|\bmain account sync")),
    ("SPHERE", re.compile(r"sphere|\$oh\b|\$oc\b|\$oq\b|\$ot\b|ourosphere|\bchest\b|harvest")),
)
_KEYWORD_RULES = (
    ("CLAIM", re.compile(r"claim|divorce|snipe|wish|\$rt\b|married|\bmarry")),
    ("KAKERA", re.compile(r"kakera|\$dk\b|\$mk\b")),
    ("ROLL", re.compile(r"\broll|\$us\b|\$rolls\b|\$wa\b|\$ma\b|\$mg\b|key mode|panic")),
    ("STATUS", re.compile(r"\$tu\b|status|cooldown|reset|available|ready|totals")),
)
_LEVEL_KIND = {"CLAIM": "CLAIM", "KAKERA": "KAKERA", "CHECK": "STATUS", "RESET": "STATUS"}


def classify_kind(message, level="INFO") -> str:
    """The line's KIND from the old level and the wording (no call site changes)."""
    level = str(level or "INFO").upper()
    text = str(message or "")
    lowered = text.casefold()
    if level == "ERROR":
        return "ERROR"
    for kind, pattern in _TOPIC_RULES:
        if pattern.search(lowered):
            # A refusal carrying the game bot's reply is an error to read.
            if level == "WARN" and "bot said:" in lowered:
                return "ERROR"
            return kind
    if level == "WARN" and "bot said:" in lowered:
        return "ERROR"
    if level in _LEVEL_KIND:
        return _LEVEL_KIND[level]
    for kind, pattern in _KEYWORD_RULES:
        if pattern.search(lowered):
            return kind
    return "WARN" if level == "WARN" else "SYSTEM"


# ------------------------------------------------------------------ format and parse

class LogEntry(NamedTuple):
    stamp: str
    profile: str
    kind: str
    message: str


def clean_profile(name) -> str:
    text = single_line(name, 60).replace("|", "/").strip()
    return text or "MudaRemote"


def format_line(when, profile, kind, message) -> str:
    """``when`` is a datetime or an already formatted stamp."""
    stamp = when.strftime("%Y-%m-%d %H:%M:%S") if hasattr(when, "strftime") else str(when)
    kind = str(kind or "SYSTEM").upper()
    body = single_line(message).replace(" | ", SEPARATOR_REPLACEMENT)
    return LINE_SEPARATOR.join((stamp, clean_profile(profile), kind, body))


def build_line(when, profile, level, message, secrets: Iterable[str] = ()) -> str:
    """Redact, classify and format in one step (what the logger calls)."""
    safe_message = redact_text(message, secrets)
    safe_profile = redact_text(profile, secrets)
    return format_line(when, safe_profile, classify_kind(safe_message, level), safe_message)


def parse_line(line) -> Optional[LogEntry]:
    match = _LINE_RE.match(str(line or "").rstrip("\r\n"))
    if not match:
        return None
    return LogEntry(*match.groups())


# ------------------------------------------------------------------ filtering

def filter_lines(lines: Iterable[str], profile=None, kind=None, search="", errors_only=False) -> List[str]:
    """Keep the lines that match every given filter (empty filter = no filter).

    ``profile`` and ``kind`` compare whole values, case-insensitively; the
    search text is a case-insensitive substring of the whole line. A line that
    does not parse is kept only when no profile/kind filter is set.
    """
    wanted_profile = str(profile or "").strip().casefold()
    wanted_kind = str(kind or "").strip().upper()
    if wanted_kind in ("ALL", "*"):
        wanted_kind = ""
    needle = str(search or "").strip().casefold()
    result = []
    for line in lines:
        entry = parse_line(line)
        if entry is None:
            if wanted_profile or wanted_kind or errors_only:
                continue
        else:
            if wanted_profile and entry.profile.casefold() != wanted_profile:
                continue
            if errors_only and entry.kind != "ERROR":
                continue
            if wanted_kind and entry.kind != wanted_kind:
                continue
        if needle and needle not in str(line).casefold():
            continue
        result.append(str(line).rstrip("\r\n"))
    return result


def profiles_in(lines: Iterable[str]) -> List[str]:
    seen = {}
    for line in lines:
        entry = parse_line(line)
        if entry:
            seen.setdefault(entry.profile.casefold(), entry.profile)
    return sorted(seen.values(), key=str.casefold)


# ------------------------------------------------------------------ settings

class LogSettings(NamedTuple):
    enabled: bool
    keep_days: int
    max_mb: int

    @classmethod
    def from_data(cls, data) -> "LogSettings":
        data = data or {}

        def whole(key, minimum, maximum):
            try:
                value = int(float(str(data.get(key, LOG_DEFAULTS[key])).strip()))
            except (TypeError, ValueError):
                value = LOG_DEFAULTS[key]
            return max(minimum, min(maximum, value))

        raw = data.get("save_logs_txt", LOG_DEFAULTS["save_logs_txt"])
        enabled = raw if isinstance(raw, bool) else str(raw).strip().casefold() not in ("false", "0", "no", "off", "")
        return cls(enabled, whole("logs_keep_days", 1, KEEP_DAYS_MAX), whole("logs_max_mb", 1, MAX_MB_MAX))


def validate_log_settings(data) -> List[str]:
    errors = []
    for key, label, maximum in (("logs_keep_days", "Keep logs for N days", KEEP_DAYS_MAX),
                                ("logs_max_mb", "Logs folder size limit (MB)", MAX_MB_MAX)):
        if key not in (data or {}):
            continue
        raw = data.get(key)
        try:
            ok = not isinstance(raw, bool) and 1 <= int(float(str(raw).strip())) <= maximum
        except (TypeError, ValueError):
            ok = False
        if not ok:
            errors.append("«{}» must be a whole number from 1 to {}.".format(label, maximum))
    return errors


# ------------------------------------------------------------------ files

_RESERVED = {"con", "prn", "aux", "nul", *("com%d" % i for i in range(1, 10)), *("lpt%d" % i for i in range(1, 10))}


def safe_file_part(name) -> str:
    """A profile name that is safe as part of a file name on every system."""
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", str(name or "")).strip(" ._")
    text = re.sub(r"\s+", " ", text)[:60].strip(" ._")
    if not text:
        text = "profile"
    if text.casefold() in _RESERVED:
        text += "_"
    return text


def day_file_name(profile, day) -> str:
    stamp = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)
    return "{}_{}.txt".format(safe_file_part(profile), stamp)


def logs_dir_for(base_dir) -> str:
    """The ``logs`` folder of the app's data directory (desktop: beside the
    config; Android: the app files directory)."""
    return os.path.join(str(base_dir), LOGS_FOLDER_NAME)


def list_log_files(folder):
    """``[(path, profile_part, day, size)]`` for every daily file in ``folder``."""
    found = []
    try:
        names = os.listdir(folder)
    except OSError:
        return found
    for name in names:
        match = _FILE_RE.match(name)
        if not match:
            continue
        path = os.path.join(folder, name)
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        found.append((path, match.group("name"), match.group("day"), size))
    return found


def prune_logs(folder, keep_days, max_mb, today=None) -> List[str]:
    """Delete files older than ``keep_days``, then the oldest until the folder
    is within ``max_mb``. Today's files are never deleted. Returns the paths removed."""
    today = today or datetime.date.today()
    cutoff = (today - datetime.timedelta(days=max(1, int(keep_days)))).strftime("%Y-%m-%d")
    today_text = today.strftime("%Y-%m-%d")
    removed = []
    files = list_log_files(folder)
    survivors = []
    for item in files:
        if item[2] < cutoff:
            if _remove(item[0]):
                removed.append(item[0])
            continue
        survivors.append(item)
    limit = max(1, int(max_mb)) * 1024 * 1024
    total = sum(item[3] for item in survivors)
    for item in sorted(survivors, key=lambda it: (it[2], it[1].casefold())):
        if total <= limit:
            break
        if item[2] >= today_text:
            continue
        if _remove(item[0]):
            removed.append(item[0])
            total -= item[3]
    return removed


def _remove(path) -> bool:
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def rename_profile_logs(folder, old_name, new_name) -> int:
    """Move a profile's daily files to the new name (appending when a file of
    that day already exists). Returns how many files moved; never raises."""
    old_part, new_part = safe_file_part(old_name), safe_file_part(new_name)
    if old_part == new_part:
        return 0
    moved = 0
    for path, part, day, _size in list_log_files(folder):
        if part != old_part:
            continue
        target = os.path.join(folder, "{}_{}.txt".format(new_part, day))
        try:
            if os.path.exists(target):
                with open(path, "r", encoding="utf-8", errors="replace") as source:
                    text = source.read()
                with open(target, "a", encoding="utf-8") as out:
                    out.write(text)
                os.remove(path)
            else:
                os.replace(path, target)
            moved += 1
        except OSError:
            continue
    return moved


def read_log_lines(folder, profile=None, days=None, today=None, max_lines=20000) -> List[str]:
    """The stored lines (oldest first), optionally of one profile and the last ``days`` days."""
    today = today or datetime.date.today()
    first = None
    if days:
        first = (today - datetime.timedelta(days=max(0, int(days) - 1))).strftime("%Y-%m-%d")
    part = safe_file_part(profile) if profile else None
    files = [item for item in list_log_files(folder)
             if (part is None or item[1] == part) and (first is None or item[2] >= first)]
    lines: List[str] = []
    for path, _part, _day, _size in sorted(files, key=lambda it: (it[2], it[1].casefold())):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                lines.extend(line.rstrip("\r\n") for line in handle if line.strip())
        except OSError:
            continue
    return lines[-max_lines:]


def export_text(lines: Sequence[str]) -> str:
    """What «Save as TXT» writes: the given (already filtered) lines."""
    return "\n".join(str(line).rstrip("\r\n") for line in lines) + ("\n" if lines else "")


def save_export(path, lines: Sequence[str]) -> bool:
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(export_text(lines))
        return True
    except OSError:
        return False


class DailyLogWriter:
    """Appends lines to ``<profile>_YYYY-MM-DD.txt``; buffered, never raises.

    ``write`` only queues the line (and flushes when the buffer is big or
    old). A failure is swallowed and reported once through ``on_error``.
    """

    FLUSH_LINES = 40
    FLUSH_SECONDS = 2.0
    PRUNE_SECONDS = 600.0

    def __init__(self, folder, settings: Optional[LogSettings] = None,
                 clock: Callable[[], datetime.datetime] = datetime.datetime.now,
                 monotonic: Callable[[], float] = time.monotonic,
                 on_error: Optional[Callable[[str], None]] = None, autoflush=False):
        self.folder = str(folder)
        self.settings = settings or LogSettings.from_data({})
        self._clock = clock
        self._monotonic = monotonic
        self._on_error = on_error
        self._lock = threading.Lock()
        self._buffer: List[tuple] = []
        self._last_flush = monotonic()
        self._last_prune = None
        self._last_prune_day = None
        self._error_reported = False
        self._timer = None
        if autoflush:
            self._timer = threading.Thread(target=self._timer_loop, name="log-writer", daemon=True)
            self._timer.start()
            atexit.register(self.flush)

    def configure(self, settings: LogSettings):
        self.settings = settings

    def write(self, profile, line, when=None) -> None:
        if not self.settings.enabled:
            return
        try:
            day = (when or self._clock()).date()
            with self._lock:
                self._buffer.append((safe_file_part(profile), day.strftime("%Y-%m-%d"), str(line)))
                due = (len(self._buffer) >= self.FLUSH_LINES
                       or self._monotonic() - self._last_flush >= self.FLUSH_SECONDS)
            if due:
                self.flush()
        except Exception as error:  # never reaches the bot
            self._report(error)

    def flush(self) -> None:
        try:
            with self._lock:
                batch, self._buffer = self._buffer, []
                self._last_flush = self._monotonic()
            if not batch:
                return
            os.makedirs(self.folder, exist_ok=True)
            grouped = {}
            for part, day, line in batch:
                grouped.setdefault((part, day), []).append(line)
            for (part, day), lines in grouped.items():
                path = os.path.join(self.folder, "{}_{}.txt".format(part, day))
                with open(path, "a", encoding="utf-8", newline="\n") as handle:
                    handle.write("\n".join(lines) + "\n")
            self._maybe_prune()
        except Exception as error:
            self._report(error)

    def prune(self) -> List[str]:
        try:
            self.flush()
            return prune_logs(self.folder, self.settings.keep_days, self.settings.max_mb,
                              today=self._clock().date())
        except Exception as error:
            self._report(error)
            return []

    def rename_profile(self, old_name, new_name) -> int:
        self.flush()
        return rename_profile_logs(self.folder, old_name, new_name)

    def _maybe_prune(self):
        now = self._monotonic()
        today = self._clock().date()
        if (self._last_prune is None or today != self._last_prune_day
                or now - self._last_prune >= self.PRUNE_SECONDS):
            self._last_prune = now
            self._last_prune_day = today
            prune_logs(self.folder, self.settings.keep_days, self.settings.max_mb, today=today)

    def _timer_loop(self):
        while True:
            time.sleep(self.FLUSH_SECONDS)
            if self._buffer:
                self.flush()

    def _report(self, error):
        if self._error_reported:
            return
        self._error_reported = True
        if self._on_error:
            try:
                self._on_error("Saving log files stopped: {}".format(error))
            except Exception:
                pass
