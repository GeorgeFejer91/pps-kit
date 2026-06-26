# Android Runner Companion

The Android companion is a local Wi-Fi control surface for the native
`PPSExperimentRunner.exe`. The laptop runner remains the timing authority,
owns playback, LSL, LabRecorder, ledgers, output files, top-up, and analysis.
The phone only submits the existing setup form, starts Part 01 or Part 02 when
the runner already allows it, continues instruction gates, and displays the
latest authorized runner snapshot.

## Pairing

1. Start Focus Mode from `PPSExperimentRunner.exe`.
2. In the Focus Mode Data Logging tab, scan the Phone Companion QR code.
3. The Android app opens `pps-companion://pair?...` and stores the runner host,
   port, session id, and per-run `X-PPS-Companion-Token`.
4. Submit the participant setup fields from the phone or laptop.
5. Use the phone `Start Part 01`, `Continue`, and `Start Part 02` controls only
   when they are enabled by the runner snapshot.

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
