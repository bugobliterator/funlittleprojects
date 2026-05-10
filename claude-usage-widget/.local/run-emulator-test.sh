#!/usr/bin/env bash
# Boots the emulator, installs the APK, drives ConfigActivity, captures screenshots.
set -euo pipefail

export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools:$PATH"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCREENSHOTS="$ROOT/screenshots"
mkdir -p "$SCREENSHOTS"

AVD=claude_widget_test

echo "==> Creating AVD if needed"
if ! avdmanager list avd 2>/dev/null | grep -q "Name: $AVD"; then
  echo no | avdmanager create avd \
    -n "$AVD" \
    -k "system-images;android-34;google_apis;arm64-v8a" \
    --device "pixel_7" --force
fi

echo "==> Booting emulator (headless)"
nohup emulator -avd "$AVD" -no-snapshot -no-audio -no-boot-anim -gpu swiftshader_indirect \
  > /tmp/emulator.log 2>&1 &
EMU_PID=$!
echo "emulator PID=$EMU_PID"

echo "==> Waiting for adb device"
adb wait-for-device

echo "==> Waiting for boot complete"
until [[ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; do
  sleep 2
done
sleep 3
adb shell input keyevent 82  # unlock

echo "==> Installing APK"
adb install -r "$ROOT/android/app/build/outputs/apk/debug/app-debug.apk"

echo "==> Launching ConfigActivity"
adb shell am start -n com.sidbh.claudeusage/.config.ConfigActivity
sleep 3
adb exec-out screencap -p > "$SCREENSHOTS/01-config-unconfigured.png"
echo "saved 01-config-unconfigured.png"

echo "==> Tapping 'Use mock data'"
adb shell uiautomator dump /sdcard/dump.xml >/dev/null 2>&1
DUMP=$(adb shell cat /sdcard/dump.xml)
BOUNDS=$(echo "$DUMP" | grep -oE 'text="Use mock data"[^/]*bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' | grep -oE 'bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' | head -1 || true)
if [[ -z "$BOUNDS" ]]; then
  echo "Could not find mock button via uiautomator. Falling back to fixed coordinates."
  CX=540; CY=920
else
  COORDS=$(echo "$BOUNDS" | grep -oE '[0-9]+' | tr '\n' ' ')
  X1=$(echo "$COORDS" | awk '{print $1}')
  Y1=$(echo "$COORDS" | awk '{print $2}')
  X2=$(echo "$COORDS" | awk '{print $3}')
  Y2=$(echo "$COORDS" | awk '{print $4}')
  CX=$(( (X1+X2)/2 ))
  CY=$(( (Y1+Y2)/2 ))
  echo "mock button center=($CX, $CY)"
fi
adb shell input tap "$CX" "$CY"

echo "==> Waiting for mock state to populate and render"
sleep 4
adb exec-out screencap -p > "$SCREENSHOTS/02-config-mock-preview.png"
echo "saved 02-config-mock-preview.png"

# Scroll down to see the preview if needed
echo "==> Scrolling to preview"
adb shell input swipe 540 1500 540 600 200
sleep 1
adb exec-out screencap -p > "$SCREENSHOTS/03-config-mock-preview-scrolled.png"
echo "saved 03-config-mock-preview-scrolled.png"

echo "==> Done. Emulator left running (PID=$EMU_PID). To stop:"
echo "    adb -s emulator-5554 emu kill"
