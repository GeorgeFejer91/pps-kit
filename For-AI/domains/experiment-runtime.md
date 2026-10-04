# Experiment runtime

Own schemas, generation, schedules, native execution, responses, calibration,
reconstruction, and authoritative experiment state. Use
[module_map.md](../module_map.md) to find code and trace its callers.

## Read for the task

- Design/manifests: matching [segment contract](../segment_registry_contract.md).
- Audio generation: [looming standard](../looming_stimulus_generation_standard.md).
- Gain/SPL or tactile calibration: [loudness](../loudness_calibration.md),
  actual calibration modules, and matching validation protocols.
- Architecture/handoff: [architecture](../engineering/architecture/ARCHITECTURE.md)
  and the affected public specs under `docs/`.
- Candidate native authority/output/transport: owning source/tests and targeted
  [detailed checkpoint notes](../archive/module_map.md).
- Changed methods/claims: [scientific evidence](scientific-evidence.md).

Use **Ponytail** for implementation and **tauri-rust-developer** for existing
Rust/Tauri code. Add **tauri-browser-remote-control** for typed actions,
authentication, revisions, revocation, or transport. Read timing/performance
references when those requirements are affected. No generic input forwarding
or competing UI-owned experiment state.

V1 Python/PySide is the qualified compatibility path. V2 has native output work
in progress; inspect code instead of treating old notes as proof of support.
Preserve generation fencing, bounded queues, native-only receipts, calibration,
and path-free remote projections. Physical timing/behavior cannot be proved
by compilation, mocks, browser clocks, or transport RTT.

Verify the changed seam and meaningful error/denial cases. Preserve deterministic
output/provenance unless the schema change is intentional. Reuse Python/Rust
differential fixtures during migration. Run owning Python, frontend, or Rust
checks. [WORKFLOW.md](../WORKFLOW.md) separates source, installed, and physical
evidence: deferred packaging cannot support an installed-behavior claim.
Quest/Android is conditional, not a default PPS gate.

`experiment_profile.py` owns the local `pps-experiment-profile.v1` JSON handoff.
It freezes approved Segment 5/6 rows and hashes local ingredients; it must not
choose a second trial order. Designer export checks the current review revision
and existing lineage gates. The compatibility Runner accepts
`--experiment-profile <json> --participant-id <id>` and uses the existing session
assembler after verifying the inventory. Remote projections never carry paths.
`pps-session-package::experiment_profile` now verifies that same JSON's bounded
local ingredient inventory in pure Rust and retains a native-only path/hash
receipt. `pps-session-package::experiment_plan` then selects one participant's
existing Segment 6 block order and Segment 5 trial audio references. It
rechecks the profile, run setup, source manifest and consumed CSV bytes against
the exported inventory and frozen rows; it does not schedule, bake media or
authorize execution. Recheck audio bytes when the native assembler consumes
them. Neither path-bearing receipt may become a WebView or phone projection.

Designer generation jobs bind to the captured design signature. Ingredient media
stays in staging until the source and cooperative cancellation checks admit
publication. Segment jobs reuse one completion handler and the existing rebuild
rollback owner. Cancellation after publication begins is reported as completion,
not as an unpublished result. Use the existing renderer's `auto` selection and
retain its explicit native/reference provenance.

`resource_limits.py` owns bounded assembly CSV reads, plan-entry limits, and
conservative PCM16/scratch/float32 estimates. Generation and block preparation
check storage before decoding or publishing media. Oversized plans are rejected,
never truncated. Keep analytical participant/event readers separate from these
assembly-input limits. UI readiness checks inspect one participant's block plan
rather than expanding every participant's schedule.

Remote participant setup is target-local; public snapshots omit identity and
private paths. Rust/browser permissions share
`pps-contracts/fixtures/remote-actions.v1.json`. The same side-effect owner must
check scope, epoch, lease, payload, and retired command IDs before execution.
Native-backed BRSP delegates retry decisions to Rust; in-memory history never
replaces a durable result journal. Controllers share one fresh-state gate and
one reliable command slot. Unknown acknowledgements never trigger automatic
replay. Phone suspension disarms exploratory outputs; resume authenticates and
fetches state before controls become available. Native authority survives a
hidden desktop window. Observer scope is read-only; remembered phone trust is
unselected. Current bounds and evidence belong in the owning tests and the
[implementation record](../engineering/validation/docs/implementation-status-2026-09-27.md).

Native execution has one actor, one existing callback scheduler, and one file
worker. `pps-runner-audio-cpal` binds verified immutable PCM to an exact reserved
stream; silent warm-up returns one native port. `native_playback.rs` retains the
shared plan, native metadata, and decoded duration. Stale or abandoned handoffs
drop and abort the port. Local and phone commands share `finish_dispatch` and
`apply_native_action`: Start/Resume wait for durable intent, callback records
confirm application, Pause does not wait for file durability, and Pause cancels
pending activation as an interrupted attempt. Stop/Abort/disarm retire the port;
revocation also cancels pending activation. Controls have a bounded deadline.
No wire caller can reconstruct the port or qualify physical onset. Callback
observations, driver predictions, and source submission remain unqualified.

`event_journal.rs` owns paired partial events and 18-column Data_min CSV in the
verified session directory. Selection/inspection remain read-only. Package and
run generations fence journal installation; ended attempts close their writer
before another attaches. Preserve the existing eight-slot queue, batch and total
byte bounds. Admission precedes authority commit; the worker acknowledges a
prefix after syncing both files. Failure/backpressure neutralizes output while
safety still proceeds. Finalization freezes a prefix, syncs/closes both files,
exclusively publishes final names, checks hashes, and publishes the manifest
last. Only a matching native package/run/count/sequence receipt can complete a
whole single-block package after response windows and the final software estimate
close. Missing/interrupted trials cannot complete. Unsupported hard-link
filesystems fail closed; partial/pending/orphan files remain. Power loss,
directory persistence, device drain and physical timing need separate evidence.
Use `validation/scripts/validate_native_results.py` under `For-AI/engineering/`
for read-only file/hash/prefix/V1-projection checks; synthetic files are not
participant acquisition.

`pps-runner-execution::response` is the shared scoring/CSV owner; Python remains
the oracle. `trial_capture.rs` consumes callback boundaries without another
scheduler. Local `runner_record_response` accepts only bounded choice/normalized
pointer content; native ingress supplies the clock/ID/block. Queued input stays
pending through actor processing even if its UI wait is abandoned. Input loss
fails closed; pauses through trials retain interrupted evidence. Filler/debug
rows stay in rich events without advancing Data_min indices. The participant
button uses this local IPC, never a phone command or replay. Native capture
readiness follows callback confirmation. Main-window-only state broadcasts
update the UI; older revisions and absent readiness cannot enable capture.
The main window may listen/unlisten but cannot emit authority snapshots.

The local output view uses the existing main-window-only native preflight
commands. It lists configurations matching prepared channels/sample rate,
requires an explicit choice, and preserves decimal generation fences. Silent
preparation never enables Start. Disable remains available during a pending
operation; stale replies cannot restore its UI. Suspension clears the view's
inventory; resume reads fresh native state without replay. The Rust owner keeps
the device/port authority. Release/disable clears the displayed media summary
as the Rust owner retires its cache; audio preparation is required again.
Desktop notifications remain in their owning panel
and use the shared bounded-text helper.

The current native source candidate enables a fenced, explicitly acknowledged
single-block activation only after verified package, compiled schedule, prepared
PCM and a matching silent output reservation. Start/Resume still wait for durable
intent and callback confirmation. It is unqualified and requires a checked local
route and levels; preparation alone does not enable execution. Exact-SHA CI and
an isolated Windows NSIS install verified package adoption, schedule compilation
and PCM preparation. The synthetic three-channel block had no matching local
output configuration, so no installed run, physical playback, recording or result
publication was tested. Whole profiles/multiple blocks, calibration and physical
qualification remain gates. Wire completion remains denied for real packages;
Stop preserves partial results.
