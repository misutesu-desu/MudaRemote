import os
import sys

# Define relative paths of runtime source code and configuration files required for MudaRemote
RUNTIME_FILES = [
    "mudae_bot.py",
    "mudae_preset_editor.py",
    "build.py",
    "mudae_core/__init__.py",
    "mudae_core/claiming.py",
    "mudae_core/config.py",
    "mudae_core/coordinator.py",
    "mudae_core/kakera.py",
    "mudae_core/runtime.py",
    "mudae_core/secrets.py",
    "mudae_core/status.py",
    "mudae_core/updater.py",
    "mudae_core/versioning.py",
    "presets.example.json",
    "requirements.txt",
    "requirements-dev.txt",
    "version.json"
]

OUTPUT_FILENAME = "PROJECT_FULL_CONTEXT.md"


def main():
    # Force utf-8 encoding for stdout if possible
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # Resolve project root directory based on script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, OUTPUT_FILENAME)

    print(f"[+] Generating '{OUTPUT_FILENAME}' in: {script_dir}")

    total_files = 0
    with open(output_path, "w", encoding="utf-8") as out:
        out.write("# PROJECT RUNTIME CODE CONTEXT\n\n")
        out.write(
            "This document contains the complete, unabridged, verbatim runtime source code "
            "and configuration files required to run MudaRemote.\n\n"
        )

        for relative_path in RUNTIME_FILES:
            full_path = os.path.join(script_dir, relative_path)
            if os.path.exists(full_path):
                ext = os.path.splitext(relative_path)[1].lstrip(".")
                lang = "python" if ext == "py" else ("json" if ext == "json" else "")
                out.write(f"## File: `{relative_path}`\n\n")
                out.write(f"```{lang}\n")
                with open(full_path, "r", encoding="utf-8", errors="replace") as infile:
                    out.write(infile.read())
                out.write("\n```\n\n")
                total_files += 1
                print(f"  - Added: {relative_path}")
            else:
                print(f"  - Skipped (file not found): {relative_path}")

    file_size_kb = os.path.getsize(output_path) / 1024
    print(f"\n[OK] Success! Written {total_files} files into '{OUTPUT_FILENAME}' ({file_size_kb:.2f} KB).")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] Error generating context: {e}")

    # Keep terminal open if user double-clicked the .py file on Windows
    if sys.stdout.isatty():
        input("\nPress Enter to exit...")
