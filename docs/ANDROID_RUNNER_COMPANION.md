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
beside the phone event log. The command diary mirrors each row into an
`operator_command` event and separates local UI actions (`phone_ui`), internal
runtime actions (`phone_runtime`), and native LSL commands (`native_lsl`); live
native LSL broadcast still requires a pinned liblsl Android native layer.

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
- Discovery: while the companion service is running, the PC emits token-free
  `pps-runner-companion-discovery.v1` UDP packets to multicast
  `239.255.77.83:48767`, limited broadcast `255.255.255.255:48767`, and
  best-effort private/link-local IPv4 directed broadcasts such as
  `192.168.43.255:48767` on a typical phone hotspot. The packet advertises
  host, port, session id, mode, transport, and whether a token is required; it
  never contains `X-PPS-Companion-Token`, participant demographics,
  participant identifiers, or LSL stream/source names. PC serialization and
  Android parsing recursively reject hidden token, participant/demographic, or
  stream-name fields even if the privacy flags claim the packet is safe. The
  packet contract is intentionally local-only:
  `network_scope` is
  `same_lan_or_local_hotspot`, multicast TTL is `1`, accepted modes are
  `pc_runner` and `phone_export`, and accepted transports are `lan`,
  `phone_hotspot`, and `wifi_direct`. Phone-export discovery must include a
  `transfer_id`, but still omits the token. `discovery.broadcast_targets` must
  include `255.255.255.255` and `interface_ipv4_directed_broadcasts` so Android
  can reject weaker packets that do not advertise the directed-broadcast
  fallback. Android's pairing screen can listen for the packet on same-Wi-Fi or
  local phone-hotspot networks, including the broadcast fallbacks, but pairing
  still requires scanning the QR or pasting the full token-bearing URI.
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
`events.csv`, `lsl_marker_mirror.csv`, `trigger_codes.csv`,
`command_diary.jsonl`, `artifact_file_inventory.json`,
`artifact_file_inventory.csv`, `lsl_runtime_status.json`, and
`completion.json` files are local experiment artifacts and are not committed.
Completion uploads that
carry Android response/top-up reconstruction fields also write
`phone_response_ledger.csv`, `phone_topup_plan.json`,
`phone_topup_materialization.json`, `phone_owned_data_export.json`, and a
PC-side `phone_owned_exports/1.Data_min` plus `2.Data_max` mirror beside the
uploaded run folder.

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
- Each local start, `Pause`, `Resume`, and `Stop After Block` button press is
  recorded in `command_diary.jsonl` as `command_source=phone_ui` and mirrored as
  an `operator_command` event. Runtime bookkeeping such as scheduled-block or
  top-up materialization uses `command_source=phone_runtime`, while
  PC/controller LSL commands use `command_source=native_lsl` with ack evidence
  when native LSL is enabled. If the phone is started remotely through the idle
  Runner-mode LSL listener, the resulting run artifact records the remote
  `start_experiment`/`start_part` signal and ack as `native_lsl`, not as a local
  phone UI start.

Packages served from the native runner's `Send To Phone` entry point are
lightweight by default: they omit prepared `block_audio` assets and transfer
only reusable `trial_building_block` WAVs plus the v2 schedule/reconstruction
manifest. Older Focus Mode companion packages still expose prepared block WAVs
for compatibility.

The phone runtime parses PCM WAV blocks and plays them with Android
`AudioTrack`, schedules tactile cue delivery from the AudioTrack playback head,
uses `SystemClock.elapsedRealtime()` for phone-side timestamps, and drives the
Android vibrator service for tactile cue signaling. If a prepared block WAV is
missing but every scheduled trial references a synced `trial_building_block`
asset, the phone can materialize that scheduled block locally by deterministic
PCM WAV concatenation, then run the same AudioTrack playback-head cue scheduler.
Treat it as an experimental mobile collection mode until physical phone timing
validation is added.

Synced v2 packages include:

- prepared block WAV assets with role `block_audio`, which remain the default
  compatibility playback path
- optional reusable Segment 3 trial WAV assets with role
  `trial_building_block`, used by lightweight scheduled-block replay and
  phone top-up logic
- `reconstruction` metadata with the Segment 0-6 hierarchy, source Segment 6
  hashes, and schedule hash
- provenance metadata with `participant_roster`, `randomization_seed`, and
  `source_segment_hashes` for the Segment 6 setup manifest, Segment 6 order
  CSV, accepted Segment 5 manifest, and source block CSV hashes
- `lsl` metadata declaring `PPSMarkersV2`, `PPSTriggerCodes`,
  `PPSCommandSignalsV1`, and `PPSCommandAcksV1`

Validate exported or prepared v2 packages before relying on phone-owned
execution:

```powershell
.\.venv\Scripts\python.exe validation_protocols\scripts\validate_mobile_phone_package.py <manifest-json-or-package-dir> --require-phone-owned-session --require-building-blocks
```

For building-block-only `Send To Phone` packages, add
`--require-lightweight-scheduled-blocks`; this fails if any `block_audio` asset
is present or any scheduled block cannot be reconstructed from
`trial_building_block` assets.

The validator checks the Segment 0-6 to phone-runtime hierarchy, schedule hash,
source provenance roster/seed/hash consistency across the package manifest,
`session_metadata` event package payload, `reconstruction_contract.json`, and
`phone_run_catalog_entry.json`, block/order consistency, reusable
building-block references, asset availability, AudioTrack playback-head timing
contract, privacy-safe Android LSL stream names, required phone command set,
and the phone-run `asset_strategy` plus `reconstruction_contract.json`
consistency across status, manifest, reconstruction, completion, and catalog
artifacts. It
also checks `lsl_runtime_status.json` `stream_descriptions` when present, and
requires them in strict native mode, so `PPSMarkersV2`, `PPSTriggerCodes`,
`PPSCommandSignalsV1`, and `PPSCommandAcksV1` keep their expected LSL roles,
formats, source identities, and PC-compatible channel order. The validator also
checks `lsl_marker_mirror.csv` or embedded `lsl_marker_mirror` rows against
completion events, marker payload JSON, Android phone event codes, and duplicate
event ids so local phone evidence stays reconstructable even before comparing it
with a PC-side LSL monitor. Participant and haptic sidecars are also checked
when present: `participant_metadata.json` must use metadata-payload-only privacy
and match embedded/catalog run identity, while `haptic_capability.json` must
declare the vibrator/amplitude policy and any calibration result consistently.
When participant metadata says the threshold came from Android haptic
calibration, strict validation also requires the haptic calibration result to
match the participant threshold/status and, on amplitude-controlled devices, the
deterministic threshold-percent-to-`VibrationEffect` amplitude mapping.
For strict app-private participant/session catalog reconstruction, add
`--expect-run-catalog --expect-run-catalog-index`; this requires the per-run
`phone_run_catalog_entry.json`, the exported/global
`phone_run_catalog/index.json`, each participant `runs.jsonl`, and
`latest_run.json` to agree on run identity, latest-run pointers, artifact file,
native LSL status booleans, and reconstruction schedule hash.
For strict phone event diary reconstruction, add `--expect-event-diary`; this
requires `events.csv` to be present and to match the embedded
`completion.json`/`latest_events.json` event list by event id, event type,
run/package identity, phone timestamps, duplicate-id checks, and primitive
event fields. When a completion `summary` is present, its
`total_event_count`, `lsl_marker_mirror_count`, and `command_diary_count` must
also match the event, marker, and command diary artifacts. This is the quick
human-readable log of what the phone runtime did before the richer marker/XDF
checks.
Phone-run command diaries are also checked against matching `operator_command`
events when present, including the command source and payload. When both
`command_diary.jsonl` and embedded `completion.json`/`latest_events.json`
`command_diary` rows are present, the validator checks that schema, source,
status, payload, ack evidence, timing, and identity fields agree for each
command id. For native `PPSCommandAcksV1` rows, strict validation also parses
the ack sample payload and compares it with the diary payload, requiring the
ack payload to preserve the applied command plus package identity and, for
active-run commands such as pause/resume/stop-after-block, the phone run id.
With `--expect-command-acks`, the completion `summary` native command counters
must also agree with the diary: received commands, sent ack samples, failed ack
sends, and rejected commands are counted from the `native_lsl` rows.
New runs should distinguish `phone_ui`, `phone_runtime`, and `native_lsl`; the
validator still accepts the older `phone_ui_or_runtime` label for historical
artifacts.
For strict run-folder file reconstruction, add `--expect-artifact-inventory`;
this requires `artifact_file_inventory.json` to list every run-folder file
except the inventory sidecars themselves with relative paths, byte sizes, and
SHA-256 hashes that match the folder or ZIP contents. Completed runs must also
advertise the JSON and CSV inventory sidecars through
`completion.json`/`latest_events.json` `artifact_file_inventory_artifact`, and
strict validation checks that the advertised filenames, schema, and
`self_included=false` flag match the sidecars on disk or in the ZIP.
For strict local numeric-trigger reconstruction, add
`--expect-trigger-code-mirror`; this requires `trigger_codes.csv` to be present
and to match the `event_id`, `event_code`, `event_type`, `trigger_key`, and
phone elapsed-time sequence implied by `lsl_marker_mirror.csv`. This is the
phone-local expected `PPSTriggerCodes` mirror used before or alongside PC-side
LSL/XDF monitor reconciliation. When `--expect-native-transport` is used on a
completed phone-run folder with marker evidence, strict validation also checks
the completion `summary`: `native_lsl_pushed_count` must equal the local marker
mirror count and `native_lsl_failed_count` must be zero, so native Android LSL
claims cannot hide dropped rich/numeric marker pushes. Strict native validation
also checks the per-stream counters:
`native_lsl_rich_marker_pushed_count` and
`native_lsl_numeric_trigger_pushed_count` must each equal the marker mirror
count, while their failed counters must be zero. This prevents a partial
rich-marker-only or trigger-only push from being treated as a complete native
broadcast.
For lightweight scheduled-block reconstruction, add
`--expect-lightweight-materializations`; this requires every
`trial_building_blocks_only` package block to have a
`phone_scheduled_block_materialization` event, a matching
`materialized_blocks/phone_materialized_block_XX.json` sidecar, a generated WAV
whose SHA-256 matches the sidecar, and a materialized trial sequence whose
`trial_uid`, sequential `trial_number`, and `building_block_asset_id` order
matches `run_package_manifest.json`. This lets a six-building-block phone
package be audited for participant-specific playback-order drift after export.
For phone-owned timing reconstruction, add
`--expect-audiotrack-timing-evidence`; this requires `block_start` events to
declare `audio_timing_strategy = audiotrack_pcm_wav_playback_head` with positive
PCM WAV facts, every block to have a matching `audio_playback_start` event after
`AudioTrack.play()` with playback-head origin, state, and buffer-size fields, and
`vibration_cue` events to carry playback-head scheduler fields
(`scheduled_audio_frame`, `audio_playback_head_frame`,
`audio_delivery_elapsed_realtime_ms`, and cue jitter). The validator checks that
the playback-start marker follows its block start, the track reports `playing`,
buffer bytes match the PCM frame format, the scheduled frame agrees with rounded
scheduled block time and sample rate, cue frames stay inside the block frame
count, frame jitter and millisecond jitter agree with the block sample rate, and
cue delivery elapsed time is late enough for the reported playback-head frame
since the matching `audio_playback_start`.
This is phone-runtime timing evidence, not a physical audio/vibration onset
claim.
For phone-owned response and top-up reconstruction, add
`--expect-phone-topup-evidence`; this requires `phone_response_ledger.csv` or
embedded `phone_response_ledger`, `phone_topup_plan.json`, the
`phone_topup_materialization.json` sidecar, and a matching
`phone_topup_block.wav` SHA-256 when the top-up status is `materialized`.
Strict lightweight scheduled-block validation automatically enables this check
because building-block-only phone runs should prove both the scheduled-block
fallback and the missed-trial rescue/top-up chain.
For completed phone-owned participant exports, add
`--expect-phone-owned-data-export`; this requires `phone_owned_data_export.json`,
an app-private `phone_owned_exports/1.Data_min/` participant CSV plus
`master_successful_participants.csv` with the same 17-column public schema used
by the PC runner, and a `phone_owned_exports/2.Data_max/<participant>/runs/`
copy of the reconstructive phone-run folder.
PC-side mobile completion uploads with embedded Android response ledgers now
write the same phone-owned data-export sidecars and mirror tree under
`runner_logs/mobile_phone_runtime/<participant>/<package_id>/phone_owned_exports/`.
The PC upload mirror also writes `run_package_manifest.json`,
`reconstruction_contract.json`, `artifact_file_inventory.json`, and
`artifact_file_inventory.csv` beside `completion.json` before copying the run
folder into the PC-side `2.Data_max` mirror, so uploaded Android completions
carry the same file-diary reconstruction spine as exported phone run folders.
If an older or sparse phone payload omits detailed `lsl_runtime_status` fields,
the PC mirror fills missing stream names, command/ack schemas, channel labels,
privacy fields, and `stream_descriptions` from `run_package_manifest.json`
while preserving phone-provided native-transport availability/status values.
When validating PC-runner or Controller-phone administration, add
`--expect-command-acks`; for phone-run artifacts this now requires
`command_diary.jsonl` or embedded `command_diary` rows with native
`PPSCommandAcksV1` samples, ack payloads that match the command diary payload,
and matching `operator_command` events. PC-runner administration status also
includes `stream_descriptions` for the PC
command-signal outlet and Android command-ack inlet, including the row-derived
command source ID when an outbox row has been written.

Phone-owned local artifacts now include `participant_metadata.json`,
`haptic_capability.json`, `events.csv`, `lsl_marker_mirror.csv`,
`trigger_codes.csv`, `command_diary.jsonl`, `artifact_file_inventory.json`,
`artifact_file_inventory.csv`, `lsl_runtime_status.json`, `phone_response_ledger.csv`,
`phone_topup_plan.json`, `phone_topup_materialization.json`, any
`phone_topup_block.wav`, reconstruction/package snapshots, and
`completion.json` in the exported phone session ZIP. The exported ZIP also
includes snapshots of the app-private `phone_run_catalog/` and
`phone_owned_exports/` trees when present. The catalog snapshot includes the
global `index.json`, participant `runs.jsonl`, and `latest_run.json` pointers
used to reconstruct which phone-owned runs happened for each participant. The
phone-owned export snapshot carries the minimal public CSV layer and the rich
per-run backup mirror. The phone preserves the package `asset_strategy` across
the parsed model, LSL runtime status, JSON/native LSL stream description metadata,
reconstruction snapshot, and phone run catalog so a lightweight
`trial_building_blocks_only` run can be distinguished from a prepared-block WAV
compatibility run during later reconstruction. The first `session_metadata`
marker and rich-marker/numeric-trigger stream-description
`session_metadata_json` also carry the package provenance summary: schedule
hash, participant roster count, randomization seed, and source segment hash
summary. When participant/haptic sidecars are present, the same
`session_metadata_json` also carries compact `participant_metadata_summary` and
`haptic_capability_summary` objects so age, handedness, gender, tactile
threshold source/value, calibration status, and recommended phone vibration
amplitude reconstruct from LSL metadata while stream names remain generic. Full
calibration response rows stay in the haptic sidecar and first marker payload.
Strict artifact validation checks that the exported
`lsl_runtime_status.json` stream descriptions match the package provenance
and participant/haptic summaries whenever native evidence, provenance-bearing
packages, or participant sidecars are expected. It also parses
`lsl_marker_mirror.csv` and requires the `session_metadata` marker payload to
match `participant_metadata.json`, `haptic_capability.json`, and any
`run_package_manifest.json` provenance fields, so the local marker mirror is a
usable reconstruction anchor rather than only an event echo. The app also
carries the Segment 0-6 hierarchy into the session metadata marker payload and
`reconstruction_contract.json`, letting strict validation reject hierarchy drift
inside phone-owned artifacts. Participant age, handedness,
gender, and tactile threshold stay in metadata and marker payloads rather than
discoverable LSL stream names.

Default Android builds do not ship liblsl. If a local validation build adds the
ignored `android/runner-companion/app/libs/liblsl-Android.aar`, runner mode opens
native `PPSMarkersV2` / `PPSTriggerCodes` outlets and can resolve
`PPSCommandSignalsV1` to emit token-gated `PPSCommandAcksV1`. When Runner mode
is idle with a synced selected package, it also keeps a native idle command
listener open so a PC runner or Controller phone can send `start_experiment` /
`start_part` and receive an ack before the phone launches the same run path as
the local Start button. Current active-run command handling records
snapshot/note/continue actions, applies pause/resume through the phone-owned
`AudioTrack` pause gate during active phone blocks, and records
`phone_playback_pause` / `phone_playback_resume` diary and marker-mirror events.
The local Runner-mode Pause and Resume buttons call the same phone-owned pause
gate and write the same command diary/operator-command evidence with
`command_source=phone_ui`.
While paused, the AudioTrack wait loop keeps polling native commands so a
PC-runner or Controller-phone `resume` command can actually release the gate.
Stop-after-block now records a request, lets the active phone block finish,
records the block-boundary stop, skips remaining scheduled phone blocks and
phone top-up, and closes the local run artifacts with
`completion_reason=stopped_after_block`.

PC-side monitoring with `pps-android-lsl-monitor` observes
`PPSMarkersV2`, `PPSTriggerCodes`, `PPSCommandSignalsV1`, and
`PPSCommandAcksV1` during rehearsals. Its report/status pair now carries
`stream_descriptions` for those four observer-side inlets, and monitor event
rows extract command-signal ids, sender ids, command names, and payload JSON so
PC-runner or Controller-phone commands can be reconstructed together with the
phone runner's acknowledgements. Strict monitor validation now parses observed
command-signal payloads, requires token evidence, compares row `payload_json`
against the serialized sample payload, and requires note text when the observed
command is `operator_note`. With `--expect-command-acks`, strict monitor
validation also requires every observed command-signal id to have a matching
ack id, and the report exposes unmatched ids in both directions for debugging
PC-runner or Controller-phone rehearsals. The offline
`reconcile_android_lsl_monitor_with_phone_run.py` script compares PC-captured
rich marker rows back to the phone `lsl_marker_mirror.csv`, including semantic
`payload_json` equality, so a captured `session_metadata` payload cannot drift
away from the phone-owned reconstruction payload without a reconciliation
failure. When the same monitor capture includes command signals and command
acks, the reconciler also pairs them by `command_id`, detects missing or extra
acks, and compares ack payload command/package/target identity against the
original command payload, including the non-secret split-part fields that define
which phone-owned part was administered. The same reconciler can load
LabRecorder `.xdf` captures directly via the optional `pyxdf` dependency and
converts recognized Android LSL streams into the durable PC monitor row schema
before comparison.

Controller mode always writes `phone_controller_command_outbox.jsonl` as the
local audit trail. In a native liblsl validation build it also keeps a
`PPSCommandSignalsV1` outlet open while Controller mode is selected, sends button
presses over LSL, polls for matching `PPSCommandAcksV1` samples, and records the
native send/ack result in the outbox row plus
`phone_controller_runtime_status.json`. That status includes controller
`stream_descriptions` for the command-signal outlet and command-ack inlet, so
strict validation can reject channel-order or source-identity drift before
controller button presses are treated as live LSL evidence. Controller target
identity is resolved from the synced manifest first, then from the package-list
summary fields `session_group_id`, `part_session_id`, and `part_number`, and
only then from the pairing session. This lets an unsynced Controller phone send
Start/Pause/Resume/Continue/Snapshot/Stop After Block/Note to the exact split
part-session id that Runner mode is listening on. The Controller screen exposes
Start, Pause, Resume, Continue, Stop After Block, and Snapshot when the selected
package advertises those commands; Stop After Block sends the same
`stop_after_block` signal used by the PC helper. When `operator_note` is
advertised, Controller mode also shows a compact note field and sends the note
inside the token-gated command payload so operator observations reconstruct
through the same outbox, LSL command, ack, and receiver diary path. The Android
LSL artifact validator rejects Controller or PC-admin command outbox rows whose
stored `payload` object differs from the serialized command-sample payload, and
it requires nonblank note text for `operator_note`. Under
`--expect-command-acks`, Controller and PC-admin outbox validation also parses
the stored ack sample payload: it must not echo the pairing token, and it must
agree with the command sample on command, target session, package, participant,
part session, session group, part number, requester, and source-behavior fields
whenever those non-secret fields were available. Runner-mode ack/diary payloads
echo the same accepted target identity from the command sample. Commands that
explicitly name a different package or split-part identity are rejected before
the phone applies a local state change.

In native liblsl builds, Runner mode resolves up to eight visible
`PPSCommandSignalsV1` streams and polls every opened command inlet, so a PC
helper and one or more Controller phones can coexist on the same Wi-Fi/LSL
network. Controller mode also resolves multiple `PPSCommandAcksV1` streams when
waiting for the matching ack. The command token, target session, package, and
split-part fields remain the acceptance gate after a sample is received.

For two-phone or PC-to-phone rehearsals, run
`validation_protocols/scripts/reconcile_android_command_admin_with_phone_run.py`
after the sender outbox and Runner phone folder/ZIP exist. It compares
Controller or PC-admin native-sent command rows against the Runner phone's
`native_lsl` command diary rows by `command_id`, target session, sender id,
command, package identity, non-secret target payload fields, and exact
`PPSCommandAcksV1` sample. This is the offline artifact proof that a controller
button press or PC helper command was received and acknowledged by the phone
runner; it is still separate from live network/XDF and physical timing proof.

The PC runner's Send To Phone window mirrors that administration path. After a
phone package is prepared it can send Start, Pause, Resume, Continue, Snapshot,
Stop After Block, and Note over `pps-android-lsl-command`; the Note command
requires text in the operator-note field and writes the same `operator_note`
payload evidence as the Android Controller mode.

Android vibration calibration is device-limited. The phone-run metadata panel
now includes a `Haptic Calibration` control. On phones with amplitude control it
runs an ascending perceptual threshold check over fixed percent levels, saves
the first felt level as `pps-android-phone-haptic-calibration.v1`, copies that
percent into participant metadata, and uses the mapped `VibrationEffect`
amplitude for phone vibration cues. On phones with a vibrator but no amplitude
control, the app records a binary detection-only calibration and uses
default-amplitude pulses. The run-artifact validator cross-checks the
participant metadata threshold, haptic sidecar recommendation, calibration
result, response rows, and amplitude mapping. These values are phone-vibrator
working thresholds, not calibrated physical vibration-strength or Woojer timing
measurements.

FFmpeg-style synthesis is technically possible on Android through native FFmpeg
builds, but the app does not depend on FFmpegKit because that wrapper project is
retired. Scheduled-block fallback and phone top-up both use a small deterministic
PCM WAV assembler over a broad FFmpeg runtime. All source WAVs must already have
matching PCM format, sample rate, channel count, bit depth, and block alignment;
future requirements for general resampling or transcoding would need a separate
native audio/FFmpeg integration.

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
