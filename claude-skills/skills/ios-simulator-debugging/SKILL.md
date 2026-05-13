---
name: ios-simulator-debugging
description: Use when the user wants to run, see, or interact with an iOS app or widget on the iOS Simulator from the terminal. Triggers - "see what my iOS app looks like", "boot the simulator", "install the app and screenshot", "verify my SwiftUI/UIKit layout renders right", "drive this flow in the simulator", "walk through onboarding on iOS", "add my widget to the home screen and screenshot", "tap through the settings sheet". Covers any task where a screenshot of a running iOS app or widget answers the question - visual verification of SwiftUI/UIKit, dark mode, dialogs/sheets, widget rendering at small/medium/large families, theming, multi-step flows. Also covers scripted launching (URL schemes, push payloads, appearance toggles), inspecting device state (`log stream`, app sandbox, UserDefaults), and the rebuild-install-screenshot loop via xcrun simctl. Use whenever "let me see it on a simulator" or "does this look right on iOS" applies. Does not cover Xcode build failures unrelated to a screenshot, signing/provisioning for the Store, or distributing to TestFlight.
---

# iOS simulator debugging from the macOS CLI

This skill captures the working pattern for bringing up an iOS Simulator on a Mac, installing an app, driving what UI you can, and reasoning about the result — entirely from the terminal. The point is to get a fast, scriptable feedback loop where every change can be verified with a screenshot, without leaving the editor.

It assumes Apple Silicon and zsh, with a copy of Xcode at `/Applications/Xcode.app`. Almost everything below routes through `xcrun simctl`, which is included with Xcode's command-line tools.

## When this is the right approach

- You're iterating on SwiftUI or UIKit code and want to see results in seconds without launching Xcode's IDE.
- You're rendering a WidgetKit widget and want to verify it at the three size families (`systemSmall` / `systemMedium` / `systemLarge`) plus light/dark.
- You want screenshots in the conversation so you can actually reason about what's on screen — typography, alignment, dark-mode contrast, dynamic type, multi-line wrap.
- You're debugging device-side state (system log, UserDefaults, app sandbox files) without attaching a debugger.
- You're testing URL-scheme entry points, push payloads, or deep links where Xcode's "Run" cycle is too slow.

## What iOS makes hard (vs. Android)

This is worth stating up front so you don't waste time. On Android you have `adb shell input tap` and `uiautomator dump` — you can drive any UI from the terminal. iOS has no equivalent for production builds.

- **You cannot programmatically tap or scroll the simulator from the CLI.** No `simctl input tap`, no `simctl ui dump`. The only sanctioned automation is `XCUITest` from within a test target you build yourself, or driving Simulator.app via AppleScript (`tell application "Simulator" to ...`) which is brittle.
- **You cannot programmatically add a widget to the home screen.** Long-press → `+` → drag is a SpringBoard interaction that has no CLI surface. The user has to do it once by hand on each fresh simulator.
- **WKWebView cookies aren't easily inspectable from outside the app.** Use Safari's Develop menu (`Safari → Develop → Simulator → <Page>`) and Web Inspector; there's no CLI tool that reads another app's WKWebsiteDataStore.

The right strategy is to lean on what *does* work from the terminal — build, install, launch, screenshot, log stream, sandbox file inspection, URL-scheme launches — and use the GUI only for the things that have no CLI surface (taps, drags, widget gallery).

## Quick reference

Set env once per shell (usually unnecessary — Xcode's tools find themselves via `xcrun`):
```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
```

Boot a simulator and wait for it:
```bash
xcrun simctl boot "iPhone 15 Pro"   # name or UDID; idempotent if already booted
xcrun simctl bootstatus "iPhone 15 Pro" -b   # blocks until boot completes
open -a Simulator                    # show the window (skip if you only need screenshots)
```

Build + install + launch + screenshot loop:
```bash
xcodebuild -project ClaudeUsage.xcodeproj -scheme ClaudeUsage \
  -configuration Debug -destination 'platform=iOS Simulator,name=iPhone 15 Pro' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build

APP="build/Build/Products/Debug-iphonesimulator/Claude Usage.app"
xcrun simctl install booted "$APP"
xcrun simctl launch booted com.sidbh.claudeusage
sleep 2
xcrun simctl io booted screenshot /tmp/shot.png
```

Then read `/tmp/shot.png` — the Read tool surfaces it inline in the conversation.

## Setup (only if Xcode is missing)

Check first:
```bash
xcode-select -p                            # path to Xcode developer dir
xcodebuild -version | head -1
xcrun simctl list devices available | head -20
```

If none of this works, the user needs the full Xcode app from the App Store (the CLT package alone isn't enough — it doesn't include the iOS SDK or Simulator runtimes). Don't try to install Xcode for them; surface the requirement and stop.

Once Xcode is installed, accept the license and download runtimes:
```bash
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch        # installs missing components
xcodebuild -downloadAllPlatforms       # iOS/watchOS/tvOS runtimes (large)
```

`xcodebuild -runFirstLaunch` is what fixes most "plug-in failed to load" errors from a stale Xcode upgrade — covered in the gotchas section.

List installed simulators:
```bash
xcrun simctl list devices available
```

Create a fresh simulator (one-time):
```bash
xcrun simctl create "ClaudeTest-iPhone15" \
  com.apple.CoreSimulator.SimDeviceType.iPhone-15-Pro \
  com.apple.CoreSimulator.SimRuntime.iOS-17-5
```

`simctl list runtimes` and `simctl list devicetypes` enumerate the strings you need. Names with spaces are fine as long as they're quoted.

## Booting the simulator

```bash
xcrun simctl boot "iPhone 15 Pro"
xcrun simctl bootstatus "iPhone 15 Pro" -b      # -b = block until booted
```

`boot` is non-blocking; `bootstatus -b` is the analog of Android's `getprop sys.boot_completed` polling — it waits for SpringBoard to be ready before you start trying to install or launch.

`open -a Simulator` reveals the window if you want to watch what's happening. For pure screenshot-driven work you can skip this and run headless.

Shut down when done:
```bash
xcrun simctl shutdown "iPhone 15 Pro"     # or "all"
```

Erase to factory state (handy when WKWebView cookies, keychain, or App Group defaults have crud you want gone):
```bash
xcrun simctl erase "iPhone 15 Pro"
```

## Building

For most iteration, you want a Debug build for the simulator without code signing:

```bash
xcodebuild -project MyApp.xcodeproj -scheme MyApp \
  -configuration Debug \
  -destination 'platform=iOS Simulator,name=iPhone 15 Pro' \
  -derivedDataPath build \
  CODE_SIGNING_ALLOWED=NO \
  build
```

`-derivedDataPath build` keeps build outputs inside the project rather than the global `~/Library/Developer/Xcode/DerivedData/` cache. Useful if you want predictable paths to the `.app` bundle.

`CODE_SIGNING_ALLOWED=NO` skips the signing step entirely, which removes the need for a Team in Signing & Capabilities just to compile.

The resulting `.app` is at `build/Build/Products/Debug-iphonesimulator/<Product Name>.app`. Spaces in the product name appear literally in the path — quote it when passing to `simctl install`.

For a real device build (no simulator runtime needed; this also works around simulator plug-in failures):
```bash
xcodebuild -project MyApp.xcodeproj -scheme MyApp \
  -configuration Debug \
  -destination 'generic/platform=iOS' \
  CODE_SIGNING_ALLOWED=NO build
```

## Installing and launching

```bash
xcrun simctl install booted "build/Build/Products/Debug-iphonesimulator/MyApp.app"
xcrun simctl launch booted com.example.myapp
```

`booted` is shorthand for "whichever simulator is currently booted" — convenient when only one is up. If you have several, use the UDID from `xcrun simctl list`.

Pass launch arguments / environment variables:
```bash
xcrun simctl launch --console-pty booted com.example.myapp -DEBUG_MODE 1
xcrun simctl launch --console-pty --terminate-running-process booted com.example.myapp
```

`--console-pty` streams the app's stdout/stderr into your terminal — useful for printf debugging. `--terminate-running-process` force-quits any existing instance first (analog of Android's `am force-stop && am start`).

Open a URL (deep link / custom scheme):
```bash
xcrun simctl openurl booted "myapp://settings"
xcrun simctl openurl booted "https://claude.ai/login"
```

Trigger a push payload:
```bash
xcrun simctl push booted com.example.myapp ./apns-payload.json
```

Force quit:
```bash
xcrun simctl terminate booted com.example.myapp
```

Reset the app's data without uninstalling:
```bash
xcrun simctl uninstall booted com.example.myapp
xcrun simctl install booted "MyApp.app"      # reinstall to clear sandbox
```

## Driving the UI

The unfortunate truth: there is no Android-equivalent `input tap` for the iOS Simulator. Plan your workflow around that constraint.

### What's available without a test target

**URL schemes and Universal Links.** `xcrun simctl openurl booted <url>` is the most reliable way to jump to a deep state without manual tapping. Wire your settings screen, login flow, or any contentious nav target to a URL scheme during development.

**Appearance and locale toggles.**
```bash
xcrun simctl ui booted appearance light    # or dark
xcrun simctl ui booted content_size extra-extra-large
```
`extra-extra-large` exercises Dynamic Type without manual settings drilling. Other values: `extra-small`, `small`, `medium`, `large`, `extra-large`, `extra-extra-extra-large`, plus the `accessibility-*` variants up to `accessibility-extra-extra-extra-large`.

**Locale & timezone.**
```bash
xcrun simctl spawn booted defaults write com.apple.preferences.datetime SetTimeZone America/Los_Angeles
xcrun simctl spawn booted launchctl stop com.apple.SpringBoard   # restart SpringBoard for changes to apply
```

**Push notifications, location, status bar.**
```bash
xcrun simctl push booted com.example.app ./payload.json
xcrun simctl location booted set 37.7749,-122.4194
xcrun simctl status_bar booted override --time "9:41" --batteryState charged --batteryLevel 100
```

`status_bar override` is useful for screenshot uniformity — pin the time to 9:41 across runs so visual diffs aren't noisy.

### When you really need to tap

Three options, in increasing complexity:

1. **AppleScript automation of Simulator.app.** Brittle and pixel-coordinate-based, but no test target required:
   ```bash
   osascript -e 'tell application "System Events" to tell process "Simulator" \
     to click at {200, 400}'
   ```
   Coordinates are screen pixels, not simulator points, and depend on the window position. Avoid unless you have nothing else.

2. **XCUITest target inside the app.** Write a UI test that performs the flow you need, then run it via:
   ```bash
   xcodebuild test -project MyApp.xcodeproj -scheme MyAppUITests \
     -destination 'platform=iOS Simulator,name=iPhone 15 Pro'
   ```
   This is the official path. The setup cost is one-time and the tests are deterministic. Worth doing for any flow you'll re-run more than two or three times.

3. **`idb`** (Facebook's iOS Development Bridge — `brew install facebook/fb/idb-companion idb`). Provides `idb ui tap`, `idb ui describe_all`, and an interactive shell similar to `adb`. Not officially supported by Apple, can lag behind iOS releases, but when it works it's the closest thing to `adb` on iOS. Reach for it only after you've confirmed XCUITest isn't a better fit.

### Adding a widget to the home screen

There is no CLI for this. The sequence is, manually in the Simulator window:
1. Long-press an empty area of the home screen until icons start jiggling.
2. Tap the `+` in the top-left.
3. Find your widget in the gallery (search by app name).
4. Tap "Add Widget" → "Done".

Once the widget is present, reloads happen via `WidgetCenter.shared.reloadAllTimelines()` from the host app (which you can trigger via a URL scheme or just relaunching the app). Subsequent code changes only require a rebuild + reinstall — the widget instance survives.

## Capturing screenshots

```bash
xcrun simctl io booted screenshot /tmp/shot.png
```

The default device family is iPhone, in the simulator's actual resolution. To capture a specific simulator when several are booted, swap `booted` for a UDID.

For the entire screen recording:
```bash
xcrun simctl io booted recordVideo /tmp/run.mov
# ^C to stop
```

Read `/tmp/shot.png` with the Read tool — it renders as an image inline in the conversation. Don't try to view via shell tools, you'll just get bytes.

## Inspecting device state

### Streaming logs

The equivalent of `adb logcat`:
```bash
xcrun simctl spawn booted log stream --level=debug --predicate \
  'subsystem == "com.sidbh.claudeusage" OR processImagePath ENDSWITH "Claude Usage.app"'
```

`log stream` is verbose; the predicate is non-negotiable for keeping output readable. Common predicates:

| Filter | Predicate |
|---|---|
| Your subsystem | `subsystem == "com.your.bundle"` |
| Your process by name | `processImagePath ENDSWITH "YourApp.app"` |
| Errors only | `messageType == error` |
| Widget timeline | `subsystem == "com.apple.chronod"` |

For a non-streaming dump of recent history:
```bash
xcrun simctl spawn booted log show --last 5m --predicate '...' --info --debug
```

To get the output of an app launched with `--console-pty`, you can also use:
```bash
xcrun simctl launch --console-pty booted com.example.app
```

Print statements from your code arrive in real time on stdout.

### App sandbox

Find the on-disk path to an installed app's container:
```bash
xcrun simctl get_app_container booted com.example.app data
# /Users/.../Devices/<UDID>/data/Containers/Data/Application/<APP-UUID>/
```

Three container types: `app` (the bundle itself), `data` (Documents, Library, tmp), `groups` (App Groups). For widgets that share state with the host app:
```bash
xcrun simctl get_app_container booted com.example.app groups.com.example.shared
```

Read shared `UserDefaults`:
```bash
GROUP_DIR=$(xcrun simctl get_app_container booted com.example.app groups.com.example.shared)
plutil -p "$GROUP_DIR/Library/Preferences/group.com.example.shared.plist"
```

### Keychain

The simulator's keychain is per-device-clone and you can't `plutil` it. The only reliable approach is to read keychain items from inside the app and `print()` what you find, or use Xcode's "Devices and Simulators" → "Open Container" then attach a debugger.

### Currently running apps

```bash
xcrun simctl listapps booted
```

Lists installed app bundle IDs. For "what's foregrounded" there's no clean equivalent of `dumpsys activity top` — pry it from the system log or just take a screenshot.

## The fast iteration loop

```bash
xcodebuild -project MyApp.xcodeproj -scheme MyApp \
  -destination 'platform=iOS Simulator,name=iPhone 15 Pro' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build \
  && xcrun simctl install booted "build/Build/Products/Debug-iphonesimulator/MyApp.app" \
  && xcrun simctl launch --terminate-running-process booted com.example.app \
  && sleep 2 \
  && xcrun simctl io booted screenshot /tmp/shot.png
```

Read `/tmp/shot.png`, decide what's wrong, edit, run again. Each cycle is typically 10-25s once Xcode is warm — slower than Android because compilation is heavier.

For widget work: once the widget is on the home screen (manual one-time step), broadcasting a reload via the host app's URL scheme keeps you in the loop without re-tapping. Trigger like:
```bash
xcrun simctl openurl booted "myapp://reload-widget"
sleep 1
xcrun simctl io booted screenshot /tmp/shot.png
```

…and have your URL handler call `WidgetCenter.shared.reloadAllTimelines()` and then exit.

## Gotchas worth remembering

These are the ones that actually waste real time.

**`xcodebuild` plug-in failures after Xcode updates.** Symptom: log lines like `DVTPlugInLoading: Failed to load code for plug-in com.apple.dt.IDESimulatorFoundation`, `dlopen ... Symbol not found`, and finally `A required plugin failed to load`. The most common cause is not a corrupt Xcode install — it's a *missing iOS Simulator runtime*. The plug-in tries to enumerate runtimes at load time and crashes when there are none. Check first:
```bash
xcrun simctl list runtimes          # if "== Runtimes ==" is empty, that's it
xcodebuild -downloadPlatform iOS    # ~8 GB, no sudo, runs as the user
```
After the runtime download finishes, the plug-in load succeeds and the build works. Only if downloading the runtime doesn't fix it should you try `sudo xcodebuild -runFirstLaunch` (which reinstalls system frameworks). Targeting `generic/platform=iOS` instead of the simulator is a temporary workaround that lets the rest of the build complete while the runtime downloads.

**`booted` ambiguity.** `simctl <cmd> booted` only works when exactly one simulator is booted. If two are up (say one from a prior session), `booted` silently picks the first one in some unspecified order. Use the UDID explicitly: `xcrun simctl list devices booted` then `simctl <cmd> <UDID> ...`.

**Spaces in the product name break paths.** A scheme named "Claude Usage" produces `Claude Usage.app`. Always quote the path: `simctl install booted "build/.../Claude Usage.app"`. Single-quote-double-quote works fine.

**`xcrun simctl bootstatus` without `-b` returns immediately.** It prints status and exits with code 0 whether or not the simulator is ready. Always use `-b` ("block until booted") if you intend to install right after.

**`open -a Simulator` is not what boots the device.** It just brings the Simulator GUI window forward. The device is booted by `simctl boot`. If you `open -a Simulator` first you may get a different default device than the one your scripts expect.

**App Groups silently no-op on unsigned simulator builds.** This one bit me hard. `UserDefaults(suiteName: "group.com.example.shared")` returns a *non-nil* instance even when the App Group isn't provisioned — but writes to it land in a per-app preferences file, not the shared container. Same-process reads succeed (in-memory cache), so it looks fine until the widget extension tries to read what the host app wrote and finds nothing. The widget renders the "Tap to log in" state forever.

The probe `set/get` trick is unreliable: the host app's own re-read passes because it hits the local cache. The authoritative check is the container directory:
```swift
FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: identifier) != nil
```
If that returns nil, the group is not provisioned — *don't* use the suite-name UserDefaults expecting cross-process visibility. Fix: sign the project with a team that has the App Group capability registered in the developer portal. There is no purely-CLI workaround.

**Keychain access groups need the team prefix.** The string must start with `$(AppIdentifierPrefix)` (which Xcode expands to `TEAM_ID.` at sign time). Cross-target Keychain sharing only works if both targets resolve to the same prefix. Without a signing team set, the prefix is empty and the access-group string becomes invalid — and (this is the cruel part) *every* Keychain call from the app fails with `errSecMissingEntitlement` (-34018), even ones that don't specify an access group at all. The invalid entitlement poisons all Keychain access.

The fix is to sign with a team. For unsigned dev builds, the pragmatic workaround is to skip the keychain-access-groups entitlement entirely, or detect the failure at init via a probe `SecItemAdd` of a dummy item and fall back to UserDefaults (with the obvious caveat that this is dev-only).

**Widget extensions cannot read host-app state without provisioned App Groups.** Consequence of the above: even if your host app writes to "shared" UserDefaults perfectly, the widget extension running in a separate process gets its own per-app file when the App Group is unprovisioned. The widget always reads empty state. Signing fixes this; no CLI workaround.

**Widgets cannot run arbitrary background tasks.** Unlike an Android `WorkManager` periodic task, a WidgetKit timeline is "advisory" — the system reloads on its own schedule, typically less often than your `.after()` policy suggests. If freshness matters, also trigger reloads from the host app whenever it enters foreground.

**Status bar in screenshots is non-deterministic.** Time, signal, battery, and carrier all vary. For visual regression work pin them with `simctl status_bar override --time "9:41" --batteryState charged --batteryLevel 100`.

**Don't trust `simctl launch` exit code as "app is running".** It returns once `launchd` has spawned the process, which is well before any UI is drawn. Always `sleep 1-3` before screencap.

**WKWebView Web Inspector requires Safari.** To debug a WKWebView in your simulator app, enable Safari → Settings → Advanced → "Show Develop menu" on your Mac, then Safari → Develop → Simulator → <page>. There is no CLI equivalent.

**SwiftUI `print()` goes to stdout, not the unified log by default.** `simctl spawn booted log stream` won't show `print(...)` output unless you also call `os.Logger` or use `os_log`. The reliable way to see prints from the CLI is to launch with `simctl launch --console-pty booted <bundle-id>`, which attaches stdout. Redirect to a file (`> /tmp/app.out`) to make it tail-friendly. The `--console-pty` foreground command returns once the app is spawned; the stream stays open as long as the app process lives, so this works fine for background-monitor workflows.

**`osascript`-based UI automation requires Accessibility permission.** `tell application "System Events" to click at {x, y}` will return error -25204 ("not permitted") until you grant Accessibility access to the parent process (Terminal, iTerm, your editor's shell, etc.) in System Settings → Privacy & Security → Accessibility. Without that grant, you cannot synthesize taps into the Simulator from the CLI at all. The user has to enable it once per terminal — don't waste time tweaking the script.

**SPA login pages may not set every cookie you expect.** claude.ai's `lastActiveOrg` cookie, for example, is only set after the user navigates to a real organization page — it isn't there on `/login` even after a successful sign-in. If your cookie-capture polling requires multiple cookies, the user will tap "Done" with only some of them present and your flow hangs. Either widen the capture criteria (sessionKey alone is often enough) or fall back to an API call (`/api/organizations`) using the cookies you *do* have.

## Debugging mindset

When a screenshot doesn't show what you expect, the question is: *did the code not run, or did it run and produce something different?* Distinguish before guessing:

1. **Did the app launch?** Was there a `simctl launch` exit code? Take a screenshot — a blank simulator means SpringBoard, which means the app never came up.
2. **Did your code path execute?** Add a `print("WIDGET-DBG: ...")` and tail `simctl spawn booted log stream --predicate 'processImagePath ENDSWITH "MyApp.app"'`. Silence here means the path didn't run.
3. **Did you build what you think you built?** `mdls -name kMDItemContentModificationDate "build/.../MyApp.app"` shows the build timestamp. `mdls -name kMDItemVersion "build/.../MyApp.app/Info.plist"` shows the version. Both should post-date your last edit.
4. **Is the screenshot fresh?** WidgetKit reloads are async. After triggering a reload, give it 1-3 seconds before screencap.
5. **Did entitlements actually apply?** `codesign -d --entitlements - "build/.../MyApp.app" 2>/dev/null` dumps the effective entitlements XML. If App Group or Keychain groups are missing here, the corresponding APIs will silently fail at runtime.

When in doubt: terminate and relaunch (`simctl terminate` then `simctl launch --console-pty`), watch stdout, then screencap. An empty log is a real signal — it means your code never ran.
