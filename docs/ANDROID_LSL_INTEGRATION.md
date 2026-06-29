# Android LSL Integration Boundary

The Android companion now has phone-owned PPS runtime artifacts, a strict
phone-side command/status protocol, and an optional native liblsl bridge. The
repository does not ship liblsl binaries. Default builds therefore write
`lsl_runtime_status.json` with `native_transport_available=false` and a
`liblsl_android_class_unavailable` reason. Local validation builds can add an
ignored `liblsl-Android.aar` to enable native LSL behavior.

## Current Implemented Layer

- `PhoneLslProtocol.kt` mirrors the PC runner `PPSCommandSignalsV1` and
  `PPSCommandAcksV1` string-sample field order.
- The phone-owned screen has explicit `Runner` and `Controller` roles. Runner
  mode owns local package playback; Controller mode writes token-gated
  `PPSCommandSignalsV1` samples to `phone_controller_command_outbox.jsonl`.
- Commands are token-gated through `token` or `companion_token` in
  `payload_json` before any local handler runs.
- Acks are shaped as applied/rejected command acknowledgements after the local
  handler returns.
- When the ignored local `liblsl-Android.aar` is present, Runner mode opens
  long-lived `PPSMarkersV2` / `PPSTriggerCodes` outlets and attempts to resolve
  a `PPSCommandSignalsV1` stream. If command resolution succeeds, it opens a
  `PPSCommandAcksV1` outlet, polls commands during AudioTrack playback, token
  gates them, applies or rejects them locally, and pushes one ack sample after
  the handler returns.
- The current phone command handler applies `start_experiment`/`start_part` as
  already-running no-ops, applies `continue_instruction`, `request_snapshot`,
  and `operator_note` as diary/snapshot actions, and rejects
  `pause`/`resume`/`stop_after_block` with
  `phone_runtime_command_not_yet_supported`. This is intentional until phone
  playback has a true pauseable AudioTrack state machine.
- Phone-owned run folders and ZIP exports include `lsl_runtime_status.json`.
- Controller-mode outboxes include `phone_controller_runtime_status.json` with
  `native_transport_available=false` and
  `current_android_source_behavior=local_controller_outbox_only`.
- PC-side phone uploads preserve `lsl_runtime_status.json` beside
  `lsl_marker_mirror.csv` and `command_diary.jsonl`.

This layer is useful because it keeps the PC runner, Android runner mode, and
Android controller mode on the same command/ack schema. Default builds are not
evidence that Android is broadcasting LSL; native builds with the AAR must still
pass network/XDF validation before they are treated as live LSL evidence.

## Native Transport Route

Use a pinned native Android liblsl layer instead of ad hoc sockets:

- Official liblsl build docs list Android as a supported target:
  <https://labstreaminglayer.readthedocs.io/dev/build.html>.
- The official Android build docs describe the `liblsl-Android` packaging flow
  and note that the output can be consumed as an `.aar` in Android projects:
  <https://labstreaminglayer.readthedocs.io/dev/build_android.html>.
- The official liblsl repository keeps Android build tooling and Java examples
  under the project source tree:
  <https://github.com/sccn/liblsl>.

The integration uses a pinned local AAR/JNI dependency and one Android bridge
that can create long-lived outlets/inlets for:

- `PPSMarkersV2`
- `PPSTriggerCodes`
- `PPSCommandSignalsV1`
- `PPSCommandAcksV1`

The bridge keeps marker outlets alive for the full phone run, attempts command
resolution at run start, retries command-stream resolution during playback when
liblsl is available but no command stream was found, uses one command/ack sample
per push, and sends a command ack only after the local Android handler has
accepted or rejected the state transition.

The app is already wired for the local AAR path. Put a locally built or release
downloaded `liblsl-Android.aar` at:

```text
android/runner-companion/app/libs/liblsl-Android.aar
```

That file is ignored by Git. When it is absent, the reflection bridge records
`liblsl_android_class_unavailable` and native status remains false. When it is
present, `PhoneNativeLslBridge.kt` can create the rich `PPSMarkersV2` and
numeric `PPSTriggerCodes` outlets, append PC-compatible channel metadata, push
every local marker mirror row to native LSL while preserving the local CSV
mirror, resolve `PPSCommandSignalsV1`, and emit `PPSCommandAcksV1` for handled
commands.

Phone marker timestamps use
`android_elapsed_realtime_plus_open_lsl_clock_offset`: the app samples
`liblsl.local_clock()` when outlets open and maps Android `elapsedRealtime`
event times into that clock domain. This is the correct clock domain for LSL
samples, but it remains phone-runtime evidence until external XDF and physical
timing validation pass.

## Network Caveats

Android LSL validation must treat Wi-Fi as a real experimental dependency.
The official Android build notes mention Android multicast/wireless issues with
some Wi-Fi devices and suggest an external USB Wi-Fi dongle as a practical
workaround when discovery is unreliable. Therefore emulator success, local unit
tests, and local marker mirrors are not enough.

Required validation levels:

1. Protocol-only unit tests: command/ack sample order, token rejection,
   runtime-status schema.
2. Artifact validator:
   `python validation_protocols/scripts/validate_android_lsl_runtime_artifact.py <phone-run-dir>`.
3. Emulator smoke test: install APK, run a phone-owned package, export ZIP, and
   validate `lsl_runtime_status.json`.
4. Native LSL network test with the AAR/JNI integration: resolve Android
   `PPSMarkersV2` / `PPSTriggerCodes` from the PC, send a token-gated
   `PPSCommandSignalsV1` command before or during playback, receive the matching
   `PPSCommandAcksV1`, and record an XDF with LabRecorder.
5. Physical phone test on same-Wi-Fi and phone-hotspot networks, including a
   failure-mode report for multicast discovery, reconnect, and command rejection
   behavior.

Use strict mode only after native transport exists:

```powershell
.\.venv\Scripts\python.exe validation_protocols\scripts\validate_android_lsl_runtime_artifact.py <phone-run-dir> --expect-native-transport
```

Until that strict validator passes together with external LSL/XDF capture, the
phone app remains a local phone-owned runner with LSL-compatible artifacts, not a
publication-grade live LSL broadcaster.
