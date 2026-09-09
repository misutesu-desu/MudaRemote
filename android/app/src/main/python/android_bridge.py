"""Android lifecycle adapter and self-updating runtime for MudaRemote."""

import asyncio
import hashlib
import importlib
import json
import os
import py_compile
import re
import shutil
import sys
import tempfile
import threading
import time

_lock = threading.RLock()
_threads = []
_profile_threads = {}
_active_profiles = {}
_active_tokens = {}
_running = False
_stopping = False
_log_path = ""
_files_dir = ""
_runtime_thread = None
_runtime_module = None
_TOKEN_ENV_PREFIX = "MUDAREMOTE_TOKEN_"

from mudae_core.versioning import (
    CURRENT_VERSION,
    compare_versions,
    get_update_manifest_urls,
    is_newer_version,
    is_prerelease,
    resolve_update_channel,
)
_BUNDLED_VERSION = CURRENT_VERSION
UPDATE_MANIFEST_URL = get_update_manifest_urls("beta")[0]
REQUIRED_SOURCE_PATHS = {
    "mudae_bot.py", "mudae_preset_editor.py", "mudae_core/__init__.py",
    "mudae_core/claiming.py", "mudae_core/config.py", "mudae_core/coordinator.py",
    "mudae_core/kakera.py", "mudae_core/runtime.py", "mudae_core/secrets.py",
    "mudae_core/status.py", "mudae_core/spheres.py", "mudae_core/filters.py",
    "mudae_core/webhooks.py", "mudae_core/updater.py", "mudae_core/versioning.py",
}

# Config keys the engine expects as Python lists. Older Android builds saved
# several of these as comma/plain strings (the schema typed them "text"),
# which crashes the runtime (str + list TypeError in on_message).
LIST_FIELDS = {
    "claim_emojis", "kakera_emojis", "chaos_emojis", "sphere_perk_emojis",
    "mk_kakera_emojis",
    "randomized_claim_reactions", "kakera_priority_order", "oh_priority_order",
    "oc_reward_priority_order", "sphere_click_targets",
    "wishlist", "avoid_list", "series_wishlist",
    "snipe_channels", "kakera_snipe_channels",
    "character_snipe_targets", "kakera_reaction_snipe_targets",
    "snipe_chat_messages", "kakera_snipe_chat_messages",
    "inactive_hours", "scheduled_roll_times",
    "auto_divorce_series", "auto_divorce_blacklist",
    "auto_divorce_blacklist_series", "claim_rounds_thresholds",
    "webhook_log_types", "debug_log_categories",
    "farm_characters", "reactive_kakera_delay_range",
}


def _normalize_preset_value(data):
    """Coerce a staged preset dict into the shape the engine expects."""
    # Desktop-editor UI artifact: merged into "tokens" by the editor before
    # save; older Android profiles may still carry it as an inert string.
    data.pop("additional_tokens", None)
    for key in list(data.keys()):
        value = data[key]
        if value is None or value == "":
            # Missing keys make the engine fall back to its own defaults;
            # empty strings do not, and have crashed list concatenation.
            del data[key]
        elif isinstance(value, str) and key in LIST_FIELDS:
            parts = [part.strip() for part in re.split(r"[,\n]", value) if part.strip()]
            if parts:
                data[key] = parts
            else:
                del data[key]
    return data


def _configure_storage(files_dir):
    global _log_path, _files_dir
    files_dir = str(files_dir)
    _files_dir = files_dir
    os.environ["HOME"] = files_dir
    os.environ["MUDAREMOTE_RUNTIME_HOME"] = files_dir
    os.environ["TERMUX_VERSION"] = "MudaRemote-Android"
    os.environ["PREFIX"] = "com.termux.mudaremote"
    os.makedirs(files_dir, exist_ok=True)
    try:
        os.chdir(files_dir)
    except OSError:
        pass
    _log_path = os.path.join(files_dir, "mudaremote_android.log")


def _log(message, preset="ANDROID", kind="INFO"):
    line = "[{}] [{}] {}".format(kind, preset, message)
    print(line, flush=True)
    if _log_path and not _tee_active:
        # While the CLI tee is active it captures this print() and mirrors it
        # into the log file itself; appending here would duplicate the line.
        _append_log_line(line.replace("\n", " ") + "\n")


_log_lock = threading.Lock()
_log_handle = None
# While the runtime CLI runs, stdout is a _Tee that mirrors every print()
# into the log file; _log must not append a second copy itself. _tee_session
# identifies the owning run so a lingering old thread cannot tear down the
# flag of a newer session.
_tee_active = False
_tee_session = 0
_tee_base_stdout = None
_tee_base_stderr = None
_tee_stdout = None
_tee_stderr = None


def _write_log_file(text):
    """Unconditional buffered append to the shared log file.

    Single open handle instead of one per write. Both _append_log_line (when
    no tee is active) and _Tee.write route through here, so each line reaches
    the file exactly once.
    """
    global _log_handle
    with _log_lock:
        try:
            if _log_handle is None:
                _log_handle = open(_log_path, "a", encoding="utf-8")
            _log_handle.write(text)
            _log_handle.flush()
        except (OSError, ValueError):
            # Handle was rotated/closed underneath us; reopen once.
            try:
                if _log_handle is not None:
                    _log_handle.close()
            except Exception:
                pass
            _log_handle = None
            try:
                with open(_log_path, "a", encoding="utf-8") as handle:
                    handle.write(text)
            except (OSError, PermissionError):
                pass


def _close_log_handle():
    global _log_handle
    with _log_lock:
        try:
            if _log_handle is not None:
                _log_handle.close()
        except Exception:
            pass
        _log_handle = None


def _clear_android_token_environment():
    """Remove plaintext token variables left by this or an older APK build."""
    for name in list(os.environ):
        if name.startswith(_TOKEN_ENV_PREFIX):
            os.environ.pop(name, None)


def _append_log_line(text):
    if not _tee_active:
        _write_log_file(text)


class _Tee:
    """Keep Chaquopy/Logcat output while copying it to the in-app log file."""

    def __init__(self, original):
        self.original = original

    def write(self, value):
        if value:
            self.original.write(value)
            self.original.flush()
            if _log_path:
                # Bypasses the _tee_active guard on purpose: this IS the
                # mirroring path that keeps engine output in the console.
                _write_log_file(value)
        return len(value)

    def flush(self):
        self.original.flush()

_active_generation_dir = None


def _get_base_python_code_dir(files_dir):
    return os.path.join(str(files_dir), "python_code")


def _get_generations_dir(files_dir):
    return os.path.join(_get_base_python_code_dir(files_dir), "generations")


def _get_selection_file(files_dir):
    return os.path.join(_get_base_python_code_dir(files_dir), "selection.json")


def _read_selection(files_dir):
    sel_file = _get_selection_file(files_dir)
    if os.path.isfile(sel_file):
        try:
            with open(sel_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
                if isinstance(data, dict) and data.get("selected_generation"):
                    return data
        except (OSError, ValueError):
            pass
    return None


def _write_selection(files_dir, gen_id, version, prev_gen=None):
    base_dir = _get_base_python_code_dir(files_dir)
    os.makedirs(base_dir, exist_ok=True)
    sel_file = _get_selection_file(files_dir)
    tmp_file = sel_file + ".tmp"
    data = {
        "selected_generation": gen_id,
        "version": str(version),
        "previous_generation": prev_gen,
    }
    with open(tmp_file, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_file, sel_file)


def _get_active_code_dir(files_dir):
    """Return selected generation directory, or None if bundled/no selection."""
    sel = _read_selection(files_dir)
    if sel:
        gen_dir = os.path.join(_get_generations_dir(files_dir), sel["selected_generation"])
        if os.path.isfile(os.path.join(gen_dir, "mudae_bot.py")):
            return gen_dir
    return None


def _get_python_code_dir(files_dir):
    active = _get_active_code_dir(files_dir)
    if active is not None:
        return active
    return _get_base_python_code_dir(files_dir)


def _ensure_python_path(files_dir, target_dir=None):
    if target_dir is None:
        target_dir = _get_active_code_dir(files_dir)
    base_dir = _get_base_python_code_dir(files_dir)
    to_remove = [p for p in list(sys.path) if p == base_dir or p.startswith(base_dir)]
    for p in to_remove:
        while p in sys.path:
            sys.path.remove(p)
    if target_dir and os.path.isdir(target_dir):
        sys.path.insert(0, target_dir)
        return target_dir
    return None


def _clean_old_generations(files_dir, keep_ids=None):
    if keep_ids is None:
        keep_ids = set()
    sel = _read_selection(files_dir)
    if sel:
        if sel.get("selected_generation"):
            keep_ids.add(sel["selected_generation"])
        if sel.get("previous_generation"):
            keep_ids.add(sel["previous_generation"])
    global _active_generation_dir
    if _active_generation_dir:
        keep_ids.add(os.path.basename(_active_generation_dir))

    gens_dir = _get_generations_dir(files_dir)
    if os.path.isdir(gens_dir):
        for entry in os.listdir(gens_dir):
            if entry not in keep_ids:
                target = os.path.join(gens_dir, entry)
                if os.path.isdir(target):
                    shutil.rmtree(target, ignore_errors=True)
def _stage_runtime(profiles, tokens):
    """Stage the same presets.json the desktop CLI reads at startup."""
    global _files_dir
    staged = {}
    for preset_name, source in profiles.items():
        data = dict(source or {})
        # Secrets move to the in-memory override/environment channel and never
        # enter the app-private staged presets.json file.
        data.pop("token", None)
        data.pop("tokens", None)
        data.pop("additional_tokens", None)
        staged[str(preset_name)] = data

    # Requests pass secrets directly to _inject_runtime_presets. Do not retain
    # plaintext copies in process-global environment variables.
    _clear_android_token_environment()

    target_dir = _files_dir or os.environ.get("HOME", ".")
    os.makedirs(target_dir, exist_ok=True)
    presets_file = os.path.join(target_dir, "presets.json")
    with open(presets_file, "w", encoding="utf-8") as handle:
        json.dump(staged, handle, ensure_ascii=False, indent=2)


def _evict_mudae_modules():
    """Cleanly evict mudae_bot and mudae_core modules from sys.modules."""
    for mod_name in list(sys.modules.keys()):
        if mod_name in {"mudae_bot", "mudae_preset_editor"} or mod_name == "mudae_core" or mod_name.startswith("mudae_core."):
            sys.modules.pop(mod_name, None)
    importlib.invalidate_caches()


def get_bundled_version():
    return _BUNDLED_VERSION

def get_installed_version(files_dir):
    sel = _read_selection(files_dir)
    if sel and sel.get("version"):
        return str(sel["version"]).strip()
    return get_bundled_version()


def get_runtime_info(files_dir):
    """Return JSON metadata about currently installed and active Python runtime."""
    files_dir = str(files_dir)
    with _lock:
        _clear_android_token_environment()
        if not _running and not _stopping:
            try:
                os.remove(os.path.join(files_dir, "presets.json"))
            except (FileNotFoundError, OSError):
                pass
        bundled = get_bundled_version()
        installed = get_installed_version(files_dir)
        active_code = _active_generation_dir if _running else _get_active_code_dir(files_dir)
        is_updated = (
            active_code is not None
            and os.path.isfile(os.path.join(active_code, "mudae_bot.py"))
            and os.path.isfile(os.path.join(active_code, ".version"))
        )
        live_version = getattr(_runtime_module, "CURRENT_VERSION", None) if _running and _runtime_module is not None else None
        selected_code = _get_active_code_dir(files_dir)
        is_staged = _running and (selected_code is not None) and (selected_code != _active_generation_dir)
        return json.dumps({
            "current_version": installed,
            "installed_version": installed,
            "bundled_version": bundled,
            "live_version": live_version,
            "is_updated": is_updated,
            "is_staged": is_staged,
            "channel": get_update_channel(files_dir),
            "code_dir": active_code or _get_base_python_code_dir(files_dir),
            "running": _running,
        }, ensure_ascii=False)


def get_update_channel(files_dir=None):
    """Return stored update channel ('beta' or 'main')."""
    target_dir = str(files_dir or _files_dir or "")
    if target_dir:
        try:
            path = os.path.join(target_dir, "settings.json")
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    if "update_channel" in data:
                        v = str(data["update_channel"]).strip().lower()
                        if v in {"beta", "preview", "pre", "alpha", "rc"}:
                            return "beta"
                        if v in {"main", "stable"}:
                            return "main"
                    if "beta_channel" in data or "beta_updates" in data:
                        flag = data.get("beta_channel", data.get("beta_updates"))
                        return "beta" if bool(flag) else "main"
        except Exception:
            pass
        try:
            from mudae_core.versioning import load_update_channel_setting, resolve_update_channel
            saved = load_update_channel_setting(target_dir)
            if saved:
                return saved
            return resolve_update_channel(base_path=target_dir)
        except Exception:
            pass
    return "beta" if "beta" in CURRENT_VERSION.lower() else "main"


def set_update_channel(files_dir, channel):
    """Persist update channel ('beta' or 'main') to settings.json in android files directory."""
    files_dir = str(files_dir)
    resolved = "beta" if str(channel).strip().lower() in {"beta", "preview", "pre", "alpha", "rc", "true", "1"} else "main"
    try:
        path = os.path.join(files_dir, "settings.json")
        data = {}
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
        data["update_channel"] = resolved
        data["beta_channel"] = (resolved == "beta")
        tmp_path = path + f".tmp.{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        pass
    try:
        from mudae_core.versioning import save_update_channel_setting
        save_update_channel_setting(resolved, base_path=files_dir)
    except Exception:
        pass
    _log(f"Android update channel set to: {resolved}", "ANDROID", "INFO")
    return json.dumps({"status": "ok", "channel": resolved}, ensure_ascii=False)

def _download_manifest(timeout_seconds=8.0, channel=None):
    from mudae_core.updater import discover_update_manifest
    discovery = discover_update_manifest(
        _AndroidSession,
        current_version=get_installed_version(_files_dir) if _files_dir else CURRENT_VERSION,
        channel=channel,
        timeout=(3.0, float(timeout_seconds)),
        frozen=False,
    )
    if discovery.get("status") == "error":
        raise RuntimeError(discovery.get("error", "Update check failed"))
    if discovery.get("manifest"):
        return discovery["manifest"]
    return {"version": CURRENT_VERSION}
class _AndroidResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error {}".format(self.status_code))


class _AndroidSession:
    @staticmethod
    def get(url, timeout=None):
        t = float(timeout[1] if isinstance(timeout, (tuple, list)) else (timeout or 15.0))
        content = _download_file(url, timeout_seconds=t)
        return _AndroidResponse(content, status_code=200)


def _download_file(url, timeout_seconds=15.0):
    try:
        import requests
        resp = requests.get(url, timeout=(3.0, timeout_seconds))
        resp.raise_for_status()
        return resp.content
    except Exception:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "MudaRemote-Android"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return resp.read()


def _format_changelog(manifest):
    changelog = manifest.get("changelog") if isinstance(manifest, dict) else None
    if isinstance(changelog, str):
        return changelog.strip() or "No changelog provided."
    if isinstance(changelog, (list, tuple)):
        return "\n".join("- {}".format(entry) for entry in changelog if str(entry).strip())
    if isinstance(changelog, dict):
        sections = []
        for heading, entries in changelog.items():
            if isinstance(entries, (list, tuple)):
                sections.append("{}\n{}".format(heading, "\n".join("- {}".format(e) for e in entries if str(e).strip())))
            elif str(entries).strip():
                sections.append("{}\n{}".format(heading, str(entries).strip()))
        if sections:
            return "\n\n".join(sections)
    return "No changelog provided."


def fetch_available_versions(platform="android", channel=None):
    """Return a JSON envelope for the Android release picker.

    ``{"status": "ok", "releases": [...]}`` on success or
    ``{"status": "error", "error": "..."}`` on failure — never fabricated
    releases. ``channel='main'`` excludes prereleases; ``'beta'`` includes them.
    """
    try:
        from mudae_core.versioning import fetch_available_releases
        releases = fetch_available_releases(platform=platform, channel=channel)
    except Exception as exc:
        return json.dumps(
            {"status": "error", "error": str(exc) or exc.__class__.__name__},
            ensure_ascii=False,
        )
    return json.dumps({"status": "ok", "releases": releases}, ensure_ascii=False)


def install_specific_version(files_dir, version_or_tag):
    """Download, stage, and activate a specific version in android app storage."""
    files_dir = str(files_dir)
    tag = str(version_or_tag or "").strip()
    if tag.lower().startswith("android-"):
        return json.dumps({
            "status": "error",
            "error": "That release is an Android APK build. Install it from its release page; the Python runtime updater does not apply APK releases.",
        }, ensure_ascii=False)
    with _lock:
        _configure_storage(files_dir)
        try:
            from mudae_core.versioning import fetch_manifest_for_version
            manifest = fetch_manifest_for_version(version_or_tag=tag)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Failed to fetch manifest for {tag}: {e}"}, ensure_ascii=False)
        return check_and_apply_update(files_dir, force=True, manifest_override=manifest)


def check_and_apply_update(files_dir, force=False, timeout_seconds=8.0, channel=None, manifest_override=None):
    """Check remote version and download/compile updated Python modules into android app storage."""
    files_dir = str(files_dir)
    with _lock:
        _configure_storage(files_dir)
        current_version = get_installed_version(files_dir)
        channel = channel or get_update_channel(files_dir)

        try:
            from mudae_core.updater import discover_update_manifest, REQUIRED_SOURCE_PATHS, _replace_transactionally
            from mudae_core.versioning import is_newer_version
        except Exception:
            from mudae_core.updater import REQUIRED_SOURCE_PATHS, _replace_transactionally
            def is_newer_version(latest, current):
                return str(latest).strip() != str(current).strip()
            def discover_update_manifest(session, current_version=None, channel=None, timeout=None, frozen=False):
                return {"status": "available", "manifest": _download_manifest(timeout_seconds=float(timeout_seconds), channel=channel), "version": "unknown"}

        try:
            if manifest_override and isinstance(manifest_override, dict):
                manifest = manifest_override
                _log("Applying targeted version manifest (v{})...".format(manifest.get("version")), "UPDATER", "INFO")
            else:
                _log("Checking for Python runtime updates (installed: v{}, channel: {})...".format(current_version, channel), "UPDATER", "INFO")
                manifest = _download_manifest(timeout_seconds=float(timeout_seconds), channel=channel)
            if not isinstance(manifest, dict):
                return json.dumps({"status": "error", "error": "Invalid update manifest.", "version": current_version}, ensure_ascii=False)
            latest_version = str(manifest.get("version") or "").strip()
            if not latest_version:
                return json.dumps({"status": "error", "error": "Invalid update manifest.", "version": current_version}, ensure_ascii=False)

            # Parse APK update notice early so it is present in all success responses
            apk_version = manifest.get("apk_version")
            apk_url = manifest.get("apk_url") or manifest.get("apk_download_url")
            apk_update = None
            if apk_version and apk_url:
                apk_update = {
                    "version": str(apk_version),
                    "url": str(apk_url),
                    "version_code": manifest.get("apk_version_code"),
                }

            if not force and not is_newer_version(latest_version, current_version):
                _log("Python runtime is up to date (v{}).".format(current_version), "UPDATER", "INFO")
                return json.dumps({
                    "status": "current",
                    "version": current_version,
                    "apk_update": apk_update,
                }, ensure_ascii=False)
            source_files = manifest.get("source_files")
            if not isinstance(source_files, list) or not source_files:
                return json.dumps({"status": "error", "error": "No source files listed in update manifest.", "version": current_version}, ensure_ascii=False)

            _log("Downloading Python update v{} ({} files)...".format(latest_version, len(source_files)), "UPDATER", "INFO")
            os.makedirs(files_dir, exist_ok=True)
            stage_dir = tempfile.mkdtemp(prefix="android-update-", dir=files_dir)
            try:
                staged_paths = []
                seen_paths = set()
                for entry in source_files:
                    if not isinstance(entry, dict):
                        raise RuntimeError("Invalid entry in source_files manifest.")
                    rel_path = os.path.normpath(str(entry.get("path", "")).replace("/", os.sep))
                    if os.path.isabs(rel_path) or rel_path.startswith(".." + os.sep) or rel_path.casefold() == "presets.json":
                        raise RuntimeError("Unsafe or protected path in manifest: {!r}".format(rel_path))
                    url = entry.get("url")
                    expected_sha = str(entry.get("sha256") or "").lower()
                    if not url or not expected_sha:
                        raise RuntimeError("Missing url or sha256 for {!r}".format(rel_path))
                    if rel_path in seen_paths:
                        raise RuntimeError("Duplicate path in manifest: {!r}".format(rel_path))
                    seen_paths.add(rel_path)
                    content = _download_file(url, timeout_seconds=20.0)
                    actual_sha = hashlib.sha256(content).hexdigest().lower()
                    if actual_sha != expected_sha:
                        raise RuntimeError("Checksum mismatch for {}: expected {}, got {}".format(rel_path, expected_sha[:8], actual_sha[:8]))
                    target = os.path.join(stage_dir, rel_path)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, "wb") as handle:
                        handle.write(content)
                    staged_paths.append(rel_path)

                if not REQUIRED_SOURCE_PATHS.issubset({p.replace("\\", "/") for p in staged_paths}):
                    raise RuntimeError("The update manifest is incomplete (missing required source files).")

                for rel_path in staged_paths:
                    if rel_path.endswith(".py"):
                        py_compile.compile(os.path.join(stage_dir, rel_path), doraise=True)

                version_json_path = os.path.join(stage_dir, "version.json")
                with open(version_json_path, "w", encoding="utf-8") as handle:
                    json.dump(manifest, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                staged_paths.append("version.json")

                version_marker_path = os.path.join(stage_dir, ".version")
                with open(version_marker_path, "w", encoding="utf-8") as handle:
                    handle.write(latest_version)
                staged_paths.append(".version")

                # Create immutable generation directory
                gen_id = f"gen-{int(time.time())}-{os.urandom(4).hex()}"
                gens_dir = _get_generations_dir(files_dir)
                gen_dir = os.path.join(gens_dir, gen_id)
                os.makedirs(gen_dir, exist_ok=True)
                _replace_transactionally(gen_dir, stage_dir, staged_paths)

                # Commit selection atomically
                current_sel = _read_selection(files_dir)
                prev_gen = current_sel.get("selected_generation") if current_sel else None
                _write_selection(files_dir, gen_id, latest_version, prev_gen)

                _clean_old_generations(files_dir, keep_ids={gen_id})

                if not _running:
                    global _active_generation_dir
                    _active_generation_dir = gen_dir
                    _ensure_python_path(files_dir, target_dir=gen_dir)
                    _evict_mudae_modules()
                    _log("Successfully updated Python runtime to v{}!".format(latest_version), "UPDATER", "INFO")
                    status = "updated"
                else:
                    _log("Python update v{} downloaded and staged. Restart the runtime to apply it.".format(latest_version), "UPDATER", "INFO")
                    status = "staged"

                changelog_text = _format_changelog(manifest)
                return json.dumps({
                    "status": status,
                    "version": latest_version,
                    "previous": current_version,
                    "changelog": changelog_text,
                    "apk_update": apk_update,
                }, ensure_ascii=False)
            finally:
                shutil.rmtree(stage_dir, ignore_errors=True)

        except Exception as exc:
            _log("Python update check failed: {}".format(exc), "UPDATER", "WARN")
            return json.dumps({
                "status": "error",
                "error": str(exc),
                "version": current_version,
            }, ensure_ascii=False)

def reset_to_bundled_code(files_dir):
    """Delete downloaded update cache and restore the bundled APK Python modules."""
    files_dir = str(files_dir)
    with _lock:
        if _running or _stopping:
            return json.dumps({
                "status": "error",
                "error": "Cannot reset Python engine while runtime is running or stopping.",
                "version": get_installed_version(files_dir),
            }, ensure_ascii=False)
        base_dir = _get_base_python_code_dir(files_dir)
        if os.path.isdir(base_dir):
            shutil.rmtree(base_dir, ignore_errors=True)
        to_remove = [p for p in list(sys.path) if p == base_dir or p.startswith(base_dir)]
        for p in to_remove:
            while p in sys.path:
                sys.path.remove(p)
        global _active_generation_dir
        _active_generation_dir = None
        _evict_mudae_modules()
    bundled = get_bundled_version()
    _log("Reset Python engine to APK bundled version (v{}).".format(bundled), "ANDROID", "INFO")
    return json.dumps({
        "status": "reset",
        "version": bundled,
    }, ensure_ascii=False)


def _load_mudae_bot(files_dir, generation_dir=None):
    if generation_dir is None:
        generation_dir = _get_active_code_dir(files_dir)
    target_dir = _ensure_python_path(files_dir, target_dir=generation_dir)
    installed_ver = get_installed_version(files_dir)
    current_mod = sys.modules.get("mudae_bot")

    should_reload = False
    if target_dir and os.path.isfile(os.path.join(target_dir, "mudae_bot.py")):
        if current_mod is not None:
            mod_file = getattr(current_mod, "__file__", "")
            mod_ver = getattr(current_mod, "CURRENT_VERSION", None)
            if not mod_file.startswith(target_dir) or (mod_ver and mod_ver != installed_ver):
                should_reload = True
    elif current_mod is not None:
        base_dir = _get_base_python_code_dir(files_dir)
        mod_file = getattr(current_mod, "__file__", "")
        if base_dir and mod_file.startswith(base_dir):
            should_reload = True

    if should_reload:
        _evict_mudae_modules()

    try:
        import mudae_bot
        return mudae_bot
    except Exception as exc:
        _log("Updated Python runtime failed to load: {}. Falling back to bundled APK code...".format(exc), "ANDROID", "ERROR")
        if target_dir and target_dir in sys.path:
            sys.path.remove(target_dir)
        global _active_generation_dir
        _active_generation_dir = None
        sel_file = _get_selection_file(files_dir)
        try:
            if os.path.isfile(sel_file):
                os.remove(sel_file)
        except OSError:
            pass
        _evict_mudae_modules()
        import mudae_bot
        return mudae_bot


def _decode_token_value(raw):
    """Normalize a scalar or JSON-array secret payload without logging it."""
    if isinstance(raw, (list, tuple)):
        decoded = raw
    elif isinstance(raw, str) and raw.strip().startswith("["):
        try:
            decoded = json.loads(raw)
        except ValueError:
            decoded = [raw]
    else:
        decoded = [raw]
    values = []
    for candidate in decoded:
        cleaned = str(candidate or "").strip()
        if cleaned and cleaned not in values:
            values.append(cleaned)
    return values


def _inject_runtime_presets(mudae_bot, files_dir, token_overrides=None):
    """Load the staged presets.json into mudae_bot.presets with resolved tokens.

    The engine resolves presets.json relative to its own module directory
    (get_base_path()), which inside Chaquopy is the interpreter asset dir, not
    the app filesDir where this bridge stages it. Without this injection the
    engine silently starts with an empty preset map and `--all` launches
    nothing — appearing as a hang right after the update checks.
    """
    presets_file = os.path.join(str(files_dir), "presets.json")
    loaded = {}
    if os.path.isfile(presets_file):
        try:
            with open(presets_file, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except (OSError, ValueError) as exc:
            _log("Staged presets.json unreadable: {}".format(exc), "ANDROID", "ERROR")
            loaded = {}
    if not isinstance(loaded, dict):
        loaded = {}

    # Mirror mudae_bot's own module-level token resolution: env var first,
    # then the platform secret store rooted at filesDir.
    tokens_by_preset = {}
    try:
        store = mudae_bot.SecretStore(str(files_dir))
        for name in loaded:
            try:
                tokens_by_preset[name] = store.get_tokens(name, "")
            except Exception as exc:
                _log("Token store error for '{}': {}".format(name, exc), "ANDROID", "WARN")
                tokens_by_preset[name] = []
    except Exception as exc:
        _log("SecretStore unavailable ({}); using env vars only.".format(exc), "ANDROID", "WARN")
        for name in loaded:
            clean = re.sub(r"[^A-Za-z0-9]+", "_", str(name)).strip("_").upper()
            raw = os.environ.get("MUDAREMOTE_TOKEN_{}".format(clean), "")
            values = []
            try:
                decoded = json.loads(raw) if raw.startswith("[") else ([raw] if raw else [])
                values = [str(v).strip() for v in decoded if str(v or "").strip()]
            except ValueError:
                values = [raw.strip()] if raw.strip() else []
            tokens_by_preset[name] = values

    # The Android service passes the selected secrets directly to the bridge.
    # Prefer that immutable request snapshot over sanitized environment names,
    # which can collide for profile names containing punctuation.
    for name, raw in dict(token_overrides or {}).items():
        values = _decode_token_value(raw)
        if values:
            tokens_by_preset[str(name)] = values

    prepared_count = 0
    tokenized_count = 0
    account_count = 0
    for name, data in loaded.items():
        if not isinstance(data, dict):
            continue
        data.pop("token", None)
        _normalize_preset_value(data)
        # Multi-account presets carry a "tokens" list in the staged JSON; env
        # vars only ever hold the primary token from the Android input. Merge
        # both (env first), preserving order and dropping duplicates, so every
        # account expands in prepare_active_presets.
        merged = []
        for candidate in list(tokens_by_preset.get(name) or []) + list(data.get("tokens") or []):
            cleaned = str(candidate or "").strip()
            if cleaned and cleaned not in merged:
                merged.append(cleaned)
        data["tokens"] = merged
        data["token"] = merged[0] if merged else ""
        prepared_count += 1
        if merged:
            tokenized_count += 1
            account_count += len(merged)

    target = getattr(mudae_bot, "presets", None)
    if isinstance(target, dict):
        target.clear()
        target.update(loaded)
    else:
        _log("mudae_bot.presets missing; cannot inject profiles.", "ANDROID", "ERROR")
        return

    _log(
        "Staged {} profile(s); {} runnable, {} account(s) total.".format(prepared_count, tokenized_count, account_count),
        "ANDROID",
        "INFO" if tokenized_count else "WARN",
    )


def _unwrap_output(stream):
    """Peel any stacked _Tee layers left by earlier runtime sessions.

    stop() releases the run lock before the previous CLI thread has fully
    exited, so a quick Start used to capture the old Tee as its "original".
    Every restart then added a mirror layer and log lines appeared once per
    layer. Unwrapping guarantees exactly one live Tee per session.
    """
    depth = 0
    while isinstance(stream, _Tee) and depth < 16:
        stream = stream.original
        depth += 1
    return stream


def _parse_launch_payload(profiles_json, tokens_json):
    profiles = json.loads(str(profiles_json))
    tokens = json.loads(str(tokens_json))
    # Backward compatibility with the first one-profile APK format.
    if isinstance(profiles, dict) and "channel_id" in profiles:
        profiles = {"MAIN": profiles}
    if not isinstance(profiles, dict):
        raise ValueError("Profiles payload must be a JSON object.")
    if not isinstance(tokens, dict):
        tokens = {"MAIN": str(tokens)}
    clean_profiles = {}
    for name, data in profiles.items():
        if isinstance(data, dict):
            clean_profiles[str(name)] = dict(data)
    clean_tokens = {str(name): raw for name, raw in tokens.items()}
    return clean_profiles, clean_tokens


def _prune_dead_workers_locked():
    global _threads
    for name in list(_profile_threads):
        alive = [thread for thread in _profile_threads[name] if thread and thread.is_alive()]
        if alive:
            _profile_threads[name] = alive
        else:
            _profile_threads.pop(name, None)
            _active_profiles.pop(name, None)
            _active_tokens.pop(name, None)
    _threads = [thread for workers in _profile_threads.values() for thread in workers]


def _worker_count_locked():
    _prune_dead_workers_locked()
    return len(_threads)


def _install_tee_locked():
    global _tee_active, _tee_session, _tee_base_stdout, _tee_base_stderr, _tee_stdout, _tee_stderr
    _tee_base_stdout = _unwrap_output(sys.stdout)
    _tee_base_stderr = _unwrap_output(sys.stderr)
    _tee_stdout = _Tee(_tee_base_stdout)
    _tee_stderr = _Tee(_tee_base_stderr)
    sys.stdout = _tee_stdout
    sys.stderr = _tee_stderr
    _tee_session += 1
    _tee_active = True
    return _tee_session


def _restore_tee_locked(session_id):
    global _tee_active, _tee_base_stdout, _tee_base_stderr, _tee_stdout, _tee_stderr
    if session_id != _tee_session or not _tee_active:
        return
    _tee_active = False
    if _tee_base_stdout is not None:
        sys.stdout = _tee_base_stdout
    if _tee_base_stderr is not None:
        sys.stderr = _tee_base_stderr
    _tee_base_stdout = None
    _tee_base_stderr = None
    _tee_stdout = None
    _tee_stderr = None


def _clear_session_locked(session_id):
    global _running, _stopping, _threads, _runtime_thread, _runtime_module, _active_generation_dir
    if session_id != _tee_session:
        return
    _running = False
    _stopping = False
    _threads = []
    _profile_threads.clear()
    _active_profiles.clear()
    _active_tokens.clear()
    _runtime_thread = None
    _runtime_module = None
    _active_generation_dir = None
    _restore_tee_locked(session_id)
    _clear_android_token_environment()
    _close_log_handle()
    if _files_dir:
        _clean_old_generations(_files_dir)

def _monitor_workers(session_id):
    """Own session cleanup after the last account worker actually exits."""
    while True:
        with _lock:
            if session_id != _tee_session:
                return
            if _worker_count_locked() == 0:
                _clear_session_locked(session_id)
                return
        time.sleep(0.2)


def _start_profile_workers(mudae_bot, profile_names, start_index):
    started = {}
    account_index = int(start_index)
    for profile_name in profile_names:
        prepared = mudae_bot.prepare_active_presets(
            [profile_name],
            mudae_bot.presets,
            start_index=account_index,
        )
        workers = []
        for account_name, account_data in prepared:
            worker = mudae_bot.start_preset_thread(account_name, account_data)
            if worker is not None:
                workers.append(worker)
                account_index += 1
        if workers:
            started[profile_name] = workers
    return started


def _status_payload(status, added_profiles=None):
    _prune_dead_workers_locked()
    return json.dumps({
        "status": status,
        "added_profiles": list(added_profiles or []),
        "active_profiles": list(_profile_threads.keys()),
        "account_count": len(_threads),
    }, ensure_ascii=False)


def start(profiles_json, tokens_json, files_dir):
    """Start new profiles inside one supervised Android runtime session.

    Repeated calls are additive and idempotent: already-active profiles stay
    connected, while newly requested profiles receive their own account
    workers. This avoids overlapping CLI generations and needless reconnects.
    """
    global _running, _stopping, _runtime_thread, _runtime_module, _active_generation_dir
    profiles, tokens = _parse_launch_payload(profiles_json, tokens_json)
    if not profiles:
        raise ValueError("No profiles were supplied.")

    with _lock:
        _configure_storage(str(files_dir))
        _prune_dead_workers_locked()
        if _stopping:
            if _profile_threads:
                return _status_payload("stopping")
            _clear_session_locked(_tee_session)

        first_launch = not _running or not _profile_threads
        if first_launch:
            session_id = _install_tee_locked()
            try:
                check_and_apply_update(files_dir, force=False, timeout_seconds=4.0)
            except Exception as update_err:
                _log("Auto-update check: {}".format(update_err), "ANDROID", "DEBUG")
            _active_generation_dir = _get_active_code_dir(files_dir)
            mudae_bot = _load_mudae_bot(files_dir, generation_dir=_active_generation_dir)
            _runtime_module = mudae_bot
            if hasattr(mudae_bot, "reset_mobile_runtime"):
                mudae_bot.reset_mobile_runtime()
        else:
            session_id = _tee_session
            mudae_bot = _runtime_module

        requested_names = list(profiles.keys())
        new_names = [name for name in requested_names if name not in _profile_threads]
        if not new_names:
            return _status_payload("already-active")

        for name in new_names:
            _active_profiles[name] = profiles[name]
            if name in tokens:
                _active_tokens[name] = tokens[name]

        # Restage the full active set so sticky restarts and later additions see
        # one coherent snapshot. Existing clients retain their copied config.
        _stage_runtime(_active_profiles, _active_tokens)
        _inject_runtime_presets(mudae_bot, str(files_dir), _active_tokens)
        start_index = _worker_count_locked()
        started = _start_profile_workers(mudae_bot, new_names, start_index)
        for name, workers in started.items():
            _profile_threads[name] = workers

        skipped = [name for name in new_names if name not in started]
        for name in skipped:
            _active_profiles.pop(name, None)
            _active_tokens.pop(name, None)
        if not started:
            if first_launch:
                _clear_session_locked(session_id)
            return _status_payload("no-runnable-profiles")

        _running = True
        _stopping = False
        if _runtime_thread is None or not _runtime_thread.is_alive():
            _runtime_thread = threading.Thread(
                target=_monitor_workers,
                args=(session_id,),
                name="MudaRemote-Supervisor",
                daemon=True,
            )
            _runtime_thread.start()

        status = "started" if first_launch else "added"
        _log(
            "{} {} profile(s); {} account worker(s) active.".format(
                "Started" if first_launch else "Added",
                len(started),
                _worker_count_locked(),
            ),
            "ANDROID",
            "INFO",
        )
        return _status_payload(status, started.keys())


def is_running():
    """Expose state only while at least one owned account worker is alive."""
    with _lock:
        return bool(_running and _worker_count_locked())


def stop(timeout_seconds=12.0):
    global _running, _stopping, _active_generation_dir
    global _running, _stopping
    timeout_seconds = max(0.0, float(timeout_seconds))
    deadline = time.monotonic() + timeout_seconds
    with _lock:
        _prune_dead_workers_locked()
        session_id = _tee_session
        if not _profile_threads:
            _clear_session_locked(session_id)
            return json.dumps({
                "status": "stopped",
                "added_profiles": [],
                "active_profiles": [],
                "account_count": 0,
            }, ensure_ascii=False)
        _stopping = True
        mudae_bot = _runtime_module
        workers = list(_threads)

    if mudae_bot is not None and hasattr(mudae_bot, "shutdown_mobile_runtime"):
        try:
            mudae_bot.shutdown_mobile_runtime(min(8.0, timeout_seconds))
        except TypeError:
            # Compatibility with a previously downloaded runtime module whose
            # hook predates the bounded-wait parameter.
            mudae_bot.shutdown_mobile_runtime()
    elif mudae_bot is not None:
        for client in list(getattr(mudae_bot, "_active_clients", [])):
            loop = getattr(client, "loop", None)
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(client.close(), loop)

    for worker in workers:
        remaining = max(0.0, deadline - time.monotonic())
        if remaining <= 0:
            break
        worker.join(remaining)

    with _lock:
        alive = _worker_count_locked()
        if alive:
            _running = True
            _log(
                "Stop is still waiting for {} account worker(s); new starts are blocked.".format(alive),
                "ANDROID",
                "WARN",
            )
            return _status_payload("stopping")
        _clear_session_locked(session_id)
        _active_generation_dir = None
        if _files_dir:
            _clean_old_generations(_files_dir)
        return json.dumps({
            "status": "stopped",
            "active_profiles": [],
            "account_count": 0,
        }, ensure_ascii=False)
