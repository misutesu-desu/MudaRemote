"""Small semantic-version helpers without an external dependency."""

import json
import os
import re
import sys
import urllib.request
from itertools import zip_longest
CURRENT_VERSION = "4.9.1-beta.15"
UPDATE_BRANCH_URL_TEMPLATE = "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/refs/heads/{branch}/version.json"
STABLE_RELEASE_MANIFEST_URL = "https://github.com/misutesu-desu/MudaRemote/releases/latest/download/version.json"
MANIFEST_REF_URL_TEMPLATE = "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/{ref}/version.json"

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
            STABLE_RELEASE_MANIFEST_URL,
        )
    return (UPDATE_BRANCH_URL_TEMPLATE.format(branch="main"), STABLE_RELEASE_MANIFEST_URL)


def get_update_manifest_url(channel=None, current_version=None, base_path=None):
    """Return the primary manifest URL for the resolved channel."""
    return get_update_manifest_urls(channel, current_version, base_path)[0]


class ReleaseDiscoveryError(RuntimeError):
    """Raised when the GitHub release catalog or a release manifest cannot be fetched."""


RELEASES_API_URL = "https://api.github.com/repos/misutesu-desu/MudaRemote/releases"
RELEASES_PAGE_SIZE = 100
RELEASES_MAX_PAGES = 10


def _release_request_headers():
    return {
        "User-Agent": "MudaRemote",
        "Accept": "application/vnd.github+json",
    }


def _fetch_release_page(session, url, headers, timeout):
    """Return (items, link_header) for one releases API page; raise on any failure."""
    if session is not None:
        resp = session.get(url, timeout=timeout, headers=headers)
        if hasattr(resp, "raise_for_status"):
            resp.raise_for_status()
        if hasattr(resp, "json"):
            raw = resp.json()
        else:
            raw = json.loads(resp.content.decode("utf-8"))
        link = resp.headers.get("Link", "") if getattr(resp, "headers", None) else ""
    else:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            link = resp.headers.get("Link", "") if hasattr(resp, "headers") else ""
    if not isinstance(raw, list):
        raise ReleaseDiscoveryError(
            "Unexpected response shape from the GitHub releases API (expected a list of releases)."
        )
    return raw, str(link or "")


def _next_page_number(link_header):
    match = re.search(r'<[^>]*[?&]page=(\d+)[^>]*>\s*;\s*rel="next"', link_header)
    return int(match.group(1)) if match else None


def fetch_available_releases(session=None, timeout=6.0, platform="all", channel=None):
    """Query the GitHub Releases API across every page.

    - ``channel='main'`` (stable) excludes prereleases; ``'beta'`` (or ``None``)
      keeps eligible stable and prerelease rows.
    - ``platform in {'pc', 'windows'}`` excludes Android-only releases.
    - Transport/API failures raise :class:`ReleaseDiscoveryError` instead of
      fabricating historical releases; an empty list means genuinely nothing
      eligible was published.
    """
    resolved_channel = resolve_update_channel(channel) if channel is not None else None
    headers = _release_request_headers()

    items = []
    page = 1
    link = ""
    while page <= RELEASES_MAX_PAGES:
        url = "{}?per_page={}&page={}".format(RELEASES_API_URL, RELEASES_PAGE_SIZE, page)
        try:
            raw, link = _fetch_release_page(session, url, headers, timeout)
        except ReleaseDiscoveryError:
            raise
        except Exception as exc:
            raise ReleaseDiscoveryError(
                "Failed to load the release list from GitHub (page {}): {}".format(page, exc)
            ) from exc
        items.extend(item for item in raw if isinstance(item, dict))
        if len(raw) < RELEASES_PAGE_SIZE:
            break
        next_page = _next_page_number(link)
        if not next_page or next_page <= page:
            break
        if page >= RELEASES_MAX_PAGES:
            raise ReleaseDiscoveryError(
                "Release history is too large to enumerate (page limit reached)."
            )
        page = next_page

    results = []
    seen_tags = set()
    for item in items:
        tag = str(item.get("tag_name", ""))
        name = str(item.get("name") or tag)
        is_pre = bool(item.get("prerelease", False))
        is_apk = tag.startswith("android-") or "android" in tag.lower()
        ver = tag[1:] if tag.startswith("v") else tag
        apk_url = None
        for asset in item.get("assets", []) or []:
            if str(asset.get("name", "")).lower().endswith(".apk"):
                apk_url = asset.get("browser_download_url")
                break

        if platform in {"pc", "windows"} and is_apk:
            continue
        if resolved_channel == "main" and is_pre:
            continue
        if not tag or tag in seen_tags:
            continue
        seen_tags.add(tag)
        results.append({
            "version": ver,
            "tag": tag,
            "name": name,
            "prerelease": is_pre,
            "is_apk": is_apk,
            "apk_url": apk_url,
            "published_at": item.get("published_at", ""),
        })
    return results


_LATEST_RELEASE_ASSET_RE = re.compile(
    r"^(?P<base>https://github\.com/[^/]+/[^/]+/releases)/latest/download/(?P<asset>[^/?#]+)$"
)
_TAGGED_RELEASE_ASSET_RE = re.compile(
    r"^(?P<base>https://github\.com/[^/]+/[^/]+/releases)/download/(?P<tag>[^/]+)/(?P<asset>[^/?#]+)$"
)


def _normalize_release_ref(ref):
    text = str(ref or "").strip().lower()
    return text[1:] if text.startswith("v") else text


def is_version_like_ref(ref):
    """True when a selected ref names a release version, not an arbitrary branch."""
    return bool(re.match(r"^[vV]?\d", str(ref or "").strip()))


def release_identity_matches(ref, manifest_version):
    ref_n = _normalize_release_ref(ref)
    ver_n = _normalize_release_ref(manifest_version)
    if not ref_n or not ver_n:
        return False
    if ref_n == ver_n:
        return True
    if ref_n.startswith("android-"):
        return _normalize_release_ref(ref_n[len("android-"):]) == ver_n
    return False


def _align_manifest_to_ref(manifest, ref):
    """Re-point release-manifest artifact URLs at the immutable selected ref.

    Older published manifests fetched their ``source_files`` from the mutable
    ``beta``/``main`` branches, and some pointed ``exe_download_url`` at the
    mutable ``releases/latest`` alias (the v4.6.4 incident: the historical
    checksum was compared against the newest stable executable). Installing
    such a release later would download current channel-head files and fail
    their recorded checksums — or, worse, verify and install the wrong
    release. Pinning to the tag keeps targeted installs possible without
    weakening verification; an executable that names a *different* explicit
    release is a broken publication and is refused before any download.
    """
    base = "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/"

    def _pin(url):
        text = str(url or "")
        for branch in ("beta", "main"):
            prefix = base + branch + "/"
            if text.startswith(prefix):
                return base + ref + "/" + text[len(prefix):]
        return url

    files = manifest.get("source_files")
    if isinstance(files, list):
        for entry in files:
            if isinstance(entry, dict) and entry.get("url"):
                entry["url"] = _pin(entry["url"])
    if manifest.get("download_url"):
        manifest["download_url"] = _pin(manifest["download_url"])

    exe_url = str(manifest.get("exe_download_url") or "")
    if exe_url:
        latest = _LATEST_RELEASE_ASSET_RE.match(exe_url)
        if latest:
            manifest["exe_download_url"] = "{}/download/{}/{}".format(
                latest.group("base"), ref, latest.group("asset"),
            )
        else:
            tagged = _TAGGED_RELEASE_ASSET_RE.match(exe_url)
            if tagged and not release_identity_matches(tagged.group("tag"), ref):
                raise ReleaseDiscoveryError(
                    "The release manifest for '{}' points its executable at release "
                    "'{}'; these releases disagree, so nothing was downloaded. The "
                    "published metadata for that release must be corrected.".format(
                        ref, tagged.group("tag"),
                    )
                )


def fetch_manifest_for_version(session=None, version_or_tag="latest", timeout=6.0, channel=None):
    """Fetch and validate the version.json manifest for a tag, branch, or alias.

    Symbolic targets: ``latest`` honors the selected channel, ``beta``/``main``/
    ``stable`` map to their branches. Anything else is tried verbatim (exact
    release tag or branch), then with a ``v`` prefix for bare versions.
    """
    raw = str(version_or_tag or "").strip()
    if not raw or raw == "latest":
        resolved = resolve_update_channel(channel, CURRENT_VERSION)
        candidates = ["beta" if resolved == "beta" else "main"]
    elif raw == "beta":
        candidates = ["beta"]
    elif raw in {"main", "stable"}:
        candidates = ["main"]
    else:
        candidates = [raw]
        if not raw.startswith(("v", "V", "android")):
            candidates.append("v" + raw)

    headers = _release_request_headers()
    last_error = None
    identity_error = None
    for tag in candidates:
        url = MANIFEST_REF_URL_TEMPLATE.format(ref=tag)
        try:
            if session is not None:
                resp = session.get(url, timeout=timeout, headers=headers)
                if hasattr(resp, "raise_for_status"):
                    resp.raise_for_status()
                data = resp.json() if hasattr(resp, "json") else json.loads(resp.content.decode("utf-8"))
            else:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
        except ReleaseDiscoveryError:
            raise
        except Exception as exc:
            last_error = exc
            continue
        if not isinstance(data, dict) or not str(data.get("version") or "").strip():
            raise ReleaseDiscoveryError(
                "The manifest for '{}' is not a valid release manifest.".format(tag)
            )
        if tag not in {"main", "beta"}:
            if is_version_like_ref(tag) and not release_identity_matches(tag, data.get("version")):
                identity_error = ReleaseDiscoveryError(
                    "The manifest published for '{}' identifies itself as version '{}'; "
                    "installing it under the selected name would mix release metadata, "
                    "so nothing was downloaded.".format(tag, data.get("version"))
                )
                continue
            try:
                _align_manifest_to_ref(data, tag)
            except ReleaseDiscoveryError as exc:
                identity_error = exc
                continue
        return data
    if identity_error is not None:
        raise identity_error
    raise ReleaseDiscoveryError(
        "No release manifest was found for '{}' (tried: {}). Last error: {}".format(
            raw or "latest", ", ".join(candidates), last_error
        )
    )
