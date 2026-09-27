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

Remote participant setup is target-local. Shared action permissions are checked
against `pps-contracts/fixtures/remote-actions.v1.json` in Rust and browser tests;
public native snapshots contain only remotely eligible actions. The reducer keeps
256 outcomes and up to 4096 retired command IDs for one authority generation.
Evicted IDs return `command_outcome_expired`; a full history denies new mutations
until deliberate authority rotation while retaining reads and safe stop/disarm.
Current epoch, scope, and lease checks also apply to cached outcomes. This is an
in-memory guarantee; durable execution must retain its own result/journal evidence.
