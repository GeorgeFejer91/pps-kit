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
  mode owns local package playback; Controller mode always writes token-gated
  `PPSCommandSignalsV1` samples to `phone_controller_command_outbox.jsonl` and,
  when native liblsl is present, keeps a long-lived `PPSCommandSignalsV1` outlet
  open for button-press commands.
- The PC-side helper `pps-android-lsl-command` sends the same token-gated
  `PPSCommandSignalsV1` samples from the runner/PC environment, waits for
  `PPSCommandAcksV1` when requested, and writes
  `pc_android_lsl_command_outbox.jsonl` plus
  `pc_android_lsl_admin_status.json`.
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
- When Runner mode is idle with a synced selected package, the native command
  listener acknowledges `start_experiment`/`start_part` and then launches the
  phone run. During active playback, those start commands are acknowledged as
  already-running no-ops; `continue_instruction`, `request_snapshot`, and
  `operator_note` are diary/snapshot actions, and `pause`/`resume` go through
  the phone-owned `AudioTrack` pause gate during active phone blocks.
  Pause/resume commands record `phone_playback_pause` /
  `phone_playback_resume` diary and marker-mirror events with pause-adjusted
  block elapsed time. `stop_after_block` now records
  `phone_stop_after_block_request`, finishes the current `AudioTrack` block
  without truncating audio, records `phone_stop_after_block_boundary`, skips
  remaining scheduled phone blocks plus phone top-up, and closes the run with
  `completion_reason=stopped_after_block`.
- Phone-owned run folders and ZIP exports include `lsl_runtime_status.json`.
- Controller-mode outboxes include `phone_controller_runtime_status.json`.
  Default builds record `current_android_source_behavior=local_controller_outbox_only`;
  native builds record `native_lsl_controller_with_local_outbox` when the
  command outlet is live. Each controller command row records whether the sample
  was sent over native LSL and whether a matching `PPSCommandAcksV1` sample was
  observed.
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

The bridge keeps marker outlets alive for the full phone run, attempts runner
command resolution at run start, retries command-stream resolution during
playback when liblsl is available but no command stream was found, keeps a
controller command outlet alive while Controller mode is selected, uses one
command/ack sample per push, and sends a command ack only after the local
Android handler has accepted or rejected the state transition.

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
mirror, resolve runner-side `PPSCommandSignalsV1`, emit `PPSCommandAcksV1` for
handled commands, and create controller-side `PPSCommandSignalsV1` outlets with
optional `PPSCommandAcksV1` ack polling.

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

The companion pairing layer now has its own token-free discovery packet:
`pps-runner-companion-discovery.v1` is sent by the PC bridge to multicast
`239.255.77.83:48767` and limited broadcast `255.255.255.255:48767`. This is a
LAN/local-hotspot convenience for finding the bridge endpoint only. It does not
carry the companion token, participant demographics, or non-generic stream
names; QR/manual URI pairing remains the authorization step.

Required validation levels:

1. Protocol-only unit tests: command/ack sample order, token rejection,
   runtime-status schema.
2. Artifact validator:
   `python validation_protocols/scripts/validate_android_lsl_runtime_artifact.py <phone-run-dir>`.
   The same validator also accepts Controller-mode
   `phone_controller_runtime_status.json` and
   `phone_controller_command_outbox.jsonl` artifacts.
3. Emulator smoke test: install APK, run a phone-owned package, export ZIP, and
   validate `lsl_runtime_status.json`.
4. Native LSL network test with the AAR/JNI integration: resolve Android
   `PPSMarkersV2` / `PPSTriggerCodes` from the PC, send a token-gated
   `PPSCommandSignalsV1` command before or during playback, receive the matching
   `PPSCommandAcksV1`, send a command from Controller mode on a second Android
   app/build, and record an XDF with LabRecorder.
5. Physical phone test on same-Wi-Fi and phone-hotspot networks, including a
   failure-mode report for multicast discovery, reconnect, and command rejection
   behavior.

Use strict mode only after native transport exists:

```powershell
.\.venv\Scripts\python.exe validation_protocols\scripts\validate_android_lsl_runtime_artifact.py <phone-run-dir> --expect-native-transport
```

For a two-phone Controller-to-Runner check where every button press should have
a matching acknowledgement, validate the Controller outbox as well:

```powershell
.\.venv\Scripts\python.exe validation_protocols\scripts\validate_android_lsl_runtime_artifact.py <phone_controller_command_outbox.jsonl> --expect-native-transport --expect-command-acks
```

For a PC-to-phone command check, send commands from the PC helper while the
Android runner is idle with a synced package or actively playing a block:

```powershell
.\.venv\Scripts\pps-android-lsl-command.exe start_experiment --session-id <part_session_id> --token <pairing-token> --package-id <package_id> --require-ack
.\.venv\Scripts\pps-android-lsl-command.exe pause --session-id <part_session_id> --token <pairing-token> --require-ack
.\.venv\Scripts\pps-android-lsl-command.exe resume --session-id <part_session_id> --token <pairing-token> --require-ack
```

Until that strict validator passes together with external LSL/XDF capture, the
phone app remains a local phone-owned runner with LSL-compatible artifacts, not a
publication-grade live LSL broadcaster.
