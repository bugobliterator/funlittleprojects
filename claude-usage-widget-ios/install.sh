#!/usr/bin/env bash
# Builds the iOS app + widget extension, installs to the connected device.
# Requires Xcode 16+ with a configured development team.
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v xcodegen >/dev/null 2>&1; then
  echo "xcodegen not found. Install with: brew install xcodegen"
  exit 1
fi

# Regenerate the .xcodeproj from project.yml so the source tree is canonical.
xcodegen generate

# Pick the first connected real iOS device (devicectl is Xcode 15+).
UDID=$(xcrun devicectl list devices 2>/dev/null \
  | awk '/connected\s+available/ {print $1; exit}')

if [[ -z "${UDID:-}" ]]; then
  echo "No connected real iOS device found. Plug in your iPhone, trust this Mac, then rerun."
  echo
  echo "Currently visible:"
  xcrun devicectl list devices || true
  exit 1
fi

echo "Building for device $UDID..."
xcodebuild -project ClaudeUsage.xcodeproj -scheme ClaudeUsage \
  -configuration Debug \
  -destination "id=$UDID" \
  -derivedDataPath build \
  build

APP_PATH=$(find build/Build/Products/Debug-iphoneos -maxdepth 2 -name "*.app" -type d | head -1)
if [[ -z "$APP_PATH" ]]; then
  echo "Could not find built .app under build/Build/Products/Debug-iphoneos"
  exit 1
fi

echo "Installing $APP_PATH to device..."
xcrun devicectl device install app --device "$UDID" "$APP_PATH"

echo
echo "Done. On your iPhone:"
echo "  1) Long-press the home screen → tap the + in the top-left"
echo "  2) Find 'Claude Usage' and add the medium widget"
echo "  3) Tap the widget → 'Log in to Claude' → sign in"
