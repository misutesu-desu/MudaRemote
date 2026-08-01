"""Pure character filters shared by runtime and tests."""

import re


_CUSTOM_EMOJI_RE = re.compile(r"<a?:[A-Za-z0-9_~]+:\d+>")
_UNICODE_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002300-\U000023FF"
    "\U00002B00-\U00002BFF"
    "\U00002900-\U0000297F"
    "\U00003030\U0000303D\U00003297\U00003299"
    "]"
)


_SERIES_METADATA_RE = re.compile(
    r"^(?:"
    r"<a?:[^:>]+:\d+>\s*\(\*{0,2}[\d,]+\*{0,2}\)"
    r"|claims?\s*:|likes?\s*:"
    r"|[\d,.]+\s+kakera\b"
    r"|\*{0,2}[\d,.]+\*{0,2}\s*<a?:kakera:"
    r")",
    re.IGNORECASE,
)


def character_series_line(description):
    """Return Mudae's series text, including any visual line wrapping.

    Long series names can be split across multiple description lines. The
    series block ends when the key/rank/value metadata begins.
    """
    series_lines = []
    for raw_line in str(description or "").splitlines():
        line = raw_line.strip()
        if not line:
            if series_lines:
                break
            continue
        if series_lines:
            if _SERIES_METADATA_RE.search(line):
                break
            # Discord/Mudae only splits the logical series marker in the cases
            # we need to recover here. Do not absorb arbitrary value lines.
            if not (_CUSTOM_EMOJI_RE.search(line) or _UNICODE_EMOJI_RE.search(line)):
                break
        series_lines.append(line)
    return " ".join(series_lines)


def series_line_has_emoji(description):
    """Treat an emoji anywhere in the wrapped series block as a starwish marker."""
    line = character_series_line(description)
    return bool(_CUSTOM_EMOJI_RE.search(line) or _UNICODE_EMOJI_RE.search(line))


def name_or_series_is_configured_wish(name, series, wishlist, series_wishlist):
    normalized_name = str(name or "").strip().casefold()
    normalized_series = str(series or "").strip().casefold()
    names = {str(item or "").strip().casefold() for item in wishlist or ()}
    series_filters = [
        str(item or "").strip().casefold()
        for item in series_wishlist or ()
        if str(item or "").strip()
    ]
    return normalized_name in names or any(item in normalized_series for item in series_filters)
