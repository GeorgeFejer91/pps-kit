# Android Runner Companion

The Android companion is a local Wi-Fi control surface for the native
`PPSExperimentRunner.exe`. The laptop runner remains the timing authority,
owns playback, LSL, LabRecorder, ledgers, output files, top-up, and analysis.
The phone only submits the existing setup form, starts Part 01 or Part 02 when
the runner already allows it, requests pause/resume when the runner advertises
those commands, continues instruction gates, and displays the latest authorized
runner snapshot.

## Pairing

1. Start Focus Mode from `PPSExperimentRunner.exe`.
2. In Focus Mode, open the `Companion Android App (Experimental)` tab and scan
   the QR code.
3. The Android app opens `pps-companion://pair?...` and stores the runner host,
   port, session id, and per-run `X-PPS-Companion-Token`.
4. Submit the participant setup fields from the phone or laptop.
5. Use the phone `Start Part 01`, separate `Pause` and `Resume`, `Continue`,
   and `Start Part 02` controls only when they are enabled by the runner
   snapshot. `Pause` and `Resume` are mutually exclusive: only the command
   currently confirmed as available by the runner is enabled. The app never
   flips its own play/pause state optimistically; it waits for a runner
   snapshot or command response before showing the confirmed state.

The QR code contains a per-run bearer token. Do not share screenshots of it.
Closing Focus Mode stops the companion service and invalidates that token.

## Network

- Default runner service: `http://<runner-lan-ip>:8767`.
- Service host: all LAN interfaces by default, configurable with
  `PPSExperimentRunner.exe --companion-host`, `--companion-port`, and
  `--companion-advertise-ip`.
- Health endpoint: `GET /api/runner/health` is public and non-sensitive.
- All state and command endpoints require `X-PPS-Companion-Token`.
- Windows Firewall must allow inbound local-network TCP traffic to the runner
  process on the selected port.
- The phone and laptop must be on the same trusted LAN. Guest Wi-Fi, client
  isolation, VPNs, or restrictive firewall profiles can block pairing.

## Privacy

The companion service is local HTTP/WebSocket on the trusted LAN. It does not
upload participant data to an external service. Participant names are not placed
in the QR payload or health endpoint. Authorized snapshots can include setup
state so the paired phone can reflect the form; name-sharing opt-in still
controls whether the runner writes the participant name into local session/LSL
metadata.

## Live Feedback

The app is designed for landscape phone viewing. During an active block it
collapses controls into a top command strip so the current-block timeline uses
the full phone width. The visualization shows current trial bands, tactile cue
ticks, the runner-confirmed playhead, cue-linked mouse-click markers, and recent
reaction times. These values are copied from runner snapshots; Android does not
run the experiment clock, write the ledger, or consume LSL directly.

For visible emulator checks while someone is using the PC, use passive
validation (`--mouse-backend none`) or direct snapshot/API checks. Do not use
`pynput`, `win32`, or `pyautogui` mouse backends unless the PC pointer is
available for automation. Passive validation also disables Focus Mode's global
response-click listener so ordinary PC clicks are not recorded as participant
responses.

On this lab PC, companion emulator screenshots should stay on the left display
shown as Windows display `2`.
Use:

```powershell
.\windows\Set_Companion_Emulation_Layout.ps1
```

The script defaults to the leftmost Windows monitor, currently `DISPLAY2`
(`-1920,5 1920x1032` working area), places `PPSExperimentRunner.exe` in the
left slice, and gives the Android emulator the wider right slice for timeline
resolution. Passive runs also enable the validation-only synthetic click
shortcut `Ctrl+Alt+Shift+F12`, which logs one in-target runner response through
the normal controller path without moving the PC mouse.

Generated APKs, Gradle build outputs, and local Android SDK downloads are not
tracked in Git. The committed Android source and Gradle wrapper are part of the
offline lab package for inspection/rebuild.

## Build And Install

Requirements:

- JDK 17
- Android SDK with `compileSdk`/`targetSdk` 37 installed
- Network access for first Gradle dependency resolution

Build from the repo root:

```powershell
.\windows\Build_Android_Companion.ps1
```

Equivalent direct command:

```powershell
cd android\runner-companion
.\gradlew.bat testDebugUnitTest assembleDebug
```

The debug APK is generated under:

```text
android\runner-companion\app\build\outputs\apk\debug\
```

Install on a connected Android device:

```powershell
adb install -r android\runner-companion\app\build\outputs\apk\debug\app-debug.apk
```

The app is native Kotlin/Compose Material 3 and uses CameraX plus bundled ML Kit
barcode scanning for QR pairing. It uses OkHttp for HTTP/WebSocket runner
communication.
