# Module Map

This is the compact navigation map for future agents. Read it after `For-AI/README.md` and before structural edits.

## Current Ownership

- Dashboard backend and Segment 0-6 materialization: `src/peripersonal_space_toolkit/dashboard_app.py`.
- Cross-platform native Designer shell: `designer_shell.py`; loopback bootstrap-cookie exchange, system WebView selection, single-instance lock, geometry persistence, external-browser handoff, and controlled profile-bundle save.
- Versioned participant order and portable profile interchange: `participant_orders.py` owns `seeded_factoradic_cycle.v1`; `profile_bundle.py` owns `.pps-profile` verification and installation.
- Designer frontend source/build: `dashboard/{index.html,styles.css,app.js,designer_main.js}` plus its Vite configuration; `dashboard/compiled/` is the shared native/GitHub-Pages artifact.
- Designer packaging: `windows/PPSDesigner.spec`, `windows/Build_PPS_Designer.ps1`, and `packaging/linux/` for the generic source launcher and DEB/RPM staging.
- Dashboard backend helper seams: `src/peripersonal_space_toolkit/dashboard_backend/`.
- Browser dashboard/static GitHub Pages surface: `src/peripersonal_space_toolkit/dashboard/`, root `index.html`, `.nojekyll`, `CNAME`.
- Loudness policy, SPL estimate metadata, dB/RMS helpers, final-active-window calibration rules, and standalone loudness-manifest helpers: `src/peripersonal_space_toolkit/loudness.py`.
- Shared stored-profile catalogue, runner memory, acquisition bridge, and output diary helpers: `profile_memory.py`.
- Runtime package preparation and participant playback: `session_runner.py`, `focus_app.py`, `focus_launch.py`, with runner-owned LabRecorder RCS subprocess capture isolated in `labrecorder_capture.py`.
- Participant tactile detection-threshold calibration: `tactile_calibration/` owns the `two_down_one_up_detection_threshold.v2` Output 3/4 assay, the 0.5% Output 3/4 cap, the fine 0.01-0.5% staircase grid, transient 44.1 kHz three-channel stimulus generation, adaptive-staircase/reversal/lower-bound-censoring metadata, response-window/ITI-jitter timing metadata, participant calibration report/CSV/latest-pointer persistence, and schema helpers; `focus_app.py` owns the native runner `Tactile Threshold` button, the capped Output 3/4 UI/settings/application path, calibration monitor window, target-click interception, one-shot calibration-target cursor recentering, success display with adopted threshold value, automatic return to the Experiment Control screen after successful calibration, per-participant reload/application, and session-metadata handoff. If resuming the 2026-06-29 interrupted packaging work, read `For-AI/tactile_calibration_handoff_20260629.md`.
- Focus Mode phone companion and phone-transfer runtime: `runner_companion.py` owns the FastAPI/WebSocket token-gated LAN service, HTTP-safe bridge-error handling, v1/v2 QR payload helpers, the token-free `pps-runner-companion-discovery.v1` UDP multicast/limited/directed-broadcast endpoint advertisements, token-gated setup/start/pause/resume/continue routes, and token-gated `/api/mobile/...` package routes; `mobile_phone_runtime.py` owns phone package list/manifest schemas, v2 reconstruction/LSL contracts, prepared block WAV and optional `trial_building_block` asset checksum export, CSV-derived phone cue/trial payloads, uploaded PC-copy artifact writing including `run_package_manifest.json`, `reconstruction_contract.json`, `lsl_marker_mirror.csv`, `trigger_codes.csv`, command diary, manifest-derived fallback/enrichment for sparse `lsl_runtime_status` uploads including `role="runner"` status/stream-description labels, Android response/top-up sidecars, `artifact_file_inventory.json`/`.csv`, and a PC-side `phone_owned_exports/1.Data_min` plus `2.Data_max` mirror when completion uploads include a phone response ledger, `phone_owned_session` manifest flags, and `validate_mobile_package_manifest()` for checking Segment 0-6 hierarchy, schedule hashes, asset/building-block references, AudioTrack timing contracts, and privacy-safe Android LSL names; `focus_app.py` owns the Qt-thread PC-control bridge, transfer-only `Send To Phone` bridge, Send To Phone Phone LSL Control strip that calls `android_lsl_admin.py` after package preparation for Start Full/Start Part/Pause/Resume/Continue/Snapshot/Stop-after-block/Note, snapshot/command state, mobile package access to active/sibling split part packages, separate mutually exclusive Pause/Resume controls, hidden internal close/stop cleanup, post-run timer responsiveness while the service is active, and Wi-Fi Direct availability messaging; `android/runner-companion/` owns the native Kotlin/Compose phone app, its two modes (`PC Runner Control` and `Run Experiment On Phone`), package sync/full-experiment phone runtime controls, phone-owned local Pause/Resume/Stop-after-block controls, phone-owned local artifact/ZIP export with `phone_run_catalog/` and `phone_owned_exports/` snapshots, app-private `phone_run_catalog` participant/session index, app-private `1.Data_min`/`2.Data_max` phone export helpers, phone-run participant metadata/haptic-capability capture, local PPSMarkersV2-shaped marker mirror, command diary, runner `lsl_runtime_status.json`/stream descriptions with explicit `role="runner"`, controller-mode command outboxes with live ack validation metadata (`ack_valid`, `ack_validation_status`, `ack_validation_reason`), discovery-packet parsing/listening, and its landscape runner-confirmed cue/click timeline visualization with inline SOA and RT annotations. Android completion uploads now include response ledger/top-up reconstruction fields when a run package is available, so the PC service can write those same reconstruction sidecars and a rehashable file diary. Android timeline scaling, annotation visibility, and density behavior lives in `TimelineLayoutModel.kt`; phone-runtime package parsing lives in `MobileRuntimeModels.kt`, which now preserves reconstruction `study_hierarchy` and source setup path; phone-owned `reconstruction_contract.json` writes that Segment 0-6 hierarchy alongside schedule/building-block evidence; phone-owned run catalog and data-export helpers live in `PhoneRunCatalog.kt`; phone-owned PCM WAV parsing plus AudioTrack playback-start evidence, playback-head cue scheduling, pause gating, and while-paused native-command polling lives in `PhoneAudioPlayback.kt`; phone-vibrator threshold calibration lives in `PhoneHapticCalibration.kt` and remains a device-limited perceptual working threshold, not Woojer/physical timing evidence. Default Android builds still use local marker mirrors instead of live LSL; local validation builds can include the ignored liblsl AAR to enable the optional native marker/trigger/command/ack bridge. Companion discovery never carries pairing tokens, demographics, or participant-coded stream names. Demographics and tactile thresholds must stay in metadata/payloads by default rather than discoverable stream names.
- Android phone-owned data export manifests live in `PhoneRunCatalog.kt`. `phone_owned_data_export.json` now carries `session_group_id` alongside run/session/part identity plus portable archive-relative `portable_paths` for `phone_owned_exports/1.Data_min` participant/master CSVs and the `2.Data_max/<participant>/runs/<run_id>` mirror with completion/export/inventory files; app-private absolute paths remain only for local UI convenience.
- PC-side phone-owned upload mirrors in `mobile_phone_runtime.py` write the same `phone_owned_data_export.json` identity and `portable_paths` contract for uploaded completed phone-owned runs, so phone ZIP exports and PC upload mirrors use the same archive-relative reconstruction map and preserve split-session group stitching.
- Android phone-side LSL protocol scaffolding lives in
  `PhoneLslProtocol.kt`. It mirrors the PC runner command/ack channel order,
  token-gates `PPSCommandSignalsV1` samples, emits applied/rejected
  `PPSCommandAcksV1` samples after local handlers return, writes
  `lsl_runtime_status.json` for phone-owned runs, includes
  `pps-android-lsl-stream-descriptions.v1` stream descriptions for the marker,
  trigger, command-signal, and command-ack LSL streams, and separates bridge,
  marker-transport, and command-transport status. The phone-run artifact
  validator now treats those stream descriptions as strict native
  reconstruction evidence, including PC-compatible channel order, source IDs,
  and the privacy rule that demographics stay out of stream names. Phone-run
  command ack payloads now declare `receiver_role="runner"`, command diaries
  distinguish `phone_ui`, `phone_runtime`, and `native_lsl`
  command sources and mirror each row as an `operator_command` event so direct
  Android button presses and received LSL commands reconstruct through the same
  event/marker path. Native receiver rows now preserve `command_channels` plus
  the exact received `PPSCommandSignalsV1` `command_sample` beside
  `ack_channels` and `ack_sample`, so the phone diary can prove which
  token-gated command sample it acted on. Idle Runner-mode `start_experiment`
  / `start_part` commands now carry their received signal, raw command sample,
  ack sample, and `ack_sent` outcome into the newly launched `PhoneRunSession`
  so remotely started phone runs are recorded as `native_lsl` receiver-side
  command evidence rather than local UI starts. For multi-part preparations,
  idle `start_experiment` now requires the
  full listed package set to be synced and then launches that full synced order;
  `start_part` remains the selected-package path, and incomplete multi-part
  starts are rejected with package/sync counts in the ack payload instead of
  silently launching only Part 01.
  `MainActivity.kt` owns the Runner-mode idle command listener that acks native `start_experiment` /
  `start_part` before launching the selected synced package or full synced package order. Default builds without the
  local liblsl AAR still report native transport unavailable; do not present
  local marker mirrors or protocol unit tests as live Android LSL evidence.
- Android phone-owned scheduled-block and top-up PCM materialization lives in
  `PhoneTopupAssembler.kt`. Prepared `block_audio` WAVs remain the default
  phone playback path, but `MainActivity.kt` can fall back to a
  `trial_building_block`-only scheduled block by concatenating matching PCM WAV
  data chunks into `materialized_blocks/phone_materialized_block_XX.wav`,
  recalculating trial/cue timing from frame counts, and recording
  `phone_scheduled_block_materialization` before the same AudioTrack
  playback-head cue scheduler runs. Source-contract tests pin this path and
  phone top-up to deterministic PCM concatenation with explicit format,
  sample-rate, channel-count, bit-depth, and block-alignment guards rather than
  FFmpeg/FFmpegKit.
- Lightweight phone package export/validation lives in
  `mobile_phone_runtime.py`. `include_block_audio=False` produces
  `asset_strategy = trial_building_blocks_only` manifests, keeps block
  `audio_asset_id` values as compatibility ids, omits `block_audio` assets,
  requires every scheduled trial to reference an available
  `trial_building_block`, and is enforced by
  `validate_mobile_phone_package.py --require-lightweight-scheduled-blocks`.
  The v2 manifest now also carries explicit package provenance:
  `participant_roster`, `randomization_seed`, and `source_segment_hashes` for
  the source Segment 6 setup manifest/order CSV, accepted Segment 5 manifest,
  and scheduled source block CSV hashes; `validate_mobile_package_manifest()`
  rejects roster/source-hash drift when those fields are present.
  `_PhoneTransferBridge` in `focus_app.py` uses this lightweight path for the
  native runner's `Send To Phone` transfer bridge; regular Focus Mode companion
  packages still default to prepared block WAV assets. Android parses this
  strategy plus provenance in `MobileRuntimeModels.kt` and preserves it in
  runtime status, stream description metadata, local reconstruction snapshots,
  and `PhoneRunCatalog.kt` entries so offline reviewers can distinguish
  lightweight building-block materializations from prepared WAV replay and
  trace them back to the source randomization/order evidence. The
  `session_metadata` event, native liblsl XML descriptions, and exported
  `lsl_runtime_status.json` rich-marker/numeric-trigger stream descriptions
  carry the same `session_metadata_json` provenance summary for marker-stream
  reconstruction, including the package asset strategy, Segment 0-6
  `study_hierarchy`, source run-setup manifest path, and source setup SHA-256.
  `validate_android_lsl_runtime_artifact.py` now enforces that package
  provenance across `run_package_manifest.json`, the `session_metadata` event
  package payload, `reconstruction_contract.json`,
  `phone_run_catalog_entry.json`, and stream-description metadata, comparing the
  roster count, randomization seed, Segment 6/5 hashes, phone-side source block
  CSV count, package asset strategy, study hierarchy, source setup path, and
  source setup SHA-256. PC upload mirrors that backfill sparse
  `lsl_runtime_status` payloads must preserve the same stream-description
  `session_metadata_json` fields from the v2 manifest reconstruction contract.
  Rich-marker and numeric-trigger stream descriptions also
  carry compact `participant_metadata_summary` and
  `haptic_capability_summary` objects when the phone has those sidecars; the
  Android validator compares those summaries against `participant_metadata.json`
  and `haptic_capability.json` so age/handedness/gender/tactile threshold and
  phone-vibration recommendations remain reconstructable from LSL metadata
  without putting demographics into stream names. The same validator now parses
  `lsl_marker_mirror.csv` and checks the local `session_metadata` marker
  payload against `participant_metadata.json`, `haptic_capability.json`, and
  package provenance, including full haptic calibration response rows.
- Optional native Android LSL marker/command transport lives in
  `PhoneNativeLslBridge.kt`. A local ignored
  `android/runner-companion/app/libs/liblsl-Android.aar` is included by Gradle
  when present; the bridge reflects `edu.ucsd.sccn.LSL`, creates
  `PPSMarkersV2`/`PPSTriggerCodes` outlets before `session_metadata`, pushes
  every local marker mirror row while preserving CSV artifacts, records separate
  rich-marker and numeric-trigger native push/failure counters, resolves
  up to eight visible `PPSCommandSignalsV1` command streams, retries command
  stream resolution during active phone playback if needed, polls every opened
  command inlet so PC-admin and Controller-phone senders can coexist on the same
  LSL network, emits token-gated `PPSCommandAcksV1`, and creates a
  controller-side `PPSCommandSignalsV1` outlet with optional multi-stream
  `PPSCommandAcksV1` polling while Controller mode is selected. The current
  phone command handler records snapshot/note/continue actions, applies
  pause/resume through the phone-owned `AudioTrack` pause gate during active
  blocks, and applies stop-after-block by finishing the current block, recording
  `phone_stop_after_block_request` / `phone_stop_after_block_boundary`, and
  skipping remaining phone blocks plus phone top-up. Native `request_snapshot`
  acks carry the versioned `pps-android-phone-runtime-command-state.v1` payload
  with run lifecycle, active block, event/marker/command counts, tap counts,
  pause/resume/stop-after-block/top-up flags, and Android wall/elapsed clocks
  for PC or Controller-phone monitoring. Strict native validation must require
  both
  `native_marker_transport_enabled=true` and `command_receiver_available=true`
  plus enabled bridge transport details.
- PC monitor reconciliation is in
  `validation_protocols/scripts/reconcile_android_lsl_monitor_with_phone_run.py`.
  It compares phone `lsl_marker_mirror.csv` rows with PC-captured
  `PPSMarkersV2` rows by event id, marker fields, numeric trigger sequence, and
  canonicalized rich-marker `payload_json`, so external monitor/XDF evidence
  must preserve the same `session_metadata` reconstruction payload. The loader
  accepts PC monitor JSONL/report artifacts and LabRecorder `.xdf` files when
  optional `pyxdf` is available. It also pairs captured `PPSCommandSignalsV1`
  and `PPSCommandAcksV1` samples by `command_id`, flags missing/extra acks, and
  compares ack payload command/package identity to the source command payload.
  Captured command-signal payloads must carry `token` or `companion_token`,
  `operator_note` commands must include a nonblank `note`, and the summarized
  row `payload_json` must match the raw LSL sample payload channel. Monitor
  rows also flatten non-secret command target identity from observed command
  and ack payloads, and strict artifact validation checks those fields against
  the raw sample payload so monitor audit tables cannot drift from captured
  command samples. Monitor reports also aggregate those target identity sets,
  and the validator recomputes them from event rows so report summaries cannot
  drift from the JSONL evidence. Payload drift is reported with redacted
  placeholders so pairing secrets stay out of validation artifacts. Ack payloads
  that echo pairing tokens or omit `receiver_role=runner` remain invalid, and
  strict artifact validation rejects orphan `PPSCommandAcksV1` ids that lack captured
  `PPSCommandSignalsV1` rows. The monitor reconciler also checks rejected
  `PPSCommandAcksV1` payloads for the structured rejection schema and
  receiver/requested identity fields.
- Sender/receiver command-admin reconciliation is in
  `validation_protocols/scripts/reconcile_android_command_admin_with_phone_run.py`.
  It compares Android Controller or PC-admin native command outboxes against the
  Runner phone `command_diary.jsonl` by command id, target session, sender id,
  command, package identity, exact received `PPSCommandSignalsV1`
  `command_sample`, and exact `PPSCommandAcksV1` sample so two-phone or
  PC-to-phone command rehearsals have an offline artifact gate before live
  XDF/physical validation claims. The reconciler also compares the sender row
  payload with the serialized `PPSCommandSignalsV1` payload and requires both
  sender and phone received command sample payloads to contain `token` or
  `companion_token`. It also requires sender-observed and phone-emitted ack
  payloads to carry `receiver_role=runner`, so Controller-mode acks cannot be
  confused with Runner-phone acknowledgements. For rejected acks it now also enforces
  `pps-android-phone-command-rejection.v1` schema/reason,
  `rejected_before_handler`, receiver/requested identity fields, and supported
  commands on both sender and phone ack payload copies.
- Android controller-role scaffolding lives in `PhoneControllerCommands.kt` and
  the `Runner` / `Controller` toggle inside `PhoneRuntimeScreen`. Controller
  mode writes token-gated command samples to
  `phone_controller_command_outbox.jsonl` plus
  `phone_controller_runtime_status.json`; default builds remain local-outbox
  only, while native liblsl validation builds also send button presses over a
  long-lived `PPSCommandSignalsV1` outlet and record native send/ack outcomes in
  the outbox row. Controller outbox rows and runtime status flatten non-secret
  target session/part/group identity alongside the serialized token-bearing
  command sample so audit tables remain reconstructable without parsing only
  the payload. Controller targets resolve from the synced manifest first,
  then from package-list summary identity (`session_group_id`,
  `part_session_id`, `part_number`), then from the pairing session, so an
  unsynced Controller phone can address the exact split part-session id that
  Runner mode listens on. Controller mode exposes `Start Full`, `Start Part`,
  Pause, Resume, Continue, Snapshot, Stop After Block, and Operator Note
  when those commands are advertised by the selected package, allowing two-phone
  rehearsals to request the same boundary stop as the PC helper and to record
  operator observations as typed command payloads. Runner-mode command acks now
  echo non-secret accepted target identity from the command sample
  (`package_id`, `participant_id`, target session/part/group/part-number, and
  requester/source-behavior fields) while excluding pairing tokens; explicit
  package, target-session, or split-part identity drift is rejected before state
  changes. Runner command diary rows flatten the same non-secret target
  identity beside the raw received command/ack samples, and strict validation
  compares those row fields against command payloads, ack payloads, embedded
  completion diary rows, and matching `operator_command` events when present.
  The
  strict Controller/PC-admin outbox validator now parses stored command and ack
  samples, rejects row-versus-command-payload target identity drift, and
  requires that same non-secret ack payload identity while rejecting pairing-token
  echoes; the phone-run command diary validator applies the same token-exclusion
  rule to native ack samples. The command-admin reconciler compares those echoed
  target payload fields
  between sender outbox and receiver command diary, requires the serialized
  command sample payload to be token-bearing, and rejects ack payload
  pairing-token echoes even when both sides match; the PC monitor/XDF reconciler
  now checks the same non-secret command/ack target identity fields when both
  command-signal and acknowledgement streams are captured, and it rejects
  observed ack payloads that echo `token` or `companion_token`. Rejected Runner
  command acks now use `pps-android-phone-command-rejection.v1` payloads with
  receiver identity, requested target identity, rejection reason,
  `rejected_before_handler`, and supported commands; strict phone-run,
  Controller/PC-admin, and monitor validation reject incomplete rejected-ack
  payloads. Handler-side runtime rejections now use
  `pps-android-phone-command-handler-rejection.v1` payloads with
  `rejected_before_handler=false`, handler completion/payload evidence,
  receiver/requested identity, and supported commands, so parsed commands that
  fail local phone runtime conditions are distinguishable from token/session
  gate failures. Malformed command samples that fail before `PPSCommandSignalsV1`
  parsing now use `pps-android-phone-command-sample-rejection.v1` payloads with
  stable synthetic ids when needed, receiver identity, raw non-secret sample
  diagnostics, and a redacted raw-sample preview; strict phone-run validation
  treats that as the only accepted `invalid_lsl_command` native row path.
  Controller runtime
  status now also includes
  `pps-android-lsl-stream-descriptions.v1` descriptions for the controller
  command-signal outlet and command-ack inlet, and strict controller validation
  checks those roles, source identity/patterns, privacy, and PC-compatible
  channel order.
- Android phone-owned response/top-up review lives in
  `PhoneResponseReview.kt`. It applies the shared 100-1300 ms post-tactile
  response policy to standard phone blocks, plans missed-trial rescue top-ups
  from reusable building-block assets, and after a played phone top-up appends
  `topup_rescue` ledger rows while marking source misses as rescued or still
  unresolved. This is phone-runtime response evidence, not physical
  audio/vibration timing evidence.
- Provisional Woojer tactile-drive latency compensation: `tactile_latency.py`, consumed by `session_runner.py` during participant/top-up block WAV preparation.
- Shared runner/dashboard profile memory and output-diary bridge: `runner_diary.py` now owns runner settings and diary helpers; future shared profile-catalogue code should live in a common Python seam consumed by both `dashboard_app.py` and `focus_app.py`, not separately in browser JS or runner UI code.
- Event, timing, and output evidence contracts: `timing_events.py`, `session_events.py`, `output_evidence.py`, `topup.py`.
- Optional LSL sender/receiver command acknowledgement helpers: `lsl_command_ack.py`, with real `pylsl` round-trip validation in `validation_protocols/scripts/run_lsl_command_ack_roundtrip.py`. PC-to-Android phone-owned administration lives in `android_lsl_admin.py` and the `pps-android-lsl-command` console entry point; it sends token-gated `PPSCommandSignalsV1` samples with `target_session_id` plus optional split target part/session-group identity in the payload, optionally requires `PPSCommandAcksV1`, supports `operator_note` with a first-class `--note` payload, validates received acks before reporting live success, marks stale/session-drifted/token-echoing, unrecognized-status, or missing-identity acks as `invalid_ack` while preserving their sample, and writes `pc_android_lsl_command_outbox.jsonl` plus `pc_android_lsl_admin_status.json` with non-secret target identity flattened into row fields. PC-admin rows with received acks now mirror Android Controller `ack_valid`, `ack_validation_status`, and `ack_validation_reason` metadata, so `ack_rejected` handler-side runtime refusals remain valid ack evidence while bad ack samples remain auditable invalid acknowledgements. Android Controller mode now applies the same same-command ack validation before showing a clean sent state, preserving invalid ack samples in `phone_controller_command_outbox.jsonl` with `ack_valid=false` and concrete validation reasons. Android Controller `stream_descriptions` also advertise the same privacy-safe package/participant/target part identity at the description root, and strict validation compares it with `phone_controller_runtime_status.json`. Focus Mode's Send-to-Phone LSL bridge forwards `target_part_session_id` and `target_session_group_id` from the active mobile package as explicit admin arguments and payload metadata. PC-admin status now includes `pps-android-lsl-stream-descriptions.v1` for the PC command-signal outlet and Android command-ack inlet, deriving the exact command source ID from the written outbox row when available. PC-side Android LSL monitoring lives in `android_lsl_monitor.py` and the `pps-android-lsl-monitor` console entry point; it resolves Android `PPSMarkersV2`, `PPSTriggerCodes`, `PPSCommandSignalsV1`, and `PPSCommandAcksV1` streams, writes `pc_android_lsl_monitor_events.jsonl` plus report/status JSON with observer-side `stream_descriptions`, extracts command-signal ids/names, ack ids/statuses, payload JSON, and non-secret target identity from observed command/ack payloads, reports command ids missing matching observed acks and ack ids without observed command signals, supports `--require-commands`, and is the lightweight non-XDF observation seam for PC/phone-to-phone rehearsals.
- Android native LSL integration guidance is tracked in
  `docs/ANDROID_LSL_INTEGRATION.md`. The phone-run artifact validator lives at
  `validation_protocols/scripts/validate_android_lsl_runtime_artifact.py` and
  checks `lsl_runtime_status.json`, Android LSL stream descriptions including
  generic stream/source identifiers with no participant/demographic/haptic
  labels, embedded completion status,
  strict native marker-push completeness from completion `summary`
  (`native_lsl_pushed_count == lsl_marker_mirror_count` and
  `native_lsl_failed_count == 0`, plus matching per-stream rich-marker and
  numeric-trigger pushed/failed counters) when marker evidence is present,
  strict native command summary counts against `native_lsl` command diary rows
  when `--expect-command-acks` is set,
  phone-run `phone_run_catalog_entry.json` when present or when
  `--expect-run-catalog` is set, app-private `phone_run_catalog/index.json`,
  participant `runs.jsonl`, and `latest_run.json` when
  `--expect-run-catalog-index` is set, including event/marker/command-diary
  counts plus native marker-push and command received/ack/rejected counts
  against completion `summary` and privacy-safe haptic calibration summaries
  against `haptic_capability.json`/completion haptic metadata, phone-run
  `events.csv` event-diary
  rows against embedded completion/latest-events when `--expect-event-diary`
  is set, strict command diary rows against matching `operator_command` event
  mirrors for local phone UI/runtime and native LSL commands, completion
  `summary` local diary counts against event, marker, and command diary artifacts when present, phone-run `artifact_file_inventory.json` file/size/SHA-256 evidence
  against actual folder or ZIP contents when `--expect-artifact-inventory` is
  set or the completion advertises the sidecar, lightweight scheduled-block materialization
  events/manifests/WAV hashes plus materialized trial UID/building-block
  sequence order against `run_package_manifest.json` when
  `--expect-lightweight-materializations` is set, package `asset_strategy`
  consistency across phone-run sidecars,
  phone-run response/top-up reconstruction evidence from
  `phone_response_ledger.csv`, `phone_topup_plan.json`,
  `phone_topup_materialization.json`, and `phone_topup_block.wav` when
  `--expect-phone-topup-evidence` is set or lightweight materializations are
  strict, with sidecar-vs-embedded completion comparisons, plan-vs-materialized
  rescue trial signature checks, contiguous top-up trial timing checks, and WAV hash checks,
  phone-run AudioTrack timing evidence from `block_start`,
  `audio_playback_start`, and `vibration_cue` events when
  `--expect-audiotrack-timing-evidence` is set, including playback-head origin,
  track state, block PCM byte-size/encoding geometry, buffer-size, scheduler fields,
  scheduled-frame/block-time/frame-count coherence, delivery elapsed-time lower
  bounds against playback-head progress, and coherent cue-jitter metadata,
  phone-run `reconstruction_contract.json` Segment 0-6 hierarchy and
  schedule/count consistency,
  Controller-mode `phone_controller_runtime_status.json` /
  `phone_controller_command_outbox.jsonl` including controller LSL stream
  descriptions, PC-admin stream descriptions, PC-monitor stream descriptions
  with private participant/demographic/haptic identifier rejection across stream
  names/source ids/source-id patterns,
  `pc_android_lsl_admin_status.json` /
  `pc_android_lsl_command_outbox.jsonl`, command/ack schema/channel order,
  Controller/PC-admin row-payload versus command-sample-payload consistency,
  Controller/PC-admin ack payload command/target identity plus pairing-token
  exclusion, nonblank `operator_note` note payloads,
  PC-monitor observed command-signal payload token/note evidence and
  payload_json versus sample-payload consistency plus observed command/ack id
  pairing under `--expect-command-acks`,
  phone-run `command_diary.jsonl` / embedded command diary native ack rows and
  sidecar-vs-embedded command field consistency, required receiver-side
  `PPSCommandSignalsV1` `command_sample` evidence in strict ack mode, native
  ack payload versus command diary payload consistency with pairing-token
  exclusion, strict version/field checks for malformed-sample
  `pps-android-phone-command-sample-rejection.v1`, handler-rejected
  `pps-android-phone-command-handler-rejection.v1`, `request_snapshot`
  `pps-android-phone-runtime-command-state.v1`, and rejected-command
  `pps-android-phone-command-rejection.v1` ack state reports, and command
  diary payload versus
  `operator_command` event payload consistency,
  phone-run `lsl_marker_mirror.csv` / embedded marker mirror reconstruction,
  phone-run `trigger_codes.csv` expected local `PPSTriggerCodes` sequence when
  `--expect-trigger-code-mirror` is set,
  phone-owned `phone_owned_data_export.json` plus app-private or PC-upload
  mirrored `phone_owned_exports/1.Data_min` and `2.Data_max` snapshots when
  `--expect-phone-owned-data-export` is set; strict Data Max validation now
  requires the mirrored run folder to include the reconstruction spine files
  (`lsl_runtime_status.json`, `events.csv`, `run_package_manifest.json`,
  `reconstruction_contract.json`, marker/trigger mirrors, command diary,
  response/top-up sidecars, phone-run catalog entry, phone-owned export
  manifest, participant metadata, haptic capability, artifact inventory
  JSON/CSV, and completion/latest-events evidence), and rehashes the copied
  Data Max inventory against the mirrored files for the current run id,
  phone-run `participant_metadata.json` and `haptic_capability.json` sidecars
  plus Android haptic calibration threshold/status/amplitude-response
  consistency, including no-vibrator, binary-detection, and amplitude-control
  status semantics,
  phone-run `artifact_file_inventory.json` / `.csv` sidecar advertisement from
  completion/latest-events JSON and strict inventory sidecar presence,
  PC-monitor `pc_android_lsl_monitor_report.json` /
  `pc_android_lsl_monitor_events.jsonl`, token requirement, privacy boundary,
  strict native-transport/send/observed-stream evidence, and optional
  controller/PC-admin/monitor ack receipt. The expected-vs-observed Android
  LSL rehearsal check lives in
  `reconcile_android_lsl_monitor_with_phone_run.py`; it compares a phone-run
  `lsl_marker_mirror.csv` or ZIP against PC-observed monitor rows and numeric
  trigger-code sequence, but remains network LSL evidence rather than physical
  timing proof.
- Android emulator validation policy: the AVD viewport is the fixed phone-screen truth. Do not use window resizing, widening, or repeated placement scripts to make the Android companion UI pass; flicker, hidden controls, scrolling burden, and clipped buttons are product findings. `windows/Set_Companion_Emulation_Layout.ps1` now places only the PC runner window, deliberately leaves Android emulator windows untouched, and treats old `-KeepForSeconds` calls as non-polling compatibility input. `focus_app.py` still honors `PPS_FOCUS_VALIDATION_DISPLAY`, `PPS_FOCUS_VALIDATION_RUNNER_WIDTH`, and `PPS_FOCUS_VALIDATION_WINDOW_RECT` for the PC runner window, and `PPS_FOCUS_VALIDATION_PARTICIPANT_RESPONSES_ONLY=1` keeps app-driven companion command tests from being preempted by validation auto-start/continue helpers.
- Android emulator stress reporting lives in
  `validation_protocols/scripts/run_android_companion_emulator_ui_stress.py`.
  It now reports optional native Android LSL source capability and local AAR
  presence separately from live network proof, plus an
  `android_emulator_fixed_viewport_policy` result proving the harness did not
  use AVD size/density/rotation or desktop window-placement commands, so default
  builds should be read as source-supported/local-mirror-only rather than as
  failed live LSL runs. The policy and source-capability assessments are added
  before ADB boot/UI work, and early exceptions are written as
  `android_emulator_ui_stress_exception` results instead of losing the report.
- Companion discovery contract: `runner_companion.py` owns the
  `pps-runner-companion-discovery.v1` payload builder/validator and UDP
  advertiser. Discovery remains token-free and local-only: same-LAN or local
  phone hotspot scope, multicast `239.255.77.83:48767`, limited broadcast
  `255.255.255.255:48767`, best-effort private/link-local IPv4 directed
  broadcasts such as typical `/24` phone-hotspot targets, TTL 1, modes
  `pc_runner`/`phone_export`, transports `lan`/`phone_hotspot`/`wifi_direct`,
  and no pairing-token, participant/demographic, participant-identifier, or LSL
  stream/source-name fields anywhere in the packet. The payload advertises
  `discovery.broadcast_targets = ["255.255.255.255",
  "interface_ipv4_directed_broadcasts"]`; Android `CompanionDiscovery.kt`
  mirrors these checks before constructing a pairing URI from a user-supplied
  QR/manual token. `RunnerCompanionDiscoveryAdvertiser.status()` now separates
  the packet contract (`packet_broadcast_targets`) from concrete runtime UDP
  destinations (`concrete_broadcast_targets` / `directed_broadcast_targets`) so
  hotspot rehearsal artifacts can show both levels.
- Published-study preload recreation gate: `profile_recreation.py`, `assets/preloads/`, `study_templates/`.
- Core paper-audit read API: `peripersonal_space_toolkit.paper_audit`.
- Behavioral PPS replication checks for collected/public derived CSVs:
  `mobile_pps_replication.py`, with the folder-capable validation helper in
  `validation_protocols/scripts/analyze_mobile_pps_replication.py`.
- Paper-audit acquisition/refresh tools: `tools/paper_metadata_parser/`.
- Tracked paper-audit memory and ledgers: `For-AI/audiotactile-paper-metadata-audit/`.
- Validation protocols and lab evidence scripts: `validation_protocols/`.

## Refactor Direction

Keep public imports stable while extracting:

- `dashboard_app.py` remains the compatibility facade for `create_app`, `DashboardController`, and `pps-dashboard`.
- Segment manifest validation should move from the backend monolith into manifest/segment modules.
- Runtime launch/session package work should move toward `runtime/` modules.
- Event and marker schemas should move toward `events/` modules.
- Browser JS should split only after backend/API seams are stable, and local packaged plus hosted/static assets must stay synchronized.

## Literature/Paper Audit Rule

The paper audit is a core pipeline, not a side report. It catalogs the needs, profiles, parameters, missing publication details, and toolkit-structure gaps across audio-tactile PPS studies so future implementations can be built from a growing knowledge base. Keep tracked audit files source-pointer-only; keep PDFs, supplements, extracted full text, screenshots, and local bundles ignored.
