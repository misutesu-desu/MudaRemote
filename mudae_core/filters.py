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


def character_series_line(description):
    """Return the first non-empty line, which is Mudae's series line."""
    for line in str(description or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def series_line_has_emoji(description):
    """Treat any custom or Unicode emoji beside the series as a starwish marker."""
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
