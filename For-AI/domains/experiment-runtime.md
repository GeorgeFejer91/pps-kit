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

`pps-runner-audio-cpal` can bind the existing verified immutable output plan to
an exact reserved stream. Silent warm-up returns one native command/event port;
no IPC caller can reconstruct it. `native_playback.rs` hands that sole port to
the existing execution actor, sharing its cached immutable plan and native
metadata receipt. Completion rechecks the package/run/cache and healthy journal;
stale or abandoned handoffs drop and abort the callback. The actor drains bounded
callback records into the existing event ledger/journal, preserving original
schedule payloads and retaining callback observation/prediction clocks separately.
Ledger timestamps reflect recording order; callback observation is not physical
onset. Preparation remains silent. Start, response collection, durable result
publication, and completion must be implemented together before enabling native
execution. No second scheduler or UI-owned playback authority is permitted. Device retirement retains callback storage off the render
path. Raw CPAL playback timestamps are predictions in their own clock domain,
not measured physical onset. The Tauri package is still non-executable until
the complete experiment adapter adopts this seam; preparation does not promote
readiness or qualification.

`event_journal.rs` is the native file owner for the existing authority event
schema. Explicit first-block audio preflight creates one `native_events_*.partial.jsonl`
in the verified session directory; choosing/inspecting a package remains read-only.
Only native receipts choose that directory. The journal has eight bounded queue
slots, 128 records/256 KiB per batch, and a 32 MiB total budget. Admission precedes
authority commit; the worker acknowledges a prefix only after syncing it. Write
failure or backpressure prevents further ordinary transitions and neutralizes
output; safety still proceeds. Package replacement closes the old writer before
another can attach. Keep files partial until real media, responses, dataset
publication, and completion are implemented. An event journal is not a response
CSV or evidence of physical timing. The shared reducer leaves verified
package Stop interrupted/partial and rejects `RunCompleteDemo` for that package.
Only a future native result publication receipt may authorize real completion.
