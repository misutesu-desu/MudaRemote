"""Verified, manifest-based updater for both source and frozen builds."""

import functools
import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import threading
from .versioning import (
    CURRENT_VERSION,
    compare_versions,
    get_update_manifest_urls,
    is_newer_version,
    is_prerelease,
    resolve_update_channel,
)

class UpdateError(RuntimeError):
    pass


# Keep startup failures short. ``requests`` applies these as separate connect
# and read-idle limits, including redirected GitHub release downloads.
UPDATE_DOWNLOAD_TIMEOUT = (5.0, 20.0)
PROTECTED_UPDATE_PATHS = {"presets.json", "settings.json"}
REQUIRED_SOURCE_PATHS = {
    "mudae_bot.py", "mudae_preset_editor.py", "mudae_core/__init__.py",
    "mudae_core/claiming.py", "mudae_core/config.py", "mudae_core/coordinator.py",
    "mudae_core/kakera.py", "mudae_core/runtime.py", "mudae_core/secrets.py",
    "mudae_core/status.py", "mudae_core/spheres.py", "mudae_core/filters.py",
    "mudae_core/webhooks.py", "mudae_core/updater.py", "mudae_core/versioning.py",
}


def format_update_changelog(manifest):
    """Return human-readable release notes from a manifest changelog value."""
    changelog = manifest.get("changelog") if isinstance(manifest, dict) else None
    if isinstance(changelog, str):
        return changelog.strip() or "No changelog was provided for this update."
    if isinstance(changelog, (list, tuple)):
        entries = [str(entry).strip() for entry in changelog if str(entry).strip()]
        if entries:
            return "\n".join("- {}".format(entry) for entry in entries)
    if isinstance(changelog, dict):
        sections = []
        for heading, entries in changelog.items():
            heading = str(heading).strip()
            if isinstance(entries, (list, tuple)):
                lines = [str(entry).strip() for entry in entries if str(entry).strip()]
                if lines:
                    sections.append("{}\n{}".format(
                        heading,
                        "\n".join("- {}".format(entry) for entry in lines),
                    ))
            elif str(entries).strip():
                sections.append("{}\n{}".format(heading, str(entries).strip()))
        if sections:
            return "\n\n".join(sections)
    return "No changelog was provided for this update."


def discover_update_manifest(session, current_version=None, channel=None, timeout=(3.05, 8.0), frozen=False):
    """Discover the newest eligible update manifest across candidate channel URLs.

    Returns a dict with:
      - status: "available", "current", or "error"
      - manifest: dict (when available)
      - version: str
      - channel: str
      - url: str
    """
    if current_version is None:
        current_version = CURRENT_VERSION
    resolved_channel = resolve_update_channel(channel, current_version)
    candidate_urls = get_update_manifest_urls(resolved_channel, current_version)

    candidates = []
    eligible_manifests = []
    errors = []
    for url in candidate_urls:
        try:
            content = _download(session, url, timeout)
            manifest = json.loads(content.decode("utf-8") if isinstance(content, bytes) else content)
            if not isinstance(manifest, dict):
                continue
            ver = str(manifest.get("version") or "").strip()
            if not ver:
                continue
            if frozen:
                exe_url = manifest.get("exe_download_url")
                exe_sha = manifest.get("exe_sha256")
                if not exe_url or not exe_sha or str(exe_sha).lower() == "pending-github-actions":
                    continue
            if resolved_channel == "main" and is_prerelease(ver):
                continue
            eligible_manifests.append((ver, manifest, url))
            if is_newer_version(ver, current_version):
                candidates.append((ver, manifest, url))
        except Exception as exc:
            errors.append((url, str(exc)))

    if candidates:
        candidates.sort(
            key=functools.cmp_to_key(lambda a, b: compare_versions(a[0], b[0])),
            reverse=True,
        )
        best_ver, best_manifest, best_url = candidates[0]
        return {
            "status": "available",
            "manifest": best_manifest,
            "version": best_ver,
            "channel": resolved_channel,
            "url": best_url,
        }
    primary_url = candidate_urls[0] if candidate_urls else None
    primary_error = next((err for url, err in errors if url == primary_url), None)

    if errors and len(errors) == len(candidate_urls):
        return {
            "status": "error",
            "error": "Failed to check update servers: " + "; ".join(f"{u}: {e}" for u, e in errors),
            "version": current_version,
            "channel": resolved_channel,
        }

    # If the primary channel failed and no candidate was found from any source, do not falsely report 'current'
    if primary_error and not candidates:
        return {
            "status": "error",
            "error": f"Primary channel check failed ({primary_url}): {primary_error}",
            "version": current_version,
            "channel": resolved_channel,
        }

    best_manifest = None
    best_ver = current_version
    best_url = candidate_urls[0] if candidate_urls else None
    if eligible_manifests:
        eligible_manifests.sort(
            key=functools.cmp_to_key(lambda a, b: compare_versions(a[0], b[0])),
            reverse=True,
        )
        best_ver, best_manifest, best_url = eligible_manifests[0]

    return {
        "status": "current",
        "manifest": best_manifest,
        "version": best_ver,
        "channel": resolved_channel,
        "url": best_url,
    }

def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def _download(session, url, timeout):
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def _validate_relative_path(relative_path):
    raw = str(relative_path or "")
    if "\0" in raw or ":" in raw:
        raise UpdateError("Unsafe update path: {!r}".format(relative_path))
    normalized = os.path.normpath(raw.replace("/", os.sep))
    if os.path.isabs(normalized) or normalized == os.pardir or normalized.startswith(os.pardir + os.sep):
        raise UpdateError("Unsafe update path: {!r}".format(relative_path))
    return normalized

def _verified_download(session, url, expected_hash, timeout=UPDATE_DOWNLOAD_TIMEOUT):
    if not expected_hash:
        raise UpdateError("The update manifest is missing a SHA-256 checksum.")
    content = _download(session, url, timeout)
    actual_hash = sha256_bytes(content)
    if actual_hash.lower() != str(expected_hash).lower():
        raise UpdateError(
            "The published download does not match its checksum "
            "(expected {}..., received {}...). Your current installation was kept unchanged; "
            "please retry after the release is corrected.".format(
                str(expected_hash)[:12], actual_hash[:12]
            )
        )
    return content


def _stage_source_manifest(session, manifest, stage_dir):
    files = manifest.get("source_files")
    if not isinstance(files, list) or not files:
        raise UpdateError("No source_files manifest was published for this update.")

    staged_paths = []
    seen_paths = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise UpdateError("The source_files manifest contains an invalid entry.")
        relative_path = _validate_relative_path(entry.get("path", ""))
        if not relative_path:
            raise UpdateError("The source_files manifest contains an empty path.")
        if relative_path.replace("\\", "/").casefold() in PROTECTED_UPDATE_PATHS:
            raise UpdateError("The update manifest may not replace user configuration files.")
        canonical_key = relative_path.casefold() if os.name == "nt" else relative_path
        if canonical_key in seen_paths:
            raise UpdateError("The source_files manifest contains a duplicate path: {}.".format(relative_path))
        seen_paths.add(canonical_key)
        target_path = os.path.join(stage_dir, relative_path)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        content = _verified_download(session, entry.get("url"), entry.get("sha256"))
        with open(target_path, "wb") as handle:
            handle.write(content)
        staged_paths.append(relative_path)

    if not REQUIRED_SOURCE_PATHS.issubset({path.replace("\\", "/") for path in staged_paths}):
        raise UpdateError("The source manifest is incomplete; update was not applied.")

    for relative_path in staged_paths:
        if relative_path.endswith(".py"):
            py_compile.compile(os.path.join(stage_dir, relative_path), doraise=True)

    version_json_path = os.path.join(stage_dir, "version.json")
    with open(version_json_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    staged_paths.append("version.json")
    version_marker_path = os.path.join(stage_dir, ".version")
    with open(version_marker_path, "w", encoding="utf-8") as handle:
        handle.write(str(manifest.get("version", "")))
    staged_paths.append(".version")

    # Order replacements so dependencies are replaced first, entry points second, and metadata last
    def _sort_key(p):
        norm = p.replace("\\", "/")
        if norm in {".version", "version.json"}:
            return (3, norm)
        if norm in {"mudae_bot.py", "mudae_preset_editor.py"}:
            return (2, norm)
        return (1, norm)

    staged_paths.sort(key=_sort_key)
    return staged_paths


def _is_pid_alive(pid):
    if not pid:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
        except Exception:
            pass
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class _ExclusiveLock:
    _locks_by_path = {}
    _locks_lock = threading.Lock()

    def __init__(self, lock_path):
        self.lock_path = os.path.abspath(lock_path)
        self.fd = None
        with self._locks_lock:
            if self.lock_path not in self._locks_by_path:
                self._locks_by_path[self.lock_path] = threading.RLock()
            self._thread_lock = self._locks_by_path[self.lock_path]
        self._acquired_thread = False

    def acquire(self):
        if not self._thread_lock.acquire(blocking=False):
            return False
        self._acquired_thread = True
        try:
            self.fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR)
            if os.name == "nt":
                import msvcrt
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(self.fd, 0)
            os.lseek(self.fd, 0, os.SEEK_SET)
            os.write(self.fd, str(os.getpid()).encode("utf-8"))
            return True
        except (OSError, IOError):
            if self.fd is not None:
                try:
                    os.close(self.fd)
                except OSError:
                    pass
                self.fd = None
            self._thread_lock.release()
            self._acquired_thread = False
            return False

    def release(self):
        if self.fd is not None:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(self.fd, 0, os.SEEK_SET)
                    msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
        if self._acquired_thread:
            self._thread_lock.release()
            self._acquired_thread = False
    def __enter__(self):
        if not self.acquire():
            raise UpdateError("Another update transaction is already in progress.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
def _write_journal(journal_path, data):
    tmp_path = journal_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, journal_path)


def recover_interrupted_update(base_path):
    """Recover from a previously crashed/interrupted update using the on-disk journal."""
    journal_path = os.path.join(base_path, "update_journal.json")
    if not os.path.isfile(journal_path):
        return True
    lock_path = os.path.join(base_path, "update_transaction.lock")
    with _ExclusiveLock(lock_path):
        return _recover_interrupted_update_locked(base_path, journal_path)


def _recover_interrupted_update_locked(base_path, journal_path):
    if not os.path.isfile(journal_path):
        return True
    try:
        with open(journal_path, "r", encoding="utf-8") as handle:
            journal = json.load(handle)
    except Exception:
        return False

    pid = journal.get("pid")
    if pid and pid != os.getpid() and _is_pid_alive(pid):
        return False
    backup_dir = journal.get("backup_dir")
    if not backup_dir or not os.path.isdir(backup_dir):
        return False

    replaced = journal.get("replaced", [])
    created = journal.get("created", [])
    recovery_errors = []

    for rel_path in reversed(replaced):
        destination = os.path.join(base_path, rel_path)
        backup = os.path.join(backup_dir, rel_path)
        if not os.path.isfile(backup):
            recovery_errors.append((rel_path, "Missing backup file"))
            continue
        try:
            shutil.copyfile(backup, destination)
        except OSError as err:
            recovery_errors.append((rel_path, str(err)))

    for rel_path in created:
        destination = os.path.join(base_path, rel_path)
        try:
            if os.path.exists(destination):
                os.remove(destination)
        except OSError as err:
            recovery_errors.append((rel_path, str(err)))

    if recovery_errors:
        return False

    try:
        os.remove(journal_path)
    except OSError:
        return False

    if backup_dir and os.path.isdir(backup_dir):
        shutil.rmtree(backup_dir, ignore_errors=True)
    return True


def _read_pid_file(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return int(handle.read().strip())
    except (ValueError, OSError):
        return None


def _load_frozen_payload(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _recover_frozen_swap(payload):
    """Repair an executable left missing by a helper that died mid-swap."""
    actions = []
    current = str(payload.get("current") or "")
    if not current or os.path.isfile(current):
        return actions
    try:
        owner_pid = int(payload.get("pid"))
    except (TypeError, ValueError):
        owner_pid = 0
    backup = "{}.{}.bak".format(current, owner_pid)
    if owner_pid and os.path.isfile(backup):
        try:
            os.replace(backup, current)
            actions.append("restored previous executable from backup after an interrupted update")
            return actions
        except OSError:
            return actions
    staged = str(payload.get("staged") or "")
    expected_hash = str(payload.get("expected_hash") or "").lower()
    if staged and os.path.isfile(staged) and expected_hash:
        try:
            with open(staged, "rb") as handle:
                actual_hash = hashlib.sha256(handle.read()).hexdigest()
            if actual_hash == expected_hash:
                os.replace(staged, current)
                actions.append("completed the verified staged executable after a helper crash")
        except OSError:
            pass
    return actions


def cleanup_update_artifacts(base_path, executable=None):
    """Sweep leftover files from a crashed frozen-update helper.

    Only touches known frozen-update artifacts (``update_payload.json``,
    ``update_helper.pid``, ``mudae-frozen-update-*`` staging directories, and
    helper-created ``.<pid>.bak`` executable backups). Live transactions are
    never disturbed. Returns a list of human-readable action strings;
    never raises.
    """
    actions = []
    try:
        base_path = os.path.abspath(str(base_path))
        helper_pid_file = os.path.join(base_path, "update_helper.pid")
        root_payload_path = os.path.join(base_path, "update_payload.json")

        helper_pid = _read_pid_file(helper_pid_file) if os.path.isfile(helper_pid_file) else None
        if helper_pid and _is_pid_alive(helper_pid):
            return actions + ["update helper (PID {}) still running; cleanup skipped".format(helper_pid)]
        if os.path.isfile(helper_pid_file):
            try:
                os.remove(helper_pid_file)
                actions.append("removed stale update_helper.pid")
            except OSError:
                pass

        if os.path.isfile(root_payload_path):
            payload = _load_frozen_payload(root_payload_path)
            payload_pid = payload.get("pid") if payload else None
            if payload_pid and _is_pid_alive(int(payload_pid)):
                return actions + ["live frozen update transaction still running; cleanup skipped"]
            try:
                os.remove(root_payload_path)
                actions.append("removed stale update_payload.json")
            except OSError:
                pass

        try:
            entries = sorted(os.listdir(base_path))
        except OSError:
            entries = []
        for name in entries:
            if not name.startswith("mudae-frozen-update-"):
                continue
            stage_dir = os.path.join(base_path, name)
            if not os.path.isdir(stage_dir):
                continue
            payload = _load_frozen_payload(os.path.join(stage_dir, "update_payload.json"))
            if payload and payload.get("pid") and _is_pid_alive(int(payload["pid"])):
                actions.append("skipped {} (originating process still alive)".format(name))
                continue
            if payload:
                actions.extend(_recover_frozen_swap(payload))
            try:
                shutil.rmtree(stage_dir)
                actions.append("removed leftover staging directory {}".format(name))
            except OSError as exc:
                actions.append("could not remove {}: {}".format(name, exc))

        # Stale executable backups are only safe to delete when the live
        # executable exists beside them (the swap finished installing).
        backup_root = ""
        if executable and os.path.isfile(str(executable)):
            backup_root = os.path.abspath(str(executable))
        if backup_root:
            backup_dir = os.path.dirname(backup_root)
            backup_prefix = os.path.basename(backup_root) + "."
            try:
                candidates = sorted(os.listdir(backup_dir))
            except OSError:
                candidates = []
            for name in candidates:
                if not name.startswith(backup_prefix) or not name.endswith(".bak"):
                    continue
                middle = name[len(backup_prefix):-len(".bak")]
                if not middle.isdigit():
                    continue
                try:
                    os.remove(os.path.join(backup_dir, name))
                    actions.append("removed stale executable backup {}".format(name))
                except OSError:
                    pass
    except Exception as exc:  # cleanup must never block startup
        actions.append("cleanup aborted: {}".format(exc))
    return actions


def _replace_transactionally(base_path, stage_dir, relative_paths):
    lock_path = os.path.join(base_path, "update_transaction.lock")
    journal_path = os.path.join(base_path, "update_journal.json")
    with _ExclusiveLock(lock_path):
        if os.path.isfile(journal_path):
            if not _recover_interrupted_update_locked(base_path, journal_path):
                raise UpdateError("Cannot apply update: prior interrupted update recovery failed and preserved its backup.")
        return _replace_transactionally_locked(base_path, stage_dir, relative_paths)


def _replace_transactionally_locked(base_path, stage_dir, relative_paths):
    backup_dir = tempfile.mkdtemp(prefix="mudae-backup-", dir=base_path)
    journal_path = os.path.join(base_path, "update_journal.json")
    replaced = []
    created = []
    _write_journal(journal_path, {"backup_dir": backup_dir, "replaced": replaced, "created": created, "pid": os.getpid()})

    try:
        for relative_path in relative_paths:
            source = os.path.join(stage_dir, relative_path)
            destination = os.path.join(base_path, relative_path)
            backup = os.path.join(backup_dir, relative_path)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if os.path.exists(destination):
                os.makedirs(os.path.dirname(backup), exist_ok=True)
                shutil.copyfile(destination, backup)
                replaced.append(relative_path)
            else:
                created.append(relative_path)
            # Write-ahead logging: record replacement in journal before replacing
            _write_journal(journal_path, {"backup_dir": backup_dir, "replaced": replaced, "created": created, "pid": os.getpid()})
            os.replace(source, destination)
    except Exception as exc:
        rollback_errors = []
        for relative_path in reversed(replaced):
            destination = os.path.join(base_path, relative_path)
            backup = os.path.join(backup_dir, relative_path)
            try:
                if os.path.exists(backup):
                    shutil.copyfile(backup, destination)
            except OSError as err:
                rollback_errors.append((relative_path, str(err)))
        for relative_path in created:
            destination = os.path.join(base_path, relative_path)
            try:
                if os.path.exists(destination):
                    os.remove(destination)
            except OSError as err:
                rollback_errors.append((relative_path, str(err)))
        if rollback_errors:
            # Preserve backup directory and journal on rollback failure so files can be recovered manually
            raise UpdateError(
                "Update failed ({}) and rollback encountered errors (backup preserved at {!r}): {}".format(
                    exc, backup_dir, "; ".join(f"{p}: {e}" for p, e in rollback_errors)
                )
            ) from exc
        try:
            os.remove(journal_path)
        except OSError:
            pass
        else:
            shutil.rmtree(backup_dir, ignore_errors=True)
        raise
    else:
        try:
            os.remove(journal_path)
        except OSError:
            pass
        else:
            shutil.rmtree(backup_dir, ignore_errors=True)



def _stage_frozen_update(session, manifest, base_path, executable):
    lock_path = os.path.join(base_path, "update_frozen.lock")
    with _ExclusiveLock(lock_path):
        return _stage_frozen_update_locked(session, manifest, base_path, executable)


def _stage_frozen_update_locked(session, manifest, base_path, executable):
    payload_path = os.path.join(base_path, "update_payload.json")
    if os.path.isfile(payload_path):
        try:
            with open(payload_path, "r", encoding="utf-8") as h:
                p = json.load(h)
            if p.get("pid") and _is_pid_alive(p["pid"]):
                raise UpdateError("Another frozen update transaction (PID {}) is currently in progress.".format(p["pid"]))
        except (ValueError, OSError):
            pass

    install_lock_path = os.path.join(base_path, "update_frozen_install.lock")
    if os.path.isfile(install_lock_path):
        try:
            fd = os.open(install_lock_path, os.O_RDWR)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        except (OSError, IOError):
            raise UpdateError("Another frozen update installation is currently in progress.")

    helper_pid_file = os.path.join(base_path, "update_helper.pid")
    if os.path.isfile(helper_pid_file):
        try:
            with open(helper_pid_file, "r", encoding="utf-8") as h:
                h_pid = int(h.read().strip())
            if _is_pid_alive(h_pid):
                raise UpdateError("Another frozen update helper (PID {}) is currently in progress.".format(h_pid))
        except (ValueError, OSError):
            pass

    if not shutil.which("powershell"):
        raise UpdateError("Windows PowerShell 5.1+ is required to install frozen updates safely. Please install PowerShell or update from source.")

    url = manifest.get("exe_download_url")
    expected_hash = manifest.get("exe_sha256")
    if not url or not expected_hash:
        raise UpdateError("A verified executable is not available for this release.")
    content = _verified_download(session, url, expected_hash)

    # Isolated per-attempt staging directory ensures concurrent attempts never collide
    stage_dir = tempfile.mkdtemp(prefix="mudae-frozen-update-", dir=base_path)
    staged_exe = os.path.join(stage_dir, "MudaRemote_update.exe")
    with open(staged_exe, "wb") as handle:
        handle.write(content)

    executable = os.path.abspath(executable)
    payload = {
        "current": executable,
        "staged": os.path.abspath(staged_exe),
        "arguments": sys.argv[1:],
        "expected_hash": str(expected_hash).lower(),
        "pid": os.getpid(),
        "base_path": os.path.abspath(base_path),
        "stage_dir": os.path.abspath(stage_dir),
    }

    stage_payload_path = os.path.join(stage_dir, "update_payload.json")
    with open(stage_payload_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    ps_script_path = os.path.join(stage_dir, "update_helper.ps1")
    ps_content = (
        '# MudaRemote Frozen Update Helper\r\n'
        'param([string]$PayloadPath)\r\n'
        '$ErrorActionPreference = "Stop"\r\n'
        'try { Import-Module Microsoft.PowerShell.Utility -ErrorAction SilentlyContinue } catch {}\r\n'
        'if (-not (Test-Path -LiteralPath $PayloadPath)) { exit 1 }\r\n'
        '$payload = Get-Content -LiteralPath $PayloadPath -Raw | ConvertFrom-Json\r\n'
        '$current = $payload.current\r\n'
        '$staged = $payload.staged\r\n'
        '$expectedHash = $payload.expected_hash\r\n'
        '$parentPid = [int]$payload.pid\r\n'
        '$basePath = $payload.base_path\r\n'
        'function Get-Sha256([string]$filePath) {\r\n'
        '    $sha = [System.Security.Cryptography.SHA256]::Create()\r\n'
        '    $stream = [System.IO.File]::OpenRead($filePath)\r\n'
        '    $bytes = $sha.ComputeHash($stream)\r\n'
        '    $stream.Close()\r\n'
        '    $stream.Dispose()\r\n'
        '    $sha.Dispose()\r\n'
        '    return (-join ($bytes | ForEach-Object { "{0:x2}" -f $_ }))\r\n'
        '}\r\n'
        'function Format-WinArg([string]$arg) {\r\n'
        '    if ([string]::IsNullOrEmpty($arg)) { return \'""\' }\r\n'
        '    if ($arg -notmatch \'[\\s"]\') { return $arg }\r\n'
        '    $escaped = $arg -replace \'(\\\\*)(")\', \'$1$1\\\"\'\r\n'
        '    $escaped = $escaped -replace \'(\\\\+)$\', \'$1$1\'\r\n'
        '    return \'"\' + $escaped + \'"\'\r\n'
        '}\r\n'
        '$quotedArgs = @()\r\n'
        'if ($null -ne $payload.arguments) {\r\n'
        '    $quotedArgs = [string[]]($payload.arguments | ForEach-Object { Format-WinArg ([string]$_) })\r\n'
        '}\r\n'
        '$argString = $quotedArgs -join \' \'\r\n'
        'function Relaunch-Executable([string]$exePath) {\r\n'
        '    try {\r\n'
        '        if ($argString) {\r\n'
        '            Start-Process -FilePath $exePath -ArgumentList $argString -WorkingDirectory $basePath\r\n'
        '        } else {\r\n'
        '            Start-Process -FilePath $exePath -WorkingDirectory $basePath\r\n'
        '        }\r\n'
        '    } catch {}\r\n'
        '}\r\n'
        'Set-Content -LiteralPath (Join-Path $basePath "update_helper.pid") -Value $PID -Encoding Ascii\r\n'
        '$backup = $current + "." + $parentPid + ".bak"\r\n'
        '$deadline = (Get-Date).AddSeconds(30)\r\n'
        'while ((Get-Date) -lt $deadline) {\r\n'
        '    $proc = $null\r\n'
        '    try { $proc = Get-Process -Id $parentPid -ErrorAction SilentlyContinue } catch { $proc = $null }\r\n'
        '    if (-not $proc) { break }\r\n'
        '    Start-Sleep -Milliseconds 300\r\n'
        '}\r\n'
        'Start-Sleep -Milliseconds 500\r\n'
        '$installLockPath = Join-Path $basePath "update_frozen_install.lock"\r\n'
        '$lockStream = $null\r\n'
        '$lockDeadline = (Get-Date).AddSeconds(30)\r\n'
        'while ((Get-Date) -lt $lockDeadline) {\r\n'
        '    try {\r\n'
        '        $lockStream = [System.IO.File]::Open($installLockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)\r\n'
        '        break\r\n'
        '    } catch { Start-Sleep -Milliseconds 500 }\r\n'
        '}\r\n'
        'if ($null -eq $lockStream) {\r\n'
        '    exit 6\r\n'
        '}\r\n'
        '$moveSuccess = $false\r\n'
        '$retryDeadline = (Get-Date).AddSeconds(15)\r\n'
        'while ((Get-Date) -lt $retryDeadline) {\r\n'
        '    try {\r\n'
        '        if (Test-Path -LiteralPath $current) { Move-Item -LiteralPath $current -Destination $backup -Force }\r\n'
        '        $moveSuccess = $true\r\n'
        '        break\r\n'
        '    } catch { Start-Sleep -Milliseconds 500 }\r\n'
        '}\r\n'
        'if (-not $moveSuccess -and (Test-Path -LiteralPath $current)) {\r\n'
        '    if ($null -ne $lockStream) { $lockStream.Close(); $lockStream.Dispose() }\r\n'
        '    Relaunch-Executable $current\r\n'
        '    exit 2\r\n'
        '}\r\n'
        '$stagedMoved = $false\r\n'
        '$retryDeadline = (Get-Date).AddSeconds(10)\r\n'
        'while ((Get-Date) -lt $retryDeadline) {\r\n'
        '    try {\r\n'
        '        Move-Item -LiteralPath $staged -Destination $current -Force\r\n'
        '        $stagedMoved = $true\r\n'
        '        break\r\n'
        '    } catch { Start-Sleep -Milliseconds 500 }\r\n'
        '}\r\n'
        'if (-not $stagedMoved) {\r\n'
        '    if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $current -Force -ErrorAction SilentlyContinue }\r\n'
        '    if ($null -ne $lockStream) { $lockStream.Close(); $lockStream.Dispose() }\r\n'
        '    Relaunch-Executable $current\r\n'
        '    exit 3\r\n'
        '}\r\n'
        '$actualHash = (Get-Sha256 $current).ToLowerInvariant()\r\n'
        'if ($actualHash -ne $expectedHash) {\r\n'
        '    Remove-Item -LiteralPath $current -Force -ErrorAction SilentlyContinue\r\n'
        '    if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $current -Force -ErrorAction SilentlyContinue }\r\n'
        '    if ($null -ne $lockStream) { $lockStream.Close(); $lockStream.Dispose() }\r\n'
        '    Relaunch-Executable $current\r\n'
        '    exit 4\r\n'
        '}\r\n'
        'try {\r\n'
        '    if ($argString) {\r\n'
        '        Start-Process -FilePath $current -ArgumentList $argString -WorkingDirectory $basePath\r\n'
        '    } else {\r\n'
        '        Start-Process -FilePath $current -WorkingDirectory $basePath\r\n'
        '    }\r\n'
        '} catch {\r\n'
        '    Remove-Item -LiteralPath $current -Force -ErrorAction SilentlyContinue\r\n'
        '    if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $current -Force -ErrorAction SilentlyContinue }\r\n'
        '    if ($null -ne $lockStream) { $lockStream.Close(); $lockStream.Dispose() }\r\n'
        '    Relaunch-Executable $current\r\n'
        '    exit 5\r\n'
        '}\r\n'
        'if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue }\r\n'
        'if (Test-Path -LiteralPath $staged) { Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue }\r\n'
        'if (Test-Path -LiteralPath $PayloadPath) { Remove-Item -LiteralPath $PayloadPath -Force -ErrorAction SilentlyContinue }\r\n'
        'if ($null -ne $lockStream) { $lockStream.Close(); $lockStream.Dispose() }\r\n'
        'Remove-Item -LiteralPath (Join-Path $basePath "update_helper.pid") -Force -ErrorAction SilentlyContinue\r\n'
        '$stageDir = $payload.stage_dir\r\n'
        'if ($stageDir -and (Test-Path -LiteralPath $stageDir)) { Remove-Item -LiteralPath $stageDir -Recurse -Force -ErrorAction SilentlyContinue }\r\n'
        'Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue\r\n'
    )
    with open(ps_script_path, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(ps_content)

    batch_path = os.path.join(stage_dir, "update.bat")
    batch = (
        "@echo off\r\n"
        "setlocal\r\n"
        'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0update_helper.ps1" -PayloadPath "%~dp0update_payload.json"\r\n'
        "set PS_ERR=%ERRORLEVEL%\r\n"
        'del "%~f0" >nul 2>&1\r\n'
        "exit /b %PS_ERR%\r\n"
    )
    with open(batch_path, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(batch)

    return batch_path
def apply_update(session, manifest, current_version, base_path, frozen=False, executable=None, force=False):
    """Apply a newer verified update (or force a specific version). Return one of: current, git, source, frozen."""
    latest_version = manifest.get("version")
    if not latest_version or (not force and not is_newer_version(latest_version, current_version)):
        return "current"
    if frozen:
        batch_path = _stage_frozen_update(session, manifest, base_path, executable or sys.executable)
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([batch_path], creationflags=creation_flags, shell=True)
        return "frozen"

    if os.path.isdir(os.path.join(base_path, ".git")):
        return "git"

    os.makedirs(base_path, exist_ok=True)
    stage_dir = tempfile.mkdtemp(prefix="mudae-update-", dir=base_path)
    try:
        relative_paths = _stage_source_manifest(session, manifest, stage_dir)
        _replace_transactionally(base_path, stage_dir, relative_paths)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
    return "source"


def install_specific_version(session, version_or_tag, current_version, base_path, frozen=False, executable=None):
    """Fetch the manifest for a specific release version and apply it transactionally."""
    from .versioning import fetch_manifest_for_version
    manifest = fetch_manifest_for_version(session, version_or_tag)
    target_ver = manifest.get("version")
    if not target_ver:
        raise UpdateError(f"Could not load valid update manifest for version '{version_or_tag}'.")
    status = apply_update(
        session,
        manifest,
        current_version,
        base_path,
        frozen=frozen,
        executable=executable,
        force=True,
    )
    return status, manifest
