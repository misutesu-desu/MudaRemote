"""
MudaRemote Build Script
Compiles mudae_preset_editor.py into a standalone .exe using PyInstaller.

Usage:
    python build.py                   # Default: --onedir build
    python build.py --onefile          # Single-file build
    python build.py --console          # Build with console window visible
    python build.py --onefile --console
"""

import argparse
import hashlib
import os
import sys


def build(onefile=False, console=False):
    """Run PyInstaller to compile MudaRemote."""
    try:
        import PyInstaller.__main__
    except ImportError:
        print("[BUILD] ERROR: PyInstaller is not installed.")
        print("[BUILD] Install the pinned build dependencies with:")
        print(f"[BUILD]   {sys.executable} -m pip install -r requirements-dev.txt")
        sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    entry_point = os.path.join(script_dir, "mudae_preset_editor.py")
    icon_path = os.path.join(script_dir, "icon.png")
    release_spec = os.path.join(script_dir, "MudaRemote.spec")
    version_file = os.path.join(script_dir, "packaging", "windows_version_info.txt")
    spec_dir = os.path.join(script_dir, "build", "spec")
    os.makedirs(spec_dir, exist_ok=True)

    if not os.path.exists(entry_point):
        print(f"[BUILD] ERROR: {entry_point} not found.")
        sys.exit(1)

    if onefile:
        # The checked-in spec is the canonical release definition. Keeping CI,
        # local builds, metadata and antivirus-hardening flags in one place
        # prevents different machines from silently producing different layouts.
        args = [release_spec, "--noconfirm", "--clean"]
        print("[BUILD] Mode: Single file (.exe)")
    else:
        args = [
            entry_point,
            "--noconfirm",
            "--clean",
            "--noupx",
            "--name=MudaRemote",
            f"--specpath={spec_dir}",
            "--onedir",
            # Include mudae_bot.py as hidden import so the bundle contains all bot logic.
            "--hidden-import=mudae_bot",
            "--hidden-import=requests",
            "--hidden-import=discord",
            "--hidden-import=discord.ext.commands",
            "--hidden-import=discord.http",
            "--hidden-import=inquirer",
            "--collect-submodules=mudae_core",
            "--hidden-import=keyring",
            f"--version-file={version_file}",
        ]
        print("[BUILD] Mode: Directory (faster startup)")

    if onefile:
        print("[BUILD] Window and icon settings: MudaRemote.spec")
    else:
        # IMPORTANT: We MUST use --console (not --windowed) because the exe needs to
        # spawn visible console windows for headless bot mode (--preset).
        # The console is hidden programmatically via ctypes when launching the GUI.
        args.append("--console")
        if console:
            print("[BUILD] Window: Console (always visible)")
        else:
            print("[BUILD] Window: Console (hidden automatically in GUI mode)")

        if os.path.exists(icon_path):
            args.append(f"--icon={icon_path}")
            print(f"[BUILD] Icon: {icon_path}")
        else:
            print(f"[BUILD] WARNING: icon.png not found at {icon_path}, building without icon.")

    print(f"\n[BUILD] Starting PyInstaller...\n{'='*60}")
    print(f"[BUILD] Command: pyinstaller {' '.join(args)}\n")

    PyInstaller.__main__.run(args)

    print(f"\n{'='*60}")
    print("[BUILD] Build complete!")
    if onefile:
        output_path = os.path.join(script_dir, "dist", "MudaRemote.exe")
    else:
        output_path = os.path.join(script_dir, "dist", "MudaRemote", "MudaRemote.exe")
    print(f"[BUILD] Output: {output_path}")
    if os.path.isfile(output_path):
        with open(output_path, "rb") as executable:
            digest = hashlib.sha256(executable.read()).hexdigest()
        print(f"[BUILD] SHA256: {digest}")
    print("[BUILD] Make sure presets.json is in the same directory as the .exe when running.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build MudaRemote into a standalone .exe")
    parser.add_argument("--onefile", action="store_true", help="Build as a single .exe file (slower startup)")
    parser.add_argument("--console", action="store_true", help="Show console window (useful for debugging)")
    args = parser.parse_args()

    build(onefile=args.onefile, console=args.console)
