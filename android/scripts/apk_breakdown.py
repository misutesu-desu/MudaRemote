#!/usr/bin/env python3
"""Where the bytes of an APK go: a plain-text breakdown from ``unzip -lv``.

Usage:  python android/scripts/apk_breakdown.py <apk> [--top N]  > apk-breakdown.txt

Prints the APK's total size, then each top-level group sorted by compressed size
(largest first): lib/<abi>/ (every .so), assets/chaquopy/ (every file), classes*.dex,
res/ + resources.arsc, META-INF/, and everything else. Inside a group the files are
sorted by compressed size too. Sizes are bytes; "ratio" is compressed / uncompressed.
Only the standard library and the ``unzip`` program are used.
"""

import argparse
import os
import re
import subprocess
import sys

# unzip -lv:  Length   Method    Size  Cmpr    Date    Time   CRC-32   Name
LINE = re.compile(r"^\s*(\d+)\s+(\S+)\s+(\d+)\s+(-?\d+%)\s+\S+\s+\S+\s+[0-9a-fA-F]{8}\s+(.+?)\s*$")


def parse(text):
    """The (name, uncompressed, compressed) of every file entry in ``unzip -lv`` output."""
    entries = []
    for line in text.splitlines():
        match = LINE.match(line)
        if not match:
            continue
        name = match.group(5)
        if name.endswith("/"):
            continue
        entries.append((name, int(match.group(1)), int(match.group(3))))
    return entries


def group_of(name):
    """The group a path belongs to."""
    parts = name.split("/")
    if parts[0] == "lib" and len(parts) >= 3:
        return "lib/" + parts[1] + "/"
    if name.startswith("assets/chaquopy/"):
        return "assets/chaquopy/"
    if parts[0] == "assets":
        return "assets/ (other)"
    if re.match(r"^classes\d*\.dex$", name):
        return "classes*.dex"
    if parts[0] == "res" or name == "resources.arsc":
        return "res + resources.arsc"
    if parts[0] == "META-INF":
        return "META-INF/"
    return "other"


def build_report(entries, apk_size, top=15):
    groups = {}
    for name, raw, packed in entries:
        groups.setdefault(group_of(name), []).append((name, raw, packed))
    total_packed = sum(packed for _name, _raw, packed in entries)
    total_raw = sum(raw for _name, raw, _packed in entries)
    lines = [
        "APK size on disk: {:,} bytes".format(apk_size),
        "Entries: {:,}; compressed {:,} bytes; uncompressed {:,} bytes".format(len(entries), total_packed, total_raw),
        "",
    ]
    ordered = sorted(groups.items(), key=lambda item: -sum(packed for _n, _r, packed in item[1]))
    lines.append("Groups by compressed size")
    for label, files in ordered:
        packed = sum(item[2] for item in files)
        raw = sum(item[1] for item in files)
        share = 100.0 * packed / total_packed if total_packed else 0.0
        lines.append("  {:<26} {:>12,} compressed {:>12,} uncompressed {:>5.1f}%  {} file(s)".format(
            label, packed, raw, share, len(files)))
    for label, files in ordered:
        lines.append("")
        lines.append("{} ({:,} file(s))".format(label, len(files)))
        show = sorted(files, key=lambda item: (-item[2], item[0]))
        full = label.startswith("lib/") or label == "assets/chaquopy/" or label == "classes*.dex"
        for name, raw, packed in (show if full else show[:top]):
            ratio = 100.0 * packed / raw if raw else 100.0
            lines.append("  {:>12,} compressed {:>12,} uncompressed {:>5.1f}%  {}".format(packed, raw, ratio, name))
        if not full and len(show) > top:
            rest = sum(item[2] for item in show[top:])
            lines.append("  ... {:,} more file(s), {:,} bytes compressed".format(len(show) - top, rest))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("apk")
    parser.add_argument("--top", type=int, default=15, help="files shown for the groups that are not listed in full")
    args = parser.parse_args(argv)
    listing = subprocess.run(["unzip", "-lv", args.apk], check=True, capture_output=True, text=True).stdout
    sys.stdout.write(build_report(parse(listing), os.path.getsize(args.apk), args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
