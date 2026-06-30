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
  open for button-press commands. Controller targets resolve from the synced
  manifest first, then from the `pps-mobile-run-package-list.v2` summary fields
  `session_group_id`, `part_session_id`, and `part_number`, then finally from
  the pairing session id; this lets a second phone address an unsynced split
  part before it downloads the full manifest.
- The PC-side helper `pps-android-lsl-command` sends the same token-gated
  `PPSCommandSignalsV1` samples from the runner/PC environment, waits for
  `PPSCommandAcksV1` when requested, and writes
  `pc_android_lsl_command_outbox.jsonl` plus
  `pc_android_lsl_admin_status.json`. The status includes
  `stream_descriptions` for the PC command-signal outlet and Android command-ack
  inlet, including source IDs/patterns and the same privacy boundary used by the
  Android artifacts. The native runner's `Send To Phone` window exposes the
  same helper as a small Phone LSL Control strip after a package bridge is
  prepared, using the prepared package part-session id as the default command
  target. The strip and CLI both support `operator_note`; note text is stored
  in the token-gated command payload and then validated against the persisted
  command sample. The strip exposes the same core runner commands as Android
  Controller mode: Start, Pause, Resume, Continue, Snapshot, Stop After Block,
  and Note.
- The PC-side helper `pps-android-lsl-monitor` resolves Android
  `PPSMarkersV2`, `PPSTriggerCodes`, `PPSCommandAcksV1`, and
  `PPSCommandSignalsV1` streams for a bounded monitoring window and writes
  `pc_android_lsl_monitor_events.jsonl`,
  `pc_android_lsl_monitor_report.json`, and
  `pc_android_lsl_monitor_status.json`. This is the intended lightweight
  "watch the phone runner from another PC" seam before a full LabRecorder/XDF
  capture. Its embedded status includes `stream_descriptions` for all four
  observed inlets, preserving the same channel-order and privacy contract as
  the phone, controller, and PC-admin artifacts.
- Commands are token-gated through `token` or `companion_token` in
  `payload_json` before any local handler runs.
- Acks are shaped as applied/rejected command acknowledgements after the local
  handler returns.
- Phone-owned command diaries now distinguish `phone_ui`,
  `phone_runtime`, and `native_lsl` command sources. Local Runner-mode start
  buttons plus local Pause, Resume, and Stop After Block controls write
  `phone_ui` rows, internal scheduled-block/top-up bookkeeping writes
  `phone_runtime` rows, and every row is mirrored into an `operator_command`
  marker so the local artifact can reconstruct both received LSL commands and
  direct phone UI actions.
- When the ignored local `liblsl-Android.aar` is present, Runner mode opens
  long-lived `PPSMarkersV2` / `PPSTriggerCodes` outlets and attempts to resolve
  a `PPSCommandSignalsV1` stream. If command resolution succeeds, it opens a
  `PPSCommandAcksV1` outlet, polls commands during AudioTrack playback, token
  gates them, applies or rejects them locally, and pushes one ack sample after
  the handler returns.
- When Runner mode is idle with a synced selected package, the native command
  listener acknowledges `start_experiment`/`start_part` and then launches the
  phone run. The start command signal, ack sample, and `ack_sent` outcome are
  carried into the new `PhoneRunSession` and written as a `native_lsl`
  `command_diary.jsonl` row plus matching `operator_command` event, so a
  remotely started phone run is reconstructable from the receiver artifact.
  During active playback, those start commands are acknowledged as
  already-running no-ops; `continue_instruction`, `request_snapshot`, and
  `operator_note` are diary/snapshot actions, and `pause`/`resume` go through
  the phone-owned `AudioTrack` pause gate during active phone blocks. The local
  Runner-mode Pause and Resume buttons use the same pause gate and diary/event
  evidence, with `command_source=phone_ui`.
  Pause/resume commands record `phone_playback_pause` /
  `phone_playback_resume` diary and marker-mirror events with pause-adjusted
  block elapsed time. `stop_after_block` now records
  `phone_stop_after_block_request`, finishes the current `AudioTrack` block
  without truncating audio, records `phone_stop_after_block_boundary`, skips
  remaining scheduled phone blocks plus phone top-up, and closes the run with
  `completion_reason=stopped_after_block`.
- Phone-owned run folders and ZIP exports include `lsl_runtime_status.json`.
  That status includes `stream_descriptions` using
  `pps-android-lsl-stream-descriptions.v1`: stream names, LSL roles, channel
  formats/counts, PC-compatible channel labels, source IDs/source patterns,
  nominal rates, marker version, and the privacy rule that demographics stay
  out of discoverable stream names. The rich-marker and numeric-trigger
  `session_metadata_json` descriptions now also include compact
  `participant_metadata_summary` and `haptic_capability_summary` objects when
  available, so age/handedness/gender/tactile-threshold policy and the
  recommended phone-vibration threshold can be reconstructed from LSL metadata
  without encoding those values into stream names. Full haptic calibration
  response rows stay in `haptic_capability.json` and the first
  `session_metadata` marker payload.
- Phone-owned run folders and ZIP exports include `reconstruction_contract.json`.
  The phone copies the v2 package's Segment 0-6 hierarchy, schedule hash,
  source setup hash/path, asset strategy, reusable building-block catalog, and
  scheduled-block references into that artifact so strict validators can reject
  hierarchy or schedule drift after the run leaves the phone.
- Phone-owned run folders and ZIP exports also include
  `phone_run_catalog_entry.json`. The app-private
  `phone_run_catalog/<participant>/runs.jsonl` and
  `phone_run_catalog/index.json` files keep a participant/run diary across
  phone-owned sessions so completed and partial phone runs can be traced back
  to package ids, part-session ids, reconstruction hashes, local artifact
  filenames, command-diary counts, LSL status, and privacy-safe participant
  metadata summaries.
- Phone-owned run folders also include `artifact_file_inventory.json` plus
  `artifact_file_inventory.csv`. The inventory excludes itself, but lists the
  rest of the run-folder files with relative paths, byte sizes, SHA-256 hashes,
  and modification timestamps so ZIP exports and app-private folders can be
  checked for missing, extra, or tampered files. Completion/latest-events JSON
  must advertise both inventory sidecars with the expected schema and
  `self_included=false`, giving validators a stable pointer to the file diary
  without creating a self-hashing loop.
- Phone-owned participant/haptic sidecars are validated as one calibration
  contract: when `participant_metadata.json` says the tactile threshold came
  from Android haptic calibration, `haptic_capability.json` must carry a
  matching `pps-android-phone-haptic-calibration.v1` result, matching threshold
  and status fields, response-row evidence, and the deterministic
  threshold-percent-to-amplitude mapping used for phone vibration cues.
- Completed phone-owned run folders now also write
  `phone_owned_data_export.json` and an app-private `phone_owned_exports/`
  snapshot. `1.Data_min/` contains a participant CSV and
  `master_successful_participants.csv` with the same 17-column public schema as
  the PC runner, while `2.Data_max/<participant>/runs/<run_id>/` mirrors the
  rich reconstructive phone-run folder.
- Controller-mode outboxes include `phone_controller_runtime_status.json`.
  Default builds record `current_android_source_behavior=local_controller_outbox_only`;
  native builds record `native_lsl_controller_with_local_outbox` when the
  command outlet is live. Each controller command row records whether the sample
  was sent over native LSL and whether a matching `PPSCommandAcksV1` sample was
  observed. Controller runtime status also includes `stream_descriptions` for
  the controller `PPSCommandSignalsV1` outlet and `PPSCommandAcksV1` inlet, so
  two-phone command rehearsals have the same channel-order and privacy evidence
  as phone-owned runner artifacts. Controller mode exposes Stop After Block
  when `stop_after_block` is in the selected package command set, letting a
  second Android phone request a clean boundary stop over the same LSL schema as
  the PC helper. It also exposes `operator_note` when advertised; the typed
  note text is carried in the command payload, written to the controller outbox,
  and acknowledged by Runner mode as a diary/snapshot action. The artifact
  validator compares the row `payload` object against the serialized
  `PPSCommandSignalsV1` sample payload and rejects missing operator-note text,
  so controller diaries cannot drift from what was actually sent. For split
  packages, controller rows and source IDs target the part `part_session_id`
  even when only the package-list summary has been loaded; the broad pairing or
  transfer session is only a last fallback.
- PC-side phone uploads preserve `lsl_runtime_status.json` beside
  `lsl_marker_mirror.csv`, `trigger_codes.csv`, and `command_diary.jsonl`.
  Completion uploads that include Android response/top-up reconstruction fields
  also write `run_package_manifest.json`, `reconstruction_contract.json`,
  `phone_response_ledger.csv`, `phone_topup_plan.json`,
  `phone_topup_materialization.json`, `phone_owned_data_export.json`,
  `artifact_file_inventory.json`, `artifact_file_inventory.csv`, and a PC-side
  `phone_owned_exports/1.Data_min` plus `2.Data_max` mirror. The inventory is
  generated after `completion.json` and before the `2.Data_max` copy so the PC
  mirror can be rehashed like an exported phone run folder. The PC writer also
  enriches sparse uploaded `lsl_runtime_status` objects with the package's
  generic stream names, command/ack schema, privacy contract, and
  `stream_descriptions`, without claiming native transport is available when
  the phone did not report it.

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
every local marker mirror row to native LSL while preserving the local rich CSV
mirror and the expected numeric `trigger_codes.csv` mirror, resolve runner-side
`PPSCommandSignalsV1`, emit `PPSCommandAcksV1` for handled commands, and create
controller-side `PPSCommandSignalsV1` outlets with optional `PPSCommandAcksV1`
ack polling.
The artifact-level `stream_descriptions` contract records those same
outlets/inlets in `lsl_runtime_status.json`, including rich-marker and
numeric-trigger `session_metadata_json` copies of package schedule/provenance
metadata. Validation can therefore detect channel-order, stream-role,
source-identity, or stream-metadata drift before a run is treated as
reconstructable native LSL evidence.

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
`239.255.77.83:48767`, limited broadcast `255.255.255.255:48767`, and
best-effort private/link-local IPv4 directed broadcasts such as a phone
hotspot's `192.168.43.255:48767`. This is a LAN/local-hotspot convenience for
finding the bridge endpoint only. It does not carry the companion token,
participant demographics/identifiers, or LSL stream/source names; QR/manual URI
pairing remains the authorization step. PC serialization and Android parsing
also recursively reject hidden token, participant/demographic, or stream-name
fields. The payload is validated on both sides as local-only: `network_scope =
same_lan_or_local_hotspot`, multicast TTL `1`, modes `pc_runner` /
`phone_export`, transports `lan` / `phone_hotspot` / `wifi_direct`, and
phone-export discovery must carry a `transfer_id` while still omitting the
token. The `discovery.broadcast_targets` field must advertise both
`255.255.255.255` and `interface_ipv4_directed_broadcasts`, matching the PC
advertiser's same-subnet fallback strategy and Android's parser gate.

Required validation levels:

1. Protocol-only unit tests: command/ack sample order, token rejection,
   runtime-status schema.
2. Artifact validator:
   `python validation_protocols/scripts/validate_android_lsl_runtime_artifact.py <phone-run-dir>`.
   Add `--expect-run-catalog` for new phone-owned run folders/ZIPs where
   `phone_run_catalog_entry.json` should be present and consistent with
   `lsl_runtime_status.json`. Add `--expect-lightweight-materializations` for
   building-block-only `Send To Phone` runs; this requires one
   `phone_scheduled_block_materialization` event plus matching
   `materialized_blocks/phone_materialized_block_XX.json` and WAV hash evidence
   for every scheduled block, and it compares each materialized trial
   sequence's `trial_uid`, sequential `trial_number`, and
   `building_block_asset_id` order against `run_package_manifest.json`. The
   same run-artifact validator also compares package provenance
   (`participant_roster_count`, `randomization_seed`, and
   `source_segment_hashes`) across the run manifest, `session_metadata` event
   package payload, `reconstruction_contract.json`, and
   `phone_run_catalog_entry.json`, so marker-stream reconstruction evidence
   cannot silently drift away from the packaged randomization/order source. It
   now also checks the `session_metadata` row in `lsl_marker_mirror.csv`
   against `participant_metadata.json`, `haptic_capability.json`, and package
   provenance, including full haptic calibration response rows, so a captured
   marker stream can be audited back to the phone sidecars. The
   same validator also accepts Controller-mode
   `phone_controller_runtime_status.json` and
   `phone_controller_command_outbox.jsonl` artifacts, PC-admin
   `pc_android_lsl_admin_status.json` /
   `pc_android_lsl_command_outbox.jsonl` artifacts from
   `pps-android-lsl-command`, and PC-monitor
   `pc_android_lsl_monitor_report.json` /
   `pc_android_lsl_monitor_events.jsonl` artifacts from
   `pps-android-lsl-monitor`. Controller and PC-admin outbox rows are checked
   for exact row-payload versus command-sample-payload consistency, including
   required `operator_note` note text when that command is used.
    Phone-run `command_diary.jsonl` rows are also checked against matching
    `operator_command` events and native `PPSCommandAcksV1` samples: strict ack
    validation requires the ack payload to match the diary payload and preserve
    the applied command plus package identity, with run id required for
    active-run control commands.
    Add `--expect-artifact-inventory` for new
    phone-run folders/ZIPs where the file inventory should prove relative
    paths, byte sizes, and SHA-256 hashes. Add
    `--expect-phone-owned-data-export` for
    completed phone-owned runs or PC-side mobile completion upload mirrors when
    the `1.Data_min`/`2.Data_max` phone export layer should be present.
3. Emulator smoke test: install APK, run a phone-owned package, export ZIP, and
   validate `lsl_runtime_status.json`. The
   `run_android_companion_emulator_ui_stress.py` report now treats Android live
   LSL as a source-capability/AAR-presence assessment: default builds should
   report `source_supported_default_build_local_mirror_only`, while validation
   builds with the ignored AAR should report that live network validation is
   still required.
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

Strict native validation requires enabled native marker and command transport
plus `stream_descriptions` for the rich marker, numeric trigger, command
signal, and command ack streams. The descriptions must preserve the
PC-compatible channel orders and keep participant demographics out of
discoverable stream names. Controller-mode strict validation similarly requires
stream descriptions for the Android controller command-signal outlet and
command-ack inlet before button presses count as reconstructable native LSL
evidence. PC-admin strict validation requires the same evidence for the PC
command-signal outlet and Android command-ack inlet. PC-monitor strict
validation requires observer-side stream descriptions for the rich marker,
numeric trigger, command-signal, and command-ack inlets. When
`--expect-command-acks` is used on a PC-monitor artifact, each observed
`PPSCommandSignalsV1` command id must have a matching observed
`PPSCommandAcksV1` ack id. The separate monitor reconciliation script compares
PC-captured rich markers against the phone marker mirror by event id, visible
marker fields, and semantic `payload_json` equality, preserving the
`session_metadata` reconstruction payload through the external monitor/XDF
path. When command signals and acks are both captured, it also reconciles
`command_id`, `session_id`, and ack payload command/package identity. It accepts
either `pc_android_lsl_monitor_events.jsonl` or a LabRecorder `.xdf` file when
the optional `pyxdf` dependency is installed.

For new phone-owned run exports, also require the catalog entry:

```powershell
.\.venv\Scripts\python.exe validation_protocols\scripts\validate_android_lsl_runtime_artifact.py <phone-run-dir-or-zip> --expect-run-catalog
```

For building-block-only `Send To Phone` exports, also require the scheduled
block materialization evidence:

```powershell
.\.venv\Scripts\python.exe validation_protocols\scripts\validate_android_lsl_runtime_artifact.py <phone-run-dir-or-zip> --expect-run-catalog --expect-lightweight-materializations
```

For a two-phone Controller-to-Runner check where every button press should have
a matching acknowledgement, validate the Controller outbox as well:

```powershell
.\.venv\Scripts\python.exe validation_protocols\scripts\validate_android_lsl_runtime_artifact.py <phone_controller_command_outbox.jsonl> --expect-native-transport --expect-command-acks
```

Then reconcile the Controller sender artifact against the Runner phone's run
folder or exported ZIP. This proves the sender outbox and receiver
`command_diary.jsonl` agree on the same native command ids, target session,
sender id, command, package identity, and `PPSCommandAcksV1` sample:

```powershell
.\.venv\Scripts\python.exe validation_protocols\scripts\reconcile_android_command_admin_with_phone_run.py <phone_controller_command_outbox.jsonl-or-dir> <phone-run-dir-or-zip> --expect-native-sends --expect-command-acks
```

For a PC-to-phone command check, send commands from the PC helper while the
Android runner is idle with a synced package or actively playing a block:

```powershell
.\.venv\Scripts\pps-android-lsl-command.exe start_experiment --session-id <part_session_id> --token <pairing-token> --package-id <package_id> --require-ack
.\.venv\Scripts\pps-android-lsl-command.exe pause --session-id <part_session_id> --token <pairing-token> --require-ack
.\.venv\Scripts\pps-android-lsl-command.exe resume --session-id <part_session_id> --token <pairing-token> --require-ack
.\.venv\Scripts\pps-android-lsl-command.exe stop_after_block --session-id <part_session_id> --token <pairing-token> --require-ack
.\.venv\Scripts\pps-android-lsl-command.exe operator_note --session-id <part_session_id> --token <pairing-token> --note "participant asked for a pause" --require-ack
```

The `Send To Phone` window can send the same Start/Pause/Resume/Continue/
Snapshot/Stop-after-block/Note commands after package preparation. The Note
command requires text in the operator-note field and sends it as
`operator_note`. The window stores the same PC-admin outbox/status artifacts
under runner logs for that phone transfer, including the row-derived command
source ID in `pc_android_lsl_admin_status.json`.

Then validate the PC-admin outbox/status pair:

```powershell
.\.venv\Scripts\python.exe validation_protocols\scripts\validate_android_lsl_runtime_artifact.py <pc_android_lsl_command_outbox.jsonl> --expect-native-transport --expect-command-acks
```

Use the same sender/receiver reconciliation for PC-admin rehearsals:

```powershell
.\.venv\Scripts\python.exe validation_protocols\scripts\reconcile_android_command_admin_with_phone_run.py <pc_android_lsl_command_outbox.jsonl-or-dir> <phone-run-dir-or-zip> --expect-native-sends --expect-command-acks
```

To monitor whether another PC can observe the Android runner's LSL evidence
stream while commands are being sent:

```powershell
.\.venv\Scripts\pps-android-lsl-monitor.exe --duration-s 30 --require-markers --require-triggers --require-acks --output-dir artifacts\android_lsl_monitor\rehearsal_001
```

Add `--require-commands` when the rehearsal is expected to capture a PC-runner
or Controller-phone `PPSCommandSignalsV1` command stream in addition to the
phone runner's acknowledgement stream. Monitor validation now parses observed
command-signal payloads, requires a pairing token, checks the row `payload_json`
against the serialized sample payload, and requires nonblank note text for
observed `operator_note` commands. Monitor reports also list
`observed_command_signal_ids_without_ack` and
`observed_command_ack_ids_without_signal` so a rehearsal can show exactly which
commands were visible without matching receiver acknowledgement evidence.

Then validate the monitor report:

```powershell
.\.venv\Scripts\python.exe validation_protocols\scripts\validate_android_lsl_runtime_artifact.py artifacts\android_lsl_monitor\rehearsal_001 --expect-native-transport --expect-command-acks
```

To compare the PC-observed monitor rows against the phone's local
`lsl_marker_mirror.csv` from the same run:

```powershell
.\.venv\Scripts\python.exe validation_protocols\scripts\reconcile_android_lsl_monitor_with_phone_run.py <phone-run-dir-or-zip> artifacts\android_lsl_monitor\rehearsal_001 --expect-numeric-triggers --expect-command-acks --output-dir artifacts\android_lsl_monitor\rehearsal_001\reconciliation
```

This reconciliation checks whether the PC saw the same rich marker event ids,
metadata fields, and numeric trigger-code sequence that the phone wrote locally
in `trigger_codes.csv`.
It is still network LSL evidence, not physical vibration/audio timing proof.

Until that strict validator passes together with external LSL/XDF capture, the
phone app remains a local phone-owned runner with LSL-compatible artifacts, not a
publication-grade live LSL broadcaster.
