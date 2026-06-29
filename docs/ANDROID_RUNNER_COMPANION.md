# Android Runner Companion

The Android companion has two paired modes:

- `PC Runner Control` is a local Wi-Fi control surface for the native
  `PPSExperimentRunner.exe`. The laptop runner remains the timing authority,
  owns playback, LSL, LabRecorder, ledgers, output files, top-up, and analysis.
  The phone submits setup, starts enabled parts, requests pause/resume,
  continues instruction gates, and displays authorized runner snapshots.
- `Run Experiment On Phone` is an experimental phone-local runtime. It downloads
  prepared runner packages from the PC, verifies block WAV checksums, plays the
  block WAVs locally, schedules Android vibration cues from the prepared block
  manifests, records touch responses, and uploads phone runtime artifacts back
  to the PC.

The phone-local runtime can run a full two-part Study 5 preparation after both
part packages are synced with `Sync All`. It does not replace the PC runner for
hardware-timed collection: Android vibration timing, phone audio output, and
touch timestamps are phone-runtime evidence only and do not provide LSL,
LabRecorder, Woojer, or wired-loopback guarantees.

The phone package schema is now `pps-mobile-run-package.v2`. It remains
backward-compatible with the original prepared-block WAV replay path, but it
also carries a reconstruction contract: Segment 6 source hashes, block order,
trial identities, a reusable trial-building-block asset catalog when
`Trial_File_Path` is available, and the Android phone LSL contract. The current
Android build writes a PPSMarkersV2-shaped local marker mirror and command diary
beside the phone event log; live native LSL broadcast is the next integration
step and requires a pinned liblsl Android native layer.

## Pairing

1. Start Focus Mode from `PPSExperimentRunner.exe`.
2. In Focus Mode, open the `Companion Android App (Experimental)` tab and scan
   the QR code.
3. The Android app opens `pps-companion://pair?...` and stores the runner host,
   port, session id, and per-run `X-PPS-Companion-Token`.
4. Choose `PC Runner Control` for the native PC timing path, or
   `Run Experiment On Phone` for the experimental phone-local runtime.
5. In `PC Runner Control`, submit the participant setup fields from the phone or
   laptop.
6. Use the phone `Start Part 01`, separate `Pause` and `Resume`, `Continue`,
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
- Phone-runtime package and upload endpoints also require
  `X-PPS-Companion-Token`: `GET /api/mobile/packages`,
  `GET /api/mobile/packages/{package_id}/manifest`,
  `GET /api/mobile/packages/{package_id}/assets/{asset_id}`,
  `POST /api/mobile/runs/{run_id}/events`, and
  `POST /api/mobile/runs/{run_id}/complete`.
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

Phone-runtime uploads are written under the selected acquisition folder's
protected context in
`Experiment_context_folder_DO_NOT_DELETE/runner_logs/mobile_phone_runtime/
<participant>/<package_id>/<run_id>/`. The uploaded `events.jsonl`,
`events.csv`, and `completion.json` files are local experiment artifacts and are
not committed.

## Run Experiment On Phone

After pairing, choose `Run Experiment On Phone`.

- `Refresh` reads the currently prepared phone packages from the PC companion
  service. Split Study 5 preparations expose separate Part 1 and Part 2
  packages.
- `Sync` downloads and checksum-verifies the selected package.
- `Sync All` downloads and checksum-verifies every listed package, which is the
  expected path for the full two-part Study 5 profile.
- `Start Phone Run` runs only the selected synced package.
- `Start Full Experiment` runs all synced packages in listed order, so a synced
  Study 5 pre/post preparation plays Part 1 and Part 2 on the phone and uploads
  a completion artifact for each part.

The phone runtime parses PCM WAV blocks and plays them with Android
`AudioTrack`, schedules tactile cue delivery from the AudioTrack playback head,
uses `SystemClock.elapsedRealtime()` for phone-side timestamps, and drives the
Android vibrator service for tactile cue signaling. Treat it as an experimental
mobile collection mode until physical phone timing validation is added.

Synced v2 packages include:

- prepared block WAV assets with role `block_audio`, which remain the current
  playback path
- optional reusable Segment 3 trial WAV assets with role
  `trial_building_block`, used by future lightweight replay/top-up logic
- `reconstruction` metadata with source Segment 6 hashes and schedule hash
- `lsl` metadata declaring `PPSMarkersV2`, `PPSTriggerCodes`,
  `PPSCommandSignalsV1`, and `PPSCommandAcksV1`

Phone-owned local artifacts now include `participant_metadata.json`,
`haptic_capability.json`, `events.csv`, `lsl_marker_mirror.csv`,
`command_diary.jsonl`, `lsl_runtime_status.json`, reconstruction/package
snapshots, response/top-up ledgers, and `completion.json` in the exported phone
session ZIP. Participant age, handedness, gender, and tactile threshold stay in
metadata and marker payloads rather than discoverable LSL stream names.

Default Android builds do not ship liblsl. If a local validation build adds the
ignored `android/runner-companion/app/libs/liblsl-Android.aar`, runner mode opens
native `PPSMarkersV2` / `PPSTriggerCodes` outlets and can resolve
`PPSCommandSignalsV1` to emit token-gated `PPSCommandAcksV1`. Current command
handling records snapshot/note/continue actions, applies pause/resume through
the phone-owned `AudioTrack` pause gate during active phone blocks, and records
`phone_playback_pause` / `phone_playback_resume` diary and marker-mirror events.
Stop-after-block remains rejected until the phone runner has a block-boundary
stop policy.

Controller mode always writes `phone_controller_command_outbox.jsonl` as the
local audit trail. In a native liblsl validation build it also keeps a
`PPSCommandSignalsV1` outlet open while Controller mode is selected, sends button
presses over LSL, polls for matching `PPSCommandAcksV1` samples, and records the
native send/ack result in the outbox row plus
`phone_controller_runtime_status.json`.

Android vibration calibration is device-limited. If Android reports amplitude
control, the entered threshold percent is mapped to the `VibrationEffect`
amplitude range for phone vibration cues. If the phone has a vibrator but no
amplitude control, the app records the device as binary detection only and uses
default-amplitude pulses; that value should not be interpreted as a calibrated
physical vibration strength.

FFmpeg-style synthesis is technically possible on Android through native FFmpeg
builds, but the app does not depend on FFmpegKit because that wrapper project is
retired. For top-up and lightweight phone replay, prefer a small deterministic
PCM WAV assembler over a broad FFmpeg runtime unless future requirements need
general resampling or transcoding.

## Emulator Evidence

On 2026-06-29, the full Study 5 phone path was verified on the local API 30 x86
ATD emulator (`emulator-5556`). The app paired to a token-gated companion
service at `10.0.2.2:8767`, listed both Study 5 part packages, synced all
824 MiB of prepared block WAV assets, enabled `Start Full Experiment`, and ran
both parts to completion in real time. The PC received two `completion.json`
artifacts:

- `P001_20260626_150806_part_01-part1`: 246 uploaded phone events, 52 scripted
  tap responses, 8 valid cue-linked taps.
- `P001_20260626_150806_part_02-part2`: 246 uploaded phone events, 52 scripted
  tap responses, 11 valid cue-linked taps.

This confirms the app can sync and run the whole prepared Study 5 profile from
the phone runtime path. It remains emulator/software evidence, not physical
phone timing certification.

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
responses. It also suppresses tactile-cue cursor recentering: the runner logs
the intended recenter position in the validation report but does not move the OS
cursor.

On this lab PC, runner-side validation windows may be placed on the left display
shown as Windows display `2`.
Use:

```powershell
.\windows\Set_Companion_Emulation_Layout.ps1
```

The script defaults to the leftmost Windows monitor, currently `DISPLAY2`
(`-1920,5 1920x1032` working area), and places only
`PPSExperimentRunner.exe` in the runner slice. It deliberately does not move,
resize, widen, or poll the Android emulator window: emulator validation uses
the AVD's fixed phone viewport, and clipping, scrolling burden, hidden controls,
or cramped buttons are app findings. Older calls that pass `-KeepForSeconds`
are accepted for compatibility but no longer start a persistent placement loop.
Passive runs also enable the validation-only synthetic click shortcut
`Ctrl+Alt+Shift+F12`, which logs one in-target runner response through the
normal controller path without moving the PC mouse.

For runner launches that happen before the placement script can see a window,
use the validation placement environment as well:

```powershell
$env:PPS_FOCUS_VALIDATION_DISPLAY = "left"
$env:PPS_FOCUS_VALIDATION_RUNNER_WIDTH = "820"
```

An exact rectangle can be supplied with `PPS_FOCUS_VALIDATION_WINDOW_RECT`, for
example `-1920,5,820,1032`.

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
