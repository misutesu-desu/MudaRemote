"""Verified, manifest-based updater for both source and frozen builds."""

import hashlib
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

from .versioning import is_newer_version


class UpdateError(RuntimeError):
    pass


# Keep startup failures short. ``requests`` applies these as separate connect
# and read-idle limits, including redirected GitHub release downloads.
UPDATE_DOWNLOAD_TIMEOUT = (5.0, 20.0)
PROTECTED_UPDATE_PATHS = {"presets.json"}


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


def sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def _download(session, url, timeout):
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def _validate_relative_path(relative_path):
    normalized = os.path.normpath(str(relative_path).replace("/", os.sep))
    if os.path.isabs(normalized) or normalized == os.pardir or normalized.startswith(os.pardir + os.sep):
        raise UpdateError("Unsafe update path: {!r}".format(relative_path))
    return normalized


def _verified_download(session, url, expected_hash, timeout=UPDATE_DOWNLOAD_TIMEOUT):
    if not expected_hash:
        raise UpdateError("The update manifest is missing a SHA-256 checksum.")
    content = _download(session, url, timeout)
    actual_hash = sha256_bytes(content)
    if actual_hash.lower() != str(expected_hash).lower():
        raise UpdateError("SHA-256 verification failed for {}.".format(url))
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
        if relative_path in seen_paths:
            raise UpdateError("The source_files manifest contains a duplicate path: {}.".format(relative_path))
        seen_paths.add(relative_path)
        target_path = os.path.join(stage_dir, relative_path)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        content = _verified_download(session, entry.get("url"), entry.get("sha256"))
        with open(target_path, "wb") as handle:
            handle.write(content)
        staged_paths.append(relative_path)

    required = {"mudae_bot.py", "mudae_preset_editor.py", os.path.join("mudae_core", "__init__.py")}
    if not required.issubset(set(staged_paths)):
        raise UpdateError("The source manifest is incomplete; update was not applied.")

    for relative_path in staged_paths:
        if relative_path.endswith(".py"):
            py_compile.compile(os.path.join(stage_dir, relative_path), doraise=True)
    return staged_paths


def _replace_transactionally(base_path, stage_dir, relative_paths):
    backup_dir = tempfile.mkdtemp(prefix="mudae-backup-", dir=base_path)
    replaced = []
    try:
        for relative_path in relative_paths:
            source = os.path.join(stage_dir, relative_path)
            destination = os.path.join(base_path, relative_path)
            backup = os.path.join(backup_dir, relative_path)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if os.path.exists(destination):
                os.makedirs(os.path.dirname(backup), exist_ok=True)
                shutil.copy2(destination, backup)
            os.replace(source, destination)
            replaced.append(relative_path)
    except Exception:
        for relative_path in reversed(replaced):
            destination = os.path.join(base_path, relative_path)
            backup = os.path.join(backup_dir, relative_path)
            try:
                if os.path.exists(backup):
                    os.replace(backup, destination)
                elif os.path.exists(destination):
                    os.remove(destination)
            except OSError:
                pass
        raise
    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)


def _stage_frozen_update(session, manifest, base_path, executable):
    url = manifest.get("exe_download_url")
    expected_hash = manifest.get("exe_sha256")
    if not url or not expected_hash:
        raise UpdateError("A verified executable is not available for this release.")
    content = _verified_download(session, url, expected_hash)
    staged_exe = os.path.join(base_path, "MudaRemote_update.exe")
    with open(staged_exe, "wb") as handle:
        handle.write(content)

    executable = os.path.abspath(executable)
    arguments = subprocess.list2cmdline(sys.argv[1:])
    batch_path = os.path.join(base_path, "update.bat")
    batch = (
        "@echo off\r\n"
        "timeout /t 3 /nobreak >nul\r\n"
        "del /f /q \"{current}\"\r\n"
        "move /y \"{staged}\" \"{current}\" >nul\r\n"
        "start \"\" \"{current}\" {arguments}\r\n"
        "del \"%~f0\"\r\n"
    ).format(current=executable, staged=staged_exe, arguments=arguments)
    with open(batch_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(batch)
    return batch_path


def apply_update(session, manifest, current_version, base_path, frozen=False, executable=None):
    """Apply a newer verified update. Return one of: current, git, source, frozen."""
    latest_version = manifest.get("version")
    if not latest_version or not is_newer_version(latest_version, current_version):
        return "current"

    if frozen:
        batch_path = _stage_frozen_update(session, manifest, base_path, executable or sys.executable)
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([batch_path], creationflags=creation_flags, shell=True)
        return "frozen"

    if os.path.isdir(os.path.join(base_path, ".git")):
        return "git"

    stage_dir = tempfile.mkdtemp(prefix="mudae-update-", dir=base_path)
    try:
        relative_paths = _stage_source_manifest(session, manifest, stage_dir)
        _replace_transactionally(base_path, stage_dir, relative_paths)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
    return "source"
