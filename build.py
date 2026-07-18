"""
MudaRemote Build Script
Compiles mudae_preset_editor.py into a standalone .exe using PyInstaller.

Usage:
    python build.py                   # Default: --onedir build
    python build.py --onefile          # Single-file build
    python build.py --console          # Build with console window visible
    python build.py --onefile --console
"""

import sys
import os
import argparse


def build(onefile=False, console=False):
    """Run PyInstaller to compile MudaRemote."""
    try:
        import PyInstaller.__main__
    except ImportError:
        print("[BUILD] PyInstaller not found. Installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        import PyInstaller.__main__

    script_dir = os.path.dirname(os.path.abspath(__file__))
    entry_point = os.path.join(script_dir, "mudae_preset_editor.py")
    icon_path = os.path.join(script_dir, "icon.png")
    spec_dir = os.path.join(script_dir, "build", "spec")
    os.makedirs(spec_dir, exist_ok=True)

    if not os.path.exists(entry_point):
        print(f"[BUILD] ERROR: {entry_point} not found.")
        sys.exit(1)

    args = [
        entry_point,
        "--noconfirm",
        "--name=MudaRemote",
        f"--specpath={spec_dir}",
        # Include mudae_bot.py as hidden import so the exe contains all bot logic
        "--hidden-import=mudae_bot",
        # Core dependencies that PyInstaller might miss
        "--hidden-import=requests",
        "--hidden-import=discord",
        "--hidden-import=discord.ext.commands",
        "--hidden-import=inquirer",
        # Collect all discord.py data files (certs, etc.)
        "--collect-all=discord",
    ]

    # Build mode
    if onefile:
        args.append("--onefile")
        print("[BUILD] Mode: Single file (.exe)")
    else:
        args.append("--onedir")
        print("[BUILD] Mode: Directory (faster startup)")

    args.extend([
        "--collect-submodules=mudae_core",
        "--hidden-import=keyring",
    ])

    # Window mode
    # IMPORTANT: We MUST use --console (not --windowed) because the exe needs to be
    # able to spawn visible console windows for headless bot mode (--preset).
    # A --windowed (GUI subsystem) exe cannot create consoles via CREATE_NEW_CONSOLE.
    # The console is hidden programmatically via ctypes when launching the GUI.
    if console:
        args.append("--console")
        print("[BUILD] Window: Console (always visible)")
    else:
        args.append("--console")
        print("[BUILD] Window: Console (hidden automatically in GUI mode)")

    # Icon
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
        print(f"[BUILD] Output: dist/MudaRemote.exe")
    else:
        print(f"[BUILD] Output: dist/MudaRemote/MudaRemote.exe")
    print("[BUILD] Make sure presets.json is in the same directory as the .exe when running.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build MudaRemote into a standalone .exe")
    parser.add_argument("--onefile", action="store_true", help="Build as a single .exe file (slower startup)")
    parser.add_argument("--console", action="store_true", help="Show console window (useful for debugging)")
    args = parser.parse_args()

    build(onefile=args.onefile, console=args.console)
