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
- **Evidence:** use the single [implementation record](engineering/validation/docs/implementation-status-2026-09-27.md).
  Source, CI packages, installed behavior, physical timing, participant results,
  and published replication are distinct gates. The existing installed
  compatibility Runner has not been rebuilt in this task.
- **Next gate:** adopt the verified media bridge in the native experiment
  authority with response/event persistence, completion, and safe execution.
  The Tauri candidate remains non-executable/unqualified. Qualification requires
  observed devices and routes; software tests cannot supply physical evidence.
- **Local constraint:** full native builds and the complete Standard tier need
  additional storage (documented working allowance: 15 GiB). Source checks and
  CI continue; an alternate location or free space has been requested.

Detailed run artifacts stay in ignored validation folders. Preserve the pre-sync
Git bundle and dirty-file backup until reconciliation is verified.
