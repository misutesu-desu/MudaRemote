#!/usr/bin/env bash
# Runs inside the CI emulator job: installs the debug APK, walks the main screen top to bottom
# and saves screenshots (plus frame and memory dumps) into ./screens.
#
# Usage: bash android/scripts/screens.sh <apk path> [package]
#
# Best effort: a missed tap or a failed walk never fails the run; the run fails only when no
# screenshot at all was produced. It never needs a Discord token (the app shows "no token").
set -u

APK="${1:?apk path required}"
PKG="${2:-com.mudafork.android}"
ACTIVITY="com.mudaremote.android.MainActivity"
OUT="${SCREENS_DIR:-screens}"
MAX_SHOTS=14

mkdir -p "$OUT"

log() { echo "[screens] $*"; }

# ---------------------------------------------------------------- device helpers

W=1080
H=2400

measure_screen() {
  local size
  size="$(adb shell wm size 2>/dev/null | tr -d '\r' | sed -n 's/.*: *\([0-9]*\)x\([0-9]*\).*/\1 \2/p' | tail -n 1)"
  if [ -n "$size" ]; then
    W="${size% *}"
    H="${size#* }"
  fi
  log "screen ${W}x${H}"
}

shot() {
  # $1 = output file
  adb exec-out screencap -p > "$1" 2>/dev/null
  if [ ! -s "$1" ]; then rm -f "$1"; log "screencap failed for $1"; return 1; fi
  return 0
}

launch_app() {
  adb shell am force-stop "$PKG" >/dev/null 2>&1
  sleep 1
  adb shell am start -W -n "$PKG/$ACTIVITY" >/dev/null 2>&1
  wait_for_render
}

# First render = the "Profiles" card title is on screen (or give up after ~60 s and go on).
wait_for_render() {
  local i
  for i in $(seq 1 30); do
    if ui_dump | grep -q 'text="Profiles"'; then
      log "first render after about $((i * 2)) s"
      sleep 2
      return 0
    fi
    sleep 2
  done
  log "first render not confirmed; continuing"
  return 1
}

ui_dump() {
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1
  adb exec-out cat /sdcard/ui.xml 2>/dev/null
}

swipe_up() {   # content moves up: about 70% of the screen
  adb shell input swipe $((W / 2)) $((H * 78 / 100)) $((W / 2)) $((H * 8 / 100)) 450 >/dev/null 2>&1
}

swipe_down() {
  adb shell input swipe $((W / 2)) $((H * 20 / 100)) $((W / 2)) $((H * 80 / 100)) 250 >/dev/null 2>&1
}

scroll_top() {
  local i
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do swipe_down; done
  sleep 1
}

# Print "x y" of the visible node whose text is exactly $1 (topmost one, never under the dock).
find_text() {
  ui_dump | python3 -I -c '
import re, sys
xml = sys.stdin.read()
want, height = sys.argv[1], int(sys.argv[2])
best = None
for m in re.finditer(r"<node [^>]*>", xml):
    node = m.group(0)
    t = re.search(r" text=\"([^\"]*)\"", node)
    if not t or t.group(1) != want:
        continue
    b = re.search(r"bounds=\"\[(\d+),(\d+)\]\[(\d+),(\d+)\]\"", node)
    if not b:
        continue
    x1, y1, x2, y2 = map(int, b.groups())
    cy = (y1 + y2) // 2
    if cy <= 0 or cy > height * 88 // 100:
        continue
    if best is None or cy < best[1]:
        best = ((x1 + x2) // 2, cy)
if best:
    print("%d %d" % best)
' "$1" "$H"
}

# Tap the text $1; scrolls down up to 8 times looking for it. Returns 1 when it was not found.
tap_text() {
  local pos tries=0
  while [ "$tries" -le 8 ]; do
    pos="$(find_text "$1")"
    if [ -n "$pos" ]; then
      adb shell input tap $pos >/dev/null 2>&1
      sleep 1.5
      return 0
    fi
    swipe_up
    sleep 0.8
    tries=$((tries + 1))
  done
  log "text not found: $1"
  return 1
}

# ---------------------------------------------------------------- the walk

walk() {
  # $1 = file prefix (fs100, fs130, rtl)
  local prefix="$1" i file sum prev=""
  scroll_top
  for i in $(seq 1 "$MAX_SHOTS"); do
    file="$(printf '%s/%s-%02d.png' "$OUT" "$prefix" "$i")"
    shot "$file" || break
    sum="$(md5sum < "$file" | cut -d' ' -f1)"
    if [ "$sum" = "$prev" ]; then
      rm -f "$file"          # the screen did not move: the bottom was reached
      break
    fi
    prev="$sum"
    swipe_up
    sleep 0.8
  done
  log "walk $prefix done: $(ls "$OUT" | grep -c "^$prefix-") shots"
}

# ---------------------------------------------------------------- main

adb wait-for-device
adb shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1
adb shell wm dismiss-keyguard >/dev/null 2>&1
# Phone-like screen: 1080 x 2400 at 420 dpi.
adb shell wm size 1080x2400 >/dev/null 2>&1
adb shell wm density 420 >/dev/null 2>&1
adb shell settings put system font_scale 1.0 >/dev/null 2>&1
adb shell settings put global debug.force_rtl 0 >/dev/null 2>&1
measure_screen

log "installing $APK"
if ! adb install -r -g "$APK"; then
  log "install failed"
  exit 1
fi
adb shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS >/dev/null 2>&1

launch_app

# 1) normal font
walk fs100

# 2) header action «Keep running», then one dialog (Rename on a profile)
scroll_top
if tap_text "Keep running"; then
  shot "$OUT/keep-running-tap.png" || true
fi
scroll_top
if tap_text "Rename"; then
  shot "$OUT/dialog-rename.png" || true
  adb shell input keyevent KEYCODE_BACK >/dev/null 2>&1
  sleep 1
fi

# 3) frame statistics for a scripted scroll down and up, then memory
adb shell dumpsys gfxinfo "$PKG" reset >/dev/null 2>&1
scroll_top
for i in 1 2 3 4 5 6; do swipe_up; sleep 0.3; done
for i in 1 2 3 4 5 6; do swipe_down; sleep 0.3; done
adb shell dumpsys gfxinfo "$PKG" framestats > "$OUT/gfx.txt" 2>&1
adb shell dumpsys meminfo "$PKG" > "$OUT/mem.txt" 2>&1

# 4) large system font
adb shell settings put system font_scale 1.3 >/dev/null 2>&1
sleep 2
launch_app
walk fs130
scroll_top
if tap_text "Keep running"; then
  shot "$OUT/fs130-keep-running-tap.png" || true
fi
adb shell settings put system font_scale 1.0 >/dev/null 2>&1

# 5) right-to-left layout
adb shell settings put global debug.force_rtl 1 >/dev/null 2>&1
sleep 2
launch_app
walk rtl
adb shell settings put global debug.force_rtl 0 >/dev/null 2>&1

# restore the emulator
adb shell wm size reset >/dev/null 2>&1
adb shell wm density reset >/dev/null 2>&1

COUNT="$(find "$OUT" -maxdepth 1 -name '*.png' | wc -l)"
log "$COUNT screenshots in $OUT"
ls -l "$OUT"
if [ "$COUNT" -eq 0 ]; then
  log "no screenshot was produced"
  exit 1
fi
exit 0
