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
them. `pps-experiment-media` binds each inventoried PCM16 trial WAV to its exact
decoded bytes through the existing native decoder and checks the exported audio
hint after decoding. Its standard-route assembler stages one bounded PCM16
block in approved trial order, with ITI silence and the provisional Woojer
drive advance. It synthesizes the Python-compatible sawtooth, sine, square,
and biphasic square pulse-train tactile waveforms,
including trial extension and prepared CSV metadata. Python-compatible speaker
switching supports gains, mixdown, source selection, and tactile preservation.
The producer now chooses the maximum trial output width for the block, with a
three-channel minimum and an 18-channel bound. Source PCM remains 2/3-channel;
switching and tactile synthesis can place samples on higher output channels.
The native decoder and CPAL adapter accept exact 4–18-channel PCM16 blocks and
preserve each source channel at the same physical output index. This direct
route requires unity gains; study-specific channel roles, calibration, and
physical verification remain open. Windows builds now enumerate CPAL's ASIO
host before WASAPI and admit F32 or I32 output configurations; I32 callbacks
convert the bounded F32 render buffer without allocation. The 256-entry bounded
inventory preserves 44.1 kHz/3-channel ASIO configurations behind lower rates
even when a device exposes 18 outputs. CI compilation and a synthetic inventory
test do not establish the Komplete Audio 6 three-channel route or measured timing.
The block has a
bounded size and is published without overwriting an existing file. The same crate now
materializes a standard-route `pps-run-session.v1` CSV/manifest package for one
approved participant's block order. For an approved two-part pre/post plan it
publishes separate verified part packages under one `pps-run-session-group.v1`
manifest and returns Part 1 for native adoption. Part 2 remains an explicit
prepared-manifest selection. The source candidate verifies the adjacent Part 1
package and its sealed native result before Part 2 adoption, including after
a process restart. Installed transition and grouped results are not qualified.
It rechecks the JSON/source
inventory, verifies the staged and published package with the existing V1
verifier, compiles every block schedule, and publishes the canonical manifest
last without overwriting an existing package. In-process publication errors
roll back the files this attempt linked into its new destination. A process
crash or failed filesystem cleanup can still leave an orphan requiring manual
inspection. The Runner main window selects the
profile and output folder through native dialogs, calls this producer on a
blocking worker, and adopts its existing V1 verification receipt. No path enters
WebView or phone IPC. Before decoding or creating each block WAV, the native
assembler checks its bounded output estimate against available space on the
selected filesystem with the Python preflight's threefold reserve and 8 MiB
margin. A concurrent disk change can still cause an ordinary write failure;
the pending WAV is removed and the final manifest is not published. This
candidate still needs advanced media transforms, installed execution, and
physical timing qualification. Path-bearing receipts stay native-only.

Designer generation jobs bind to the captured design signature. Ingredient media
stays in staging until the source and cooperative cancellation checks admit
publication. Segment jobs reuse one completion handler and the existing rebuild
rollback owner. Cancellation after publication begins is reported as completion,
not as an unpublished result. Use the existing renderer's `auto` selection and
retain its explicit native/reference provenance.
The native 3DTI child receives a plain Win32 working directory: its SOFA/HDF5
reader cannot open a `\\?\` extended path. Keep the resource-relative HRTF
reference in the render config and verify the installed Shared copy.

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
last. Sequential native blocks keep one run journal; each block must drain and
close its response windows before the next is prepared and locally armed. Only
the final block may request publication, using the compiled package's total
trial count and a matching native package/run/count/sequence receipt.
Missing/interrupted trials cannot complete. Unsupported hard-link
filesystems fail closed; partial/pending/orphan files remain. Power loss,
directory persistence, device drain and physical timing need separate evidence.
Use `validation/scripts/validate_native_results.py` under `For-AI/engineering/`
for read-only file/hash/prefix/V1-projection checks; synthetic files are not
participant acquisition. Its `--group-manifest` mode derives two-part native
completion from the adjacent package identities and both sealed
result manifests. The prepared Rust group manifest's `completed: false` fields
are not native run evidence; this audit does not rewrite them. It requires one
unambiguous published result per part and still makes no physical timing,
recording-device, or participant-use claim.

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

The current native source candidate enables fenced sequential blocks after a
verified package, compiled schedules, the current block's PCM and a matching
silent output reservation. The native owner chooses the next block; the WebView
cannot supply its ordinal. A drained non-final block disarms and releases its
port while retaining the run journal. Each next block needs a new local route
check and acknowledgement. Start/Resume still wait for durable intent and
callback confirmation. This remains unqualified for participant use. Earlier
exact-SHA CI and an isolated Windows NSIS install verified package adoption,
schedule compilation and PCM preparation only. The synthetic three-channel
block had no matching local output configuration, so no installed run, physical
playback, recording or result publication was tested. Complete installed
multi-block operation, calibration and physical qualification remain gates.
Wire completion remains denied for real packages; Stop preserves partial results.
