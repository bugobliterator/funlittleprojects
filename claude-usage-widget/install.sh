#!/usr/bin/env bash
# Builds the debug APK and installs it on the connected Android device.
# Requires: openjdk@17 + android-commandlinetools (already installed by setup).
set -euo pipefail

cd "$(dirname "$0")/android"

export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export PATH="$JAVA_HOME/bin:$PATH"

if ! adb devices | awk 'NR>1 && $2=="device" {found=1} END {exit !found}'; then
  echo "No Android device in 'device' state. Plug in the Pixel, allow USB debugging on the device, then rerun."
  echo
  echo "Currently visible:"
  adb devices
  exit 1
fi

./gradlew installDebug

echo
echo "Done. On your Pixel:"
echo "  1) Long-press the home screen → Widgets"
echo "  2) Find 'Claude Usage' and drag onto a screen"
echo "  3) Tap the widget → 'Log in to Claude' → sign in"
