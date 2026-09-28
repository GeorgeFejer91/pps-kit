# Current work

Updated: 2026-09-28. Replace at stage transitions; do not append command logs.

- **Approved goal:** implement the 17 [audit items](engineering/validation/docs/unification-and-critical-audit-2026-09-27.md).
  Use Ponytail and existing owners. Planner creates/previews looming stimuli
  and exports JSON ingredients/file/assembly profiles. Rust/HTML Runner consumes
  them, executes experiments and records the specified data; phone controls
  use the same native authority. Scoped proposals already have approval. The
  desktop packaging target is two standalone Tauri/Rust apps with bundled HTML
  and one Full installer that adds Experiment Planner and Experiment Runner.
  After clean-path verification, use it to reinstall both apps on this PC.
  GitHub Pages does not provide their PC-connected GUI.
  See [the packaging plan](packaging/README.md).
- **Domain:** [experiment runtime](domains/experiment-runtime.md), with UI and
  release handoffs. Reuse 3DTI, the 3D viewer, Segment 0–6, current schemas,
  bounded jobs, native ownership and Python/Rust oracle fixtures.
- **Source stage:** JSON export/compatibility assembly, bounded generation,
  shared Pretext, locked dependency patches and phone recovery are implemented.
  Native execution has one actor, one callback scheduler and one journal worker.
  Immutable PCM, response scoring, paired event/CSV files and exclusive result
  publication share package/run fences. Local and phone commands now use the
  same control path: durable Start/Resume intent, matching callback confirmation,
  immediate Pause and pending-activation cancellation. Stale ports, writers,
  snapshots and completion receipts cannot authorize another attempt.
  The participant response button calls local native IPC; main-window state
  updates enable it only after native confirmation. Partial or interrupted
  evidence cannot certify completion. Local output setup uses the existing
  native preflight commands, exact device/configuration fences and silent
  preparation. Disabling pending preparation never restores a late result;
  resumed UI needs fresh output state and an explicit device choice.
  Release/disable retires the displayed media cache and requires audio preparation again.
  Desktop notifications stay in their owning panel. Preparation does not enable Start.
- **Evidence:** the single [implementation record](engineering/validation/docs/implementation-status-2026-09-27.md)
  identifies exact source and checks. Source, CI packages, installed behavior,
  physical timing, participant results and replication remain distinct gates.
  A local V1 Designer/compatibility Runner Full Windows package was rebuilt on
  2026-09-28 and both installed entrypoints opened in a clean-folder smoke.
  It is an unpublished packaging candidate, not V2 or physical qualification.
- **Next gate:** native experiment activation and one complete installed
  experiment; extend the same owner to full profiles/multiple blocks.
  The candidate remains non-executable/unqualified until its complete adapter
  is enabled. Qualification requires observed devices/routes and calibration;
  source tests cannot supply physical evidence.
- **Local constraint:** complete native V2 builds and the Standard tier remain
  unrun under the 15 GiB working allowance. Local V1 packaging and installed
  smoke succeeded with current free space; CI supplies native V2 builds.

Detailed run artifacts stay in ignored validation folders. Preserve the pre-sync
Git bundle and dirty-file backup until reconciliation is verified.
