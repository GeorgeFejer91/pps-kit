# Android LSL Integration Boundary

The Android companion now has phone-owned PPS runtime artifacts and a strict
phone-side command/status protocol, but it does not yet ship a live native LSL
transport. Current phone runs write `lsl_runtime_status.json` with
`native_transport_available=false` and
`reason=native_liblsl_android_layer_not_present`.

## Current Implemented Layer

- `PhoneLslProtocol.kt` mirrors the PC runner `PPSCommandSignalsV1` and
  `PPSCommandAcksV1` string-sample field order.
- The phone-owned screen has explicit `Runner` and `Controller` roles. Runner
  mode owns local package playback; Controller mode writes token-gated
  `PPSCommandSignalsV1` samples to `phone_controller_command_outbox.jsonl` for
  the future native bridge.
- Commands are token-gated through `token` or `companion_token` in
  `payload_json` before any local handler runs.
- Acks are shaped as applied/rejected command acknowledgements after the local
  handler returns.
- Phone-owned run folders and ZIP exports include `lsl_runtime_status.json`.
- Controller-mode outboxes include `phone_controller_runtime_status.json` with
  `native_transport_available=false` and
  `current_android_source_behavior=local_controller_outbox_only`.
- PC-side phone uploads preserve `lsl_runtime_status.json` beside
  `lsl_marker_mirror.csv` and `command_diary.jsonl`.

This layer is useful because it keeps the PC runner, Android runner mode, and a
future Android controller mode on the same command/ack schema. It is not
evidence that Android is currently broadcasting LSL.

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

The integration should add a pinned AAR/JNI dependency, then implement one
Android bridge that can create long-lived outlets/inlets for:

- `PPSMarkersV2`
- `PPSTriggerCodes`
- `PPSCommandSignalsV1`
- `PPSCommandAcksV1`

The bridge must keep outlets alive for the full phone run, use one command/ack
sample per push, and send a command ack only after the local Android handler has
accepted or rejected the state transition.

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
4. Native LSL network test after AAR/JNI integration: resolve Android
   `PPSMarkersV2` / `PPSTriggerCodes` from the PC, send
   `PPSCommandSignalsV1`, receive matching `PPSCommandAcksV1`, and record an
   XDF with LabRecorder.
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
