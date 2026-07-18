"""Small semantic-version helpers without an external dependency."""

import re
from itertools import zip_longest


_VERSION_RE = re.compile(
    r"^\s*[vV]?(?P<release>\d+(?:\.\d+)*)"
    r"(?:[-.]?(?P<pre>(?:a|alpha|b|beta|rc|pre|preview))[-.]?(?P<pre_n>\d*)?)?"
    r"(?:\+[0-9A-Za-z.-]+)?\s*$",
    re.IGNORECASE,
)
_PRECEDENCE = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "pre": 2, "preview": 2, "rc": 3}


def _parse(version):
    match = _VERSION_RE.match(str(version or ""))
    if not match:
        raise ValueError("Invalid version: {!r}".format(version))
    release = tuple(int(part) for part in match.group("release").split("."))
    pre_name = match.group("pre")
    if pre_name is None:
        pre = (1, 0, 0)
    else:
        pre = (0, _PRECEDENCE[pre_name.lower()], int(match.group("pre_n") or 0))
    return release, pre


def compare_versions(left, right):
    """Return -1, 0, or 1 using semantic numeric version ordering."""
    left_release, left_pre = _parse(left)
    right_release, right_pre = _parse(right)
    for l_part, r_part in zip_longest(left_release, right_release, fillvalue=0):
        if l_part != r_part:
            return 1 if l_part > r_part else -1
    if left_pre == right_pre:
        return 0
    return 1 if left_pre > right_pre else -1


def is_newer_version(candidate, current):
    return compare_versions(candidate, current) > 0
