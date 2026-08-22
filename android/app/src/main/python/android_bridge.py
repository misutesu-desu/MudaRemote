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

_lock = threading.RLock()
_threads = []
_running = False
_log_path = ""
_files_dir = ""
_runtime_thread = None
_runtime_module = None

UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/misutesu-desu/MudaRemote/refs/heads/main/version.json"
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


def _get_python_code_dir(files_dir):
    return os.path.join(str(files_dir), "python_code")


def _ensure_python_path(files_dir):
    code_dir = _get_python_code_dir(files_dir)
    if os.path.isdir(code_dir):
        while code_dir in sys.path:
            sys.path.remove(code_dir)
        sys.path.insert(0, code_dir)
    return code_dir


def _stage_runtime(profiles, tokens):
    """Stage the same presets.json the desktop CLI reads at startup."""
    global _files_dir
    staged = {}
    for preset_name, source in profiles.items():
        data = dict(source or {})
        # Tokens stay in the process environment, never in the JSON file.
        data.pop("token", None)
        data.pop("tokens", None)
        staged[str(preset_name)] = data
        raw_token = tokens.get(preset_name, "") or source.get("token", "")
        try:
            token_values = json.loads(raw_token) if isinstance(raw_token, str) and raw_token.strip().startswith("[") else [raw_token]
        except (TypeError, ValueError):
            token_values = [raw_token]
        token_values = [str(item or "").strip() for item in token_values if str(item or "").strip()]
        env_name = "MUDAREMOTE_TOKEN_{}".format(re.sub(r"[^A-Za-z0-9]+", "_", str(preset_name)).strip("_").upper())
        if token_values:
            os.environ[env_name] = json.dumps(token_values) if len(token_values) > 1 else token_values[0]

    target_dir = _files_dir or os.environ.get("HOME", ".")
    os.makedirs(target_dir, exist_ok=True)
    presets_file = os.path.join(target_dir, "presets.json")
    with open(presets_file, "w", encoding="utf-8") as handle:
        json.dump(staged, handle, ensure_ascii=False, indent=2)


def get_bundled_version():
    try:
        from mudae_core.versioning import CURRENT_VERSION
        return CURRENT_VERSION
    except Exception:
        return "1.0.0"


def get_installed_version(files_dir):
    code_dir = _get_python_code_dir(files_dir)
    version_file = os.path.join(code_dir, ".version")
    if os.path.isfile(version_file):
        try:
            with open(version_file, "r", encoding="utf-8") as handle:
                v = handle.read().strip()
                if v:
                    return v
        except OSError:
            pass
    return get_bundled_version()


def get_runtime_info(files_dir):
    """Return JSON metadata about currently installed and active Python runtime."""
    files_dir = str(files_dir)
    code_dir = _get_python_code_dir(files_dir)
    bundled = get_bundled_version()
    installed = get_installed_version(files_dir)
    is_updated = os.path.isfile(os.path.join(code_dir, "mudae_bot.py")) and os.path.isfile(os.path.join(code_dir, ".version"))
    return json.dumps({
        "current_version": installed,
        "bundled_version": bundled,
        "is_updated": is_updated,
        "code_dir": code_dir,
    }, ensure_ascii=False)


def _download_manifest(timeout_seconds=8.0):
    try:
        import requests
        response = requests.get(UPDATE_MANIFEST_URL, timeout=(3.0, timeout_seconds))
        response.raise_for_status()
        return response.json()
    except Exception:
        import urllib.request
        req = urllib.request.Request(UPDATE_MANIFEST_URL, headers={"User-Agent": "MudaRemote-Android"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))


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


def check_and_apply_update(files_dir, force=False, timeout_seconds=8.0):
    """Check remote version and download/compile updated Python modules into android app storage."""
    files_dir = str(files_dir)
    _configure_storage(files_dir)
    code_dir = _get_python_code_dir(files_dir)
    current_version = get_installed_version(files_dir)

    try:
        from mudae_core.versioning import is_newer_version
    except Exception:
        def is_newer_version(latest, current):
            return str(latest).strip() != str(current).strip()

    try:
        _log("Checking for Python runtime updates (installed: v{})...".format(current_version), "UPDATER", "INFO")
        manifest = _download_manifest(timeout_seconds=float(timeout_seconds))
        latest_version = str(manifest.get("version") or "").strip()
        if not latest_version:
            return json.dumps({"status": "error", "error": "Invalid update manifest.", "version": current_version}, ensure_ascii=False)

        if not force and not is_newer_version(latest_version, current_version):
            _log("Python runtime is up to date (v{}).".format(current_version), "UPDATER", "INFO")
            return json.dumps({"status": "current", "version": current_version}, ensure_ascii=False)

        source_files = manifest.get("source_files")
        if not isinstance(source_files, list) or not source_files:
            return json.dumps({"status": "error", "error": "No source files listed in update manifest.", "version": current_version}, ensure_ascii=False)

        _log("Downloading Python update v{} ({} files)...".format(latest_version, len(source_files)), "UPDATER", "INFO")
        os.makedirs(files_dir, exist_ok=True)
        stage_dir = tempfile.mkdtemp(prefix="android-update-", dir=files_dir)
        try:
            staged_paths = []
            for entry in source_files:
                if not isinstance(entry, dict):
                    continue
                rel_path = os.path.normpath(str(entry.get("path", "")).replace("/", os.sep))
                if os.path.isabs(rel_path) or rel_path.startswith(".." + os.sep) or rel_path.casefold() == "presets.json":
                    continue
                url = entry.get("url")
                expected_sha = str(entry.get("sha256") or "").lower()
                if not url or not expected_sha:
                    continue
                content = _download_file(url, timeout_seconds=20.0)
                actual_sha = hashlib.sha256(content).hexdigest().lower()
                if actual_sha != expected_sha:
                    raise RuntimeError("Checksum mismatch for {}: expected {}, got {}".format(rel_path, expected_sha[:8], actual_sha[:8]))
                target = os.path.join(stage_dir, rel_path)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as handle:
                    handle.write(content)
                staged_paths.append(rel_path)

            for rel_path in staged_paths:
                if rel_path.endswith(".py"):
                    try:
                        py_compile.compile(os.path.join(stage_dir, rel_path), doraise=False)
                    except Exception:
                        pass

            os.makedirs(code_dir, exist_ok=True)
            for rel_path in staged_paths:
                src = os.path.join(stage_dir, rel_path)
                dst = os.path.join(code_dir, rel_path)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                # Direct byte copy avoids copystat chmod/utime PermissionError on Android
                try:
                    with open(src, "rb") as fsrc:
                        raw_data = fsrc.read()
                    with open(dst, "wb") as fdst:
                        fdst.write(raw_data)
                except Exception:
                    if os.path.exists(dst):
                        try:
                            os.remove(dst)
                        except OSError:
                            pass
                    shutil.copyfile(src, dst)

            with open(os.path.join(code_dir, ".version"), "w", encoding="utf-8") as handle:
                handle.write(latest_version)
            with open(os.path.join(code_dir, "version.json"), "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, ensure_ascii=False, indent=2)

            # When a runtime is already live in this process, only stage the
            # files; touching sys.path/import caches now could mix old and new
            # modules inside the running bot. Activation happens on next start.
            if not _running:
                _ensure_python_path(files_dir)
                importlib.invalidate_caches()
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
    code_dir = _get_python_code_dir(files_dir)
    if os.path.isdir(code_dir):
        shutil.rmtree(code_dir, ignore_errors=True)
    if code_dir in sys.path:
        sys.path.remove(code_dir)
    for mod_name in list(sys.modules.keys()):
        if mod_name == "mudae_bot" or mod_name.startswith("mudae_core"):
            sys.modules.pop(mod_name, None)
    importlib.invalidate_caches()
    bundled = get_bundled_version()
    _log("Reset Python engine to APK bundled version (v{}).".format(bundled), "ANDROID", "INFO")
    return json.dumps({
        "status": "reset",
        "version": bundled,
    }, ensure_ascii=False)


def _load_mudae_bot(files_dir):
    code_dir = _ensure_python_path(files_dir)
    # Check if we should invalidate module cache to pick up newly updated files
    if os.path.isfile(os.path.join(code_dir, "mudae_bot.py")):
        current_mod = sys.modules.get("mudae_bot")
        if current_mod is not None and not getattr(current_mod, "__file__", "").startswith(code_dir):
            for mod_name in list(sys.modules.keys()):
                if mod_name == "mudae_bot" or mod_name.startswith("mudae_core"):
                    sys.modules.pop(mod_name, None)
            importlib.invalidate_caches()

    try:
        import mudae_bot
        return mudae_bot
    except Exception as exc:
        _log("Updated Python runtime failed to load: {}. Falling back to bundled APK code...".format(exc), "ANDROID", "ERROR")
        if code_dir in sys.path:
            sys.path.remove(code_dir)
        for mod_name in list(sys.modules.keys()):
            if mod_name == "mudae_bot" or mod_name.startswith("mudae_core"):
                sys.modules.pop(mod_name, None)
        importlib.invalidate_caches()
        import mudae_bot
        return mudae_bot


def _inject_runtime_presets(mudae_bot, files_dir):
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

    prepared_count = 0
    tokenized_count = 0
    for name, data in loaded.items():
        if not isinstance(data, dict):
            continue
        data.pop("token", None)
        data.pop("tokens", None)
        _normalize_preset_value(data)
        tokens = tokens_by_preset.get(name) or []
        data["tokens"] = tokens
        data["token"] = tokens[0] if tokens else ""
        prepared_count += 1
        if tokens:
            tokenized_count += 1

    target = getattr(mudae_bot, "presets", None)
    if isinstance(target, dict):
        target.clear()
        target.update(loaded)
    else:
        _log("mudae_bot.presets missing; cannot inject profiles.", "ANDROID", "ERROR")
        return

    _log(
        "Staged {} profile(s); {} with token(s).".format(prepared_count, tokenized_count),
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


def start(profiles_json, tokens_json, files_dir):
    """Invoke the real ``mudae_bot.py`` CLI entry point in a worker thread."""
    global _running, _threads, _runtime_thread, _runtime_module, _tee_active, _tee_session
    with _lock:
        if _running:
            return "already-running"
        if _runtime_thread is not None and _runtime_thread.is_alive():
            _log("Previous runtime thread is still stopping; starting anyway.", "ANDROID", "WARN")
        _configure_storage(str(files_dir))
        profiles = json.loads(str(profiles_json))
        tokens = json.loads(str(tokens_json))
        # Backward compatibility with the first one-profile APK format.
        if "channel_id" in profiles:
            profiles = {"MAIN": profiles}
        if not isinstance(tokens, dict):
            tokens = {"MAIN": str(tokens)}
        _stage_runtime(profiles, tokens)

        # Install this session's tee BEFORE any staging/updater output so every
        # line of the session flows through exactly one writer.
        base_stdout = _unwrap_output(sys.stdout)
        base_stderr = _unwrap_output(sys.stderr)
        out_tee = _Tee(base_stdout)
        err_tee = _Tee(base_stderr)
        sys.stdout = out_tee
        sys.stderr = err_tee
        _tee_session += 1
        session_id = _tee_session
        _tee_active = True

        # Non-blocking automatic check for Python updates on start
        try:
            check_and_apply_update(files_dir, force=False, timeout_seconds=4.0)
        except Exception as update_err:
            _log("Auto-update check: {}".format(update_err), "ANDROID", "DEBUG")

        mudae_bot = _load_mudae_bot(files_dir)
        _runtime_module = mudae_bot
        mudae_bot.print_log = _log
        if hasattr(mudae_bot, "reset_mobile_runtime"):
            mudae_bot.reset_mobile_runtime()

        # Critical on Android: see docstring. Without it the engine never sees
        # any profiles and exits immediately after its update checks.
        _inject_runtime_presets(mudae_bot, str(files_dir))

        def run_real_cli():
            global _running, _runtime_thread, _tee_active
            _log("Runtime CLI starting (--all)...", "ANDROID", "INFO")
            try:
                # This is the same dispatcher used by `python mudae_bot.py`.
                mudae_bot.run_cli(["--all"])
                _log("Runtime CLI exited normally.", "ANDROID", "WARN")
            except Exception as exc:
                _log("Python runtime stopped: {}".format(exc), "ANDROID", "ERROR")
            finally:
                # Only tear down if a newer session hasn't already replaced us.
                if sys.stdout is out_tee:
                    sys.stdout = base_stdout
                if sys.stderr is err_tee:
                    sys.stderr = base_stderr
                if session_id == _tee_session:
                    _tee_active = False
                with _lock:
                    _running = False

        _running = True
        _runtime_thread = threading.Thread(target=run_real_cli, name="MudaRemote-PythonCLI", daemon=True)
        _threads = [_runtime_thread]
        _runtime_thread.start()
    return "started"


def is_running():
    """Expose runtime state so tooling (and future UI work) can query it cheaply."""
    with _lock:
        return _running


def stop():
    """Close Discord gateway clients so foreground-service Stop is authoritative."""
    global _running, _threads, _runtime_thread, _runtime_module
    with _lock:
        try:
            mudae_bot = _runtime_module
            if mudae_bot is not None and hasattr(mudae_bot, "shutdown_mobile_runtime"):
                mudae_bot.shutdown_mobile_runtime()
            elif mudae_bot is not None:
                for client in list(getattr(mudae_bot, "_active_clients", [])):
                    loop = getattr(client, "loop", None)
                    if loop and loop.is_running():
                        asyncio.run_coroutine_threadsafe(client.close(), loop)
        finally:
            _running = False
            _threads = []
            _runtime_thread = None
            _runtime_module = None
    return "stopped"
