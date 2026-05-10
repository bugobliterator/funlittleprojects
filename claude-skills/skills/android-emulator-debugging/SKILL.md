---
name: android-emulator-debugging
description: Use when the user wants to run, see, or interact with an Android app on an emulator from the terminal. Triggers - "see what my app looks like", "boot the emulator", "install the APK and screenshot", "verify my layout/Compose/dialog renders right", "drive this UI flow", "walk through onboarding", "tap outside the dialog", "navigate to settings and screenshot". Covers any task where a screenshot of a running Android app answers the question - visual verification of XML/Compose UI, custom View rendering, dark mode, dialogs, bottom sheets, animations, theming, widgets on the launcher, multi-step flows, onboarding. Also covers scripted UI automation (taps, swipes, drags, text entry), inspecting device state (logcat, dumpsys, prefs), and the rebuild-install-screenshot loop via adb. Use whenever "let me see it on a phone" or "does this look right" applies to Android. Does not cover Gradle build failures, APK signing/release, or crash log analysis without a UI verification step.
---

# Android emulator debugging from the macOS CLI

This skill captures the working pattern for bringing up an Android emulator on a Mac, installing an app, driving its UI, and reasoning about the result — entirely from the terminal. The point is to get a fast, scriptable feedback loop where every change can be verified with a screenshot, without ever opening Android Studio.

It assumes Apple Silicon and zsh, but the commands all work the same on Intel (swap `arm64-v8a` for `x86_64` in the system image name).

## When this is the right approach

- You're iterating on UI code — XML layouts, Compose, custom Views, animations, drawables — and want to see results in seconds without leaving the terminal.
- You need to drive multi-step flows deterministically (login screens, onboarding wizards, dialog dismissals, settings toggles) where manual tapping is too slow or non-reproducible.
- You want screenshots in the conversation so you can actually reason about what's on screen — typography, alignment, dark-mode contrast, density-specific clipping.
- You're debugging device-side state (logs, shared prefs, content providers, widget options) without attaching a debugger.
- The thing you're testing involves the launcher (widgets, shortcuts, intent filters) where there's no other way to see it.

## Quick reference

Set env once per shell (skip if already set):
```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@17
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools:$PATH"
```

Boot an existing AVD headless and wait for it:
```bash
nohup emulator -avd <avd_name> -no-snapshot -no-audio -no-boot-anim -gpu swiftshader_indirect \
  > /tmp/emulator.log 2>&1 &
adb wait-for-device
until [[ "$(adb shell getprop sys.boot_completed | tr -d '\r')" == "1" ]]; do sleep 3; done
adb shell input keyevent 82  # dismiss keyguard
```

Install + launch + screenshot loop:
```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.example/.MainActivity
sleep 3
adb exec-out screencap -p > /tmp/shot.png
```

Then read `/tmp/shot.png` (the Read tool surfaces it as an image in the conversation).

## Setup (only if the dev environment is missing)

Check what's already installed first — the user may have Android Studio with a working SDK:
```bash
which adb && adb version | head -2
echo "ANDROID_HOME=$ANDROID_HOME"
ls -d ~/Library/Android/sdk 2>/dev/null
ls /opt/homebrew/share/android-commandlinetools 2>/dev/null
```

If nothing's there, install via Homebrew. This avoids the multi-GB Android Studio download and gives you a clean CLI-only setup. Be aware: this writes ~2 GB to disk total. Confirm with the user before kicking it off if you're not sure they want it.

```bash
brew install openjdk@17
brew install --cask android-commandlinetools
yes | sdkmanager --licenses > /dev/null
sdkmanager "platform-tools" \
           "platforms;android-34" \
           "build-tools;34.0.0" \
           "emulator" \
           "system-images;android-34;google_apis;arm64-v8a"
```

JDK 17 is required for AGP 8.5+. The `arm64-v8a` system image is the right one on Apple Silicon. Use `default` instead of `google_apis` if you don't need Play Services and want a smaller, faster image.

The system-image download is the slow part (~1 GB+). It writes to a `.temp/PackageOperation01/` directory before extracting; if you're polling progress, watch that folder rather than the final destination, which only gets populated at the end.

Create the AVD (one-time):
```bash
echo no | avdmanager create avd \
  -n claude_test \
  -k "system-images;android-34;google_apis;arm64-v8a" \
  --device "pixel_7" --force
```

`--force` clobbers an existing AVD by the same name — useful for resetting state, harmful if the user had something they cared about. Skip it on reuse.

## Booting the emulator

The emulator must keep running while you work, so launch it with `nohup ... &` and redirect stdout/stderr to a log. Don't try to keep an interactive emulator window in the same shell session.

```bash
nohup emulator -avd claude_test \
  -no-snapshot -no-audio -no-boot-anim -gpu swiftshader_indirect \
  > /tmp/emulator.log 2>&1 &
```

Useful flags:
- `-no-snapshot` — fresh boot every time. Slower, but state is predictable.
- `-no-audio` — skip audio init, faster boot, no warnings.
- `-no-boot-anim` — skip the boot animation (small win).
- `-gpu swiftshader_indirect` — software GPU. Slower than `host` but works in headless contexts and on machines without GL passthrough.

Boot is a two-stage thing: `adb wait-for-device` returns once `adbd` is up, but the OS may still be booting for another minute. The reliable signal is the `sys.boot_completed` system property:

```bash
adb wait-for-device
until [[ "$(adb shell getprop sys.boot_completed | tr -d '\r')" == "1" ]]; do sleep 3; done
adb shell input keyevent 82  # KEYCODE_MENU also dismisses the keyguard
```

Stop the emulator when done:
```bash
adb -s emulator-5554 emu kill
```

## Installing and launching

```bash
adb install -r path/to/app-debug.apk          # -r replaces existing install
adb shell am start -n com.example/.MainActivity
```

Component syntax: `<package>/<activity>`. Use `.ActivityName` (leading dot) as shorthand when the activity is in the package's root.

If an activity is `exported="false"`, `am start` from adb is rejected with a SecurityException. Either launch a parent activity and tap into it, or temporarily mark the activity exported during local development.

To send a broadcast to a specific receiver (e.g. trigger a widget refresh):
```bash
adb shell am broadcast -n com.example/.widget.MyProvider -a com.example.ACTION_REFRESH
```

The `-n` flag is critical: on Android 8+ many implicit broadcasts to manifest receivers are blocked, so always address the receiver by component.

To force-stop and relaunch (useful after editing only an activity):
```bash
adb shell am force-stop com.example
adb shell am start -n com.example/.MainActivity
```

## Driving the UI

The general pattern is: dump the UI tree, find the element you want by `text` or `resource-id`, parse its `bounds`, tap the center.

### Find an element by visible text

```bash
adb shell uiautomator dump /sdcard/dump.xml > /dev/null 2>&1
adb shell cat /sdcard/dump.xml | tr '>' '\n' | grep 'text="Use mock data"' | head -1
```

`tr '>' '\n'` puts each XML node on its own line so `grep` works cleanly. Each matching line has a `bounds="[X1,Y1][X2,Y2]"` attribute. To extract and tap:

```bash
BOUNDS=$(adb shell cat /sdcard/dump.xml | tr '>' '\n' \
  | grep 'text="Use mock data"' | head -1 \
  | grep -oE 'bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"')
read X1 Y1 X2 Y2 <<<"$(echo "$BOUNDS" | grep -oE '[0-9]+' | tr '\n' ' ')"
adb shell input tap $(( (X1+X2)/2 )) $(( (Y1+Y2)/2 ))
```

Filter by `resource-id` instead when text is dynamic — e.g. `grep 'resource-id="com.example:id/btn_save"'`.

### Long-press

`input swipe` with start == end and a long duration:
```bash
adb shell input swipe 540 1200 540 1200 1500   # 1.5s long-press
```

### Drag and drop

Important: `input swipe` with movement does **not** trigger drag-and-drop in launchers — it's a fling/scroll. For dragging widgets onto the home screen or rearranging icons, use `input draganddrop`:

```bash
adb shell input draganddrop $START_X $START_Y $END_X $END_Y 2500
```

The duration matters: too short and the launcher won't recognize it as a drag.

### Type text into the focused field

```bash
adb shell input text "hello%sworld"   # %s = space
adb shell input keyevent 66           # KEYCODE_ENTER
```

`%`, `&`, single/double quotes need careful shell escaping. For passwords with special chars, prefer pasting via `cmd inputmethod` or a clipboard-paste approach.

### Common keyevents

| Code | Name | Use |
|---|---|---|
| 3 | KEYCODE_HOME | Go to home screen |
| 4 | KEYCODE_BACK | System back |
| 66 | KEYCODE_ENTER | Submit/newline |
| 82 | KEYCODE_MENU | Dismiss keyguard, open menu |

Names also work: `adb shell input keyevent KEYCODE_HOME`.

### Adding a widget to the home screen (Pixel launcher)

The cleanest path on stock Pixel launcher:

```bash
# 1. Go home
adb shell input keyevent KEYCODE_HOME

# 2. Long-press an empty area (1.5s)
adb shell input swipe 540 1200 540 1200 1500

# 3. Tap the "Widgets" option (find via uiautomator dump → bounds)
# 4. Tap your widget's row to expand the preview
# 5. draganddrop the preview onto the home screen
adb shell input draganddrop 540 1110 540 1500 2500
```

If your widget has a configure activity, this triggers it; tap "Done" (or whatever Save button you have) to commit. Then `KEYCODE_HOME` returns to the home screen with the widget placed.

This sequence is fragile across launcher versions — Samsung One UI, Nova, etc. all differ. The Pixel emulator with the default Pixel launcher follows the steps above.

## Capturing screenshots

```bash
adb exec-out screencap -p > /tmp/shot.png
```

**Always use `exec-out`, not `shell`.** `adb shell` mangles `\r\n` line endings on the wire and corrupts binary data. `exec-out` is binary-safe.

Read the file with the Read tool — it renders as an image inline in the conversation. Don't try to view via shell tools, you'll just get bytes.

## Inspecting device state

### Filtered logcat

Always clear before reproducing, then dump after:
```bash
adb logcat -c
# trigger the action
adb logcat -d -s YourTag:D -t 50 | tail -20
```

`-d` = dump and exit (vs streaming `-f`). `-s YourTag:D` filters to one tag at level D and above. `-t 50` limits to last 50 lines.

For systemwide errors only:
```bash
adb logcat -d -t 200 *:E | tail -30
```

When debugging your own code, prefix log tags with something distinctive (e.g. `WIDGET-DBG`) so you can grep without picking up framework noise. The CLAUDE.md convention of "label your debug prints so they're easy to remove later" pairs well with this.

### Foreground activity / activity stack

```bash
adb shell dumpsys activity activities | grep topResumedActivity
adb shell dumpsys activity activities | grep -E "(topResumedActivity|mResumed|Hist)" | head -10
```

### Widget state

```bash
adb shell dumpsys appwidget | grep -B 2 -A 8 "<your-package>"
```

Shows provider info (min/max sizes, resize mode) and host info. The actual size the launcher passed to the widget lives in the per-id `getAppWidgetOptions` bundle, which isn't shown here — instrument your provider to log `OPTION_APPWIDGET_MIN_WIDTH` etc. to see those.

### App-private data

```bash
adb shell run-as com.example.app ls files/
adb shell run-as com.example.app cat shared_prefs/main.xml
adb shell run-as com.example.app sqlite3 databases/x.db ".tables"
```

`run-as` requires a debuggable APK (your debug build is). `EncryptedSharedPreferences` are not readable this way — they're encrypted with a Keystore-backed master key. Read those values from inside the app and `Log.d` what you need.

## The fast iteration loop

```bash
./gradlew assembleDebug \
  && adb install -r app/build/outputs/apk/debug/app-debug.apk \
  && adb shell am broadcast -n com.example/.widget.MyProvider -a com.example.ACTION_REFRESH \
  && sleep 3 \
  && adb exec-out screencap -p > /tmp/shot.png
```

Read `/tmp/shot.png`, decide what's wrong, edit, run again. Each cycle is typically 5-15s once the emulator is warm.

For widget work: once the widget is on the home screen, you don't need to re-add it — broadcasting your refresh action triggers a re-render. For activity work: `force-stop` then `am start` to pick up code changes.

## Gotchas worth remembering

These are the ones that actually wasted real time:

**Manifest receivers don't get implicit broadcasts on Android 8+.** `am broadcast -a com.example.ACTION` may complete with `result=0` and never fire your receiver. Always send to the specific component: `am broadcast -n com.example/.MyReceiver -a ...`.

**`input swipe` with movement is a flick, not a drag.** It scrolls views. For drag-and-drop (e.g. moving widgets onto a launcher), use `input draganddrop` with a generous duration (2000-2500ms).

**`adb wait-for-device` is necessary but not sufficient.** It returns when adbd is up, which is well before the OS finishes booting. Always poll `getprop sys.boot_completed` in addition.

**WebView won't fire `onPageFinished` for SPA navigation.** Apps like claude.ai navigate via the History API after login; your `WebViewClient` callback never sees it. Add a periodic cookie/state poll while the WebView activity is alive (every 2s in a `lifecycleScope` coroutine), and provide a manual "Done" button as a backup.

**Google OAuth is silently blocked in embedded WebViews.** Google detects WebView (since 2021) and won't sign the user in — they end up on a blank page or redirected back to login. Always offer email/magic-link as an alternate path, plus a "paste link from clipboard" feature so they can complete OAuth in a real browser and bring the auth URL back.

**Widget bitmap is letterboxed inside the cell.** `getAppWidgetOptions(id)` returns four dp values: `MIN_WIDTH`, `MIN_HEIGHT`, `MAX_WIDTH`, `MAX_HEIGHT`. These bracket sizes across orientations. For portrait, the actual cell ≈ `MIN_WIDTH × MAX_HEIGHT`. Render your bitmap at exactly that dp pair and `scaleType="fitCenter"` will fill the cell with no empty borders.

**`adb shell screencap > out.png` produces a corrupted image.** `adb shell` mangles binary data. Always use `adb exec-out screencap -p > out.png`.

**`am start` of an `exported="false"` activity is rejected.** Launch a parent activity and tap into it via UI automation, or — for development only — temporarily mark the activity exported.

## Debugging mindset

When a screenshot doesn't show what you expect, the question is: *did the code not run, or did it run and produce something different?* Distinguish them before guessing:

1. **Did the activity launch?** `adb shell dumpsys activity activities | grep topResumedActivity` shows what's actually on top.
2. **Did your code path execute?** Add a `Log.d("WIDGET-DBG", ...)` and check `adb logcat -d -s WIDGET-DBG:D` after triggering. Silence here means the path didn't run.
3. **Did you build what you think you built?** `adb shell pm dump com.example | grep versionName` shows the installed version. `gradle assembleDebug` outputs an APK timestamp; verify it post-dates your edit.
4. **Is the screenshot fresh?** Rendering can lag for a few hundred ms after a broadcast. `sleep 2-3` between trigger and screencap.

When in doubt: clear logcat (`adb logcat -c`), trigger the action, dump immediately. Empty logs are a real signal — they mean your code never ran.
