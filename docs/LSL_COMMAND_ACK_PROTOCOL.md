# LSL Command/Acknowledgement Protocol

This project uses Lab Streaming Layer (LSL) primarily as a timestamped evidence and recording bus. The Focus Mode runner remains the timing and command authority; audio playback, tactile drive, response logging, LabRecorder, ledgers, and analysis are still runner-owned.

For lab tools that need a sender/receiver handshake over LSL, use the optional command/ack protocol in `peripersonal_space_toolkit.lsl_command_ack`.

## Stream Pair

Use two long-lived irregular string streams:

- `PPSCommandSignalsV1`: sender to receiver.
- `PPSCommandAcksV1`: receiver to sender.

Each command carries a unique `command_id`. The receiver sends one acknowledgement with the same `command_id` after the local application handler has returned. That means an `applied` ack confirms that the receiver changed or accepted its own state; it does not prove that a physical output, EEG amplifier, or LabRecorder file has captured anything. Hardware and XDF proof still comes from the existing loopback, local marker mirror, and LabRecorder reconciliation protocols.

## Efficient Pattern

1. Create both outlets once and keep them alive for the session.
2. Resolve both inlets before the first command.
3. Use `chunk_size=0` and one sample per command/ack.
4. Push each command/ack with `pushthrough=True`.
5. Poll the command inlet frequently on a background thread or event loop.
6. Apply the receiver action locally.
7. Immediately push the ack sample with `status=applied` or `status=rejected`.
8. The sender waits for the matching `command_id`, not just the next ack.

This follows the LSL API model: outlets make streams discoverable and push samples with `local_clock()` timestamps; inlets subscribe to streams and pull queued samples. LSL documentation notes that `pushthrough` avoids buffering with later samples, and that local-machine latency is typically under 0.1 ms when samples are not allowed to queue.

## Fields

`PPSCommandSignalsV1` channels:

- `schema`
- `command_id`
- `session_id`
- `sender_id`
- `command`
- `issued_lsl_time`
- `payload_json`

`PPSCommandAcksV1` channels:

- `schema`
- `command_id`
- `session_id`
- `receiver_id`
- `status`
- `reason`
- `received_lsl_time`
- `applied_lsl_time`
- `ack_lsl_time`
- `payload_json`

## Validation

Run a local round-trip validation:

```powershell
.\.venv\Scripts\python.exe validation_protocols\scripts\run_lsl_command_ack_roundtrip.py --count 10
```

The script writes `lsl_command_ack_roundtrip_report.json` and `.md` under `artifacts/validation_runs/`. It verifies that every command id receives an `applied` ack and reports:

- sender-observed round-trip time
- receiver receive delay
- receiver handler duration
- ack emission delay after apply

## Companion Boundary

The Android companion app still uses the token-gated local HTTP/WebSocket
companion service for ordinary PC-runner control. That remains intentional:
LSL does not provide request authentication, privacy, or command authorization
by itself.

Phone-owned packages declare an Android LSL contract in
`pps-mobile-run-package.v2`. In default public builds, the Android runtime
writes a PPSMarkersV2-shaped local marker mirror, command diary, controller
outbox, and runtime status artifacts. When the ignored local
`android/runner-companion/app/libs/liblsl-Android.aar` is supplied for a
validation build, the same app can open native `PPSMarkersV2` /
`PPSTriggerCodes` outlets, receive token-gated `PPSCommandSignalsV1` samples,
emit `PPSCommandAcksV1`, and let Controller mode publish command-button samples
over native LSL while still keeping the local outbox.

The pairing token stays in the command payload (`token` or `companion_token`),
not in stream names. Demographics and tactile thresholds stay in metadata and
marker payload artifacts by default rather than discoverable stream names.
Use `validation_protocols/scripts/validate_android_lsl_runtime_artifact.py` on
phone-run folders, exported ZIPs, `lsl_runtime_status.json`, Controller-mode
`phone_controller_runtime_status.json`, or
`phone_controller_command_outbox.jsonl`, or PC-admin
`pc_android_lsl_admin_status.json` /
`pc_android_lsl_command_outbox.jsonl`. Add `--expect-native-transport` for
native marker/command/controller/PC-admin transport checks and
`--expect-command-acks` when a controller-runner or PC-runner test should prove
matching acknowledgements. Android runner acknowledgements must include
`receiver_role="runner"` in the ack payload; the live Controller and PC-admin
senders, the Android artifact validator, and the command-admin/monitor
reconcilers reject missing or non-runner receiver roles.

The PC side can also administer a phone-owned Android runner directly over the
same command stream with the `pps-android-lsl-command` helper. It writes
`pc_android_lsl_command_outbox.jsonl` and
`pc_android_lsl_admin_status.json` while sending `PPSCommandSignalsV1` samples
and optionally requiring matching `PPSCommandAcksV1` samples. The native
runner's `Send To Phone` dialog exposes the same sender after package
preparation, defaulting the target to the prepared package part-session id:

```powershell
pps-android-lsl-command start_experiment --session-id <part_session_id> --token <pairing-token> --package-id <package_id> --require-ack
pps-android-lsl-command pause --session-id <part_session_id> --token <pairing-token> --require-ack
pps-android-lsl-command resume --session-id <part_session_id> --token <pairing-token> --require-ack
```

Validate the resulting PC-admin outbox/status pair with the same Android LSL
artifact validator when auditing a rehearsal.

Use `pps-android-lsl-monitor` when the question is whether a separate PC can
observe the Android runner/controller streams during a rehearsal. It resolves
`PPSMarkersV2`, `PPSTriggerCodes`, and `PPSCommandAcksV1`, writes
`pc_android_lsl_monitor_events.jsonl` plus
`pc_android_lsl_monitor_report.json`, and can be validated with the Android LSL
artifact validator:

```powershell
pps-android-lsl-monitor --duration-s 30 --require-markers --require-triggers --require-acks
python validation_protocols/scripts/validate_android_lsl_runtime_artifact.py artifacts/android_lsl_monitor --expect-native-transport --expect-command-acks
```

For rehearsals with an exported phone-run folder or ZIP, follow the monitor
validation with:

```powershell
python validation_protocols/scripts/reconcile_android_lsl_monitor_with_phone_run.py <phone-run-dir-or-zip> artifacts/android_lsl_monitor --expect-numeric-triggers --expect-command-acks
```

That reconciliation compares the phone-local `lsl_marker_mirror.csv` against
the PC-observed rich marker rows and numeric trigger sequence.

When the claim is specifically that a Controller phone or the PC admin helper
sent commands that the Runner phone applied, reconcile the sender outbox
directly against the Runner phone artifact:

```powershell
python validation_protocols/scripts/reconcile_android_command_admin_with_phone_run.py <phone_controller_or_pc_admin_outbox_or_dir> <phone-run-dir-or-zip> --expect-native-sends --expect-command-acks
```

This compares native-sent command ids, target sessions, sender ids, command
names, package identity, and exact `PPSCommandAcksV1` samples between the
sender outbox and the phone-run `command_diary.jsonl`.

## References

- [Lab Streaming Layer overview](https://labstreaminglayer.org/)
- [liblsl stream outlets](https://labstreaminglayer.readthedocs.io/projects/liblsl/ref/outlet.html)
- [liblsl stream inlets](https://labstreaminglayer.readthedocs.io/projects/liblsl/ref/inlet.html)
- [LSL FAQ latency note](https://labstreaminglayer.readthedocs.io/info/faqs.html#latency)
