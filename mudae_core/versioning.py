"""Small semantic-version helpers without an external dependency."""

import json
import os
import re
import sys
from itertools import zip_longest
CURRENT_VERSION = "4.9.1-beta.3"
UPDATE_BRANCH_URL_TEMPLATE = "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/refs/heads/{branch}/version.json"

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
def is_prerelease(version=None):
    """Return True if the version is a pre-release (alpha, beta, rc, pre, preview)."""
    if version is None:
        version = CURRENT_VERSION
    try:
        _, pre = _parse(version)
        return pre[0] == 0
    except ValueError:
        return False


def get_settings_path(base_path=None):
    if base_path:
        return os.path.join(base_path, "settings.json")
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "settings.json")
    cwd_path = os.path.join(os.getcwd(), "settings.json")
    if os.path.isfile(cwd_path):
        return cwd_path
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(script_dir, "settings.json")


def load_update_channel_setting(base_path=None):
    """Read saved update channel from settings.json if present; return 'beta', 'main', or None."""
    try:
        path = get_settings_path(base_path)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                if "update_channel" in data:
                    val = str(data["update_channel"]).strip().lower()
                    if val in {"beta", "preview", "pre", "alpha", "rc"}:
                        return "beta"
                    if val in {"main", "stable"}:
                        return "main"
                if "beta_channel" in data or "beta_updates" in data:
                    flag = data.get("beta_channel", data.get("beta_updates"))
                    return "beta" if bool(flag) else "main"
    except Exception:
        pass
    return None


def save_update_channel_setting(channel, base_path=None):
    """Save update channel ('beta' or 'main') to settings.json atomically."""
    resolved = "beta" if str(channel).strip().lower() in {"beta", "preview", "pre", "alpha", "rc", "true", "1"} else "main"
    path = get_settings_path(base_path)
    data = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
        except Exception:
            data = {}
    data["update_channel"] = resolved
    data["beta_channel"] = (resolved == "beta")
    tmp_path = path + f".tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
    return resolved


def resolve_update_channel(channel=None, current_version=None, base_path=None):
    """Return the normalized update channel ('main' or 'beta')."""
    if channel is not None:
        raw = str(channel).strip().lower()
        if raw in {"main", "stable", "false", "0"}:
            return "main"
        if raw in {"beta", "preview", "pre", "alpha", "rc", "true", "1"}:
            return "beta"
        raise ValueError("Unknown update channel: {!r}".format(channel))
    env_channel = os.environ.get("MUDAREMOTE_UPDATE_CHANNEL", "").strip().lower()
    if env_channel:
        if env_channel in {"main", "stable", "false", "0"}:
            return "main"
        if env_channel in {"beta", "preview", "pre", "alpha", "rc", "true", "1"}:
            return "beta"
    saved = load_update_channel_setting(base_path)
    if saved:
        return saved
    version = current_version or CURRENT_VERSION
    return "beta" if is_prerelease(version) else "main"


def get_update_manifest_urls(channel=None, current_version=None, base_path=None):
    """Return an ordered tuple of candidate manifest URLs for the resolved channel."""
    resolved = resolve_update_channel(channel, current_version, base_path)
    if resolved == "beta":
        return (
            UPDATE_BRANCH_URL_TEMPLATE.format(branch="beta"),
            UPDATE_BRANCH_URL_TEMPLATE.format(branch="main"),
        )
    return (UPDATE_BRANCH_URL_TEMPLATE.format(branch="main"),)


def get_update_manifest_url(channel=None, current_version=None, base_path=None):
    """Return the primary manifest URL for the resolved channel."""
    return get_update_manifest_urls(channel, current_version, base_path)[0]
