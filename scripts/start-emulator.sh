#!/usr/bin/env bash
set -euo pipefail

STATE_ROOT="${SCREENSHOT_SHIELD_STATE_DIR:-$HOME/Library/Application Support/ScreenshotShield}"
SDK_ROOT="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
EMULATOR="$SDK_ROOT/emulator/emulator"
ADB="$SDK_ROOT/platform-tools/adb"

if [[ ! -x "$EMULATOR" || ! -f "$STATE_ROOT/emulator/ramdisk.img" ]]; then
    printf '%s\n' 'Missing emulator SDK or prepared Magisk ramdisk.' >&2
    exit 1
fi
if "$ADB" -s emulator-5584 get-state >/dev/null 2>&1; then
    name="$("$ADB" -s emulator-5584 emu avd name | tr -d '\r' | head -n 1)"
    if [[ "$name" == "ScreenshotShield_API36" ]]; then
        printf '%s\n' 'ScreenshotShield emulator is already running on emulator-5584.'
        exit 0
    fi
    printf '%s\n' 'Port 5584 belongs to another emulator; leave it untouched.' >&2
    exit 1
fi
exec "$EMULATOR" -avd ScreenshotShield_API36 -ports 5584,5585 \
    -ramdisk "$STATE_ROOT/emulator/ramdisk.img" -no-audio -no-snapshot \
    -no-boot-anim -gpu swiftshader_indirect -memory 2048 "$@"
