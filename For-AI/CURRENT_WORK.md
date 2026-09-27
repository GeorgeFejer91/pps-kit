# Current work

Updated: 2026-09-27. Replace at task/stage transitions; do not append command logs.

- **Approved goal:** implement all 17 [audit items](engineering/validation/docs/unification-and-critical-audit-2026-09-27.md).
  Use Ponytail and existing owners. Planner creates/previews looming stimuli
  and exports JSON ingredients/file/assembly profiles; Runner consumes them,
  executes experiments, and records the specified data. Do not ask again for
  approval of the scoped proposals.
- **Domain:** [experiment runtime](domains/experiment-runtime.md), with design/UI
  and release handoffs. Reuse 3DTI, the 3D viewer, Segment 0–6, existing schemas,
  bounded jobs, native execution ownership, and Python/Rust oracle fixtures.
- **Source stage:** JSON export/compatibility assembly, bounded generation and
  publication, shared Pretext, dependency patches, local setup permissions,
  retry fences, and phone suspension/recovery are implemented. The main phone
  flow is Pair → fresh state → permitted action; exploratory phone outputs stay
  separate. The native media bridge reuses the verified renderer and returns
  one command/event port after silent warm-up; no second scheduler was added.
  Explicit audio preflight now installs a bounded native event journal using
  the existing authority schema. Writer/admission failures interrupt and disarm
  active state; partial files are retained and cannot certify a completed run.
  The review branch also binds cached media through that authority: immutable
  PCM is shared, stale handoffs abort, and callback metadata enters the same
  journal. Preparation remains silent, non-executable, and unqualified.
  Stop interrupts a verified package and the demo completion command rejects
  it; native results must authorize real completion.
- **Evidence:** use the single [implementation record](engineering/validation/docs/implementation-status-2026-09-27.md).
  Source, CI packages, installed behavior, physical timing, participant results,
  and published replication are distinct gates. The existing installed
  compatibility Runner has not been rebuilt in this task.
- **Next gate:** finish the native experiment authority with real response
  capture, result CSVs, completion, and safe execution.
  The Tauri candidate remains non-executable/unqualified. Qualification requires
  observed devices and routes; software tests cannot supply physical evidence.
- **Local constraint:** full native builds and the complete Standard tier need
  additional storage (documented working allowance: 15 GiB). Source checks and
  CI continue; an alternate location or free space has been requested. C: is
  currently full. Native authority integration stays on
  `review/native-playback-authority` until local synchronization is possible.

Detailed run artifacts stay in ignored validation folders. Preserve the pre-sync
Git bundle and dirty-file backup until reconciliation is verified.
