# Current work

Updated: 2026-09-27. Replace at a meaningful task/stage transition; do not
append command logs or machine-specific paths.

- **Domain:** experiment runtime, with design/UI and release handoffs.
- **Outcome:** implement all 17 approved [audit items](engineering/validation/docs/unification-and-critical-audit-2026-09-27.md)
  using Ponytail and existing centralized owners. Designer creates/previews
  spatial stimuli and exports JSON ingredients/file/assembly profiles; Runner
  reads them, executes experiments, and records data. The existing 3DTI adapter,
  3D viewer, schemas, and profile pipeline are the starting point.
- **Stage:** planner JSON handoff and shared text measurement, followed by independently verified implementation
  checkpoints, local UI previews, source promotion, packaged candidates, and
  measured qualification. The audit is approved; do not ask again to implement
  its scoped proposals. Physical evidence cannot be replaced by software tests.
- **Baseline:** source is synchronized at `8daf723`; one local/public branch and
  one registered worktree remain. Candidate native output is non-executable and
  unqualified. Native source gates are restored; full-suite testing exceeded local
  storage. An alternate build/test location or additional free space is requested.
- **Evidence:** prior synchronization and test evidence is retained in the audit.
  Centralized validator-source and owning coverage checks passed: 18 tests,
  with one existing unavailable-local-source skip. Rust formatting now passes;
  core and Python/Rust oracle checks passed on three CI platforms at `3e6eeb4`;
  desktop, core, browser, Python/Rust oracle, and optional Android checks passed
  at `9290bea`, including validation package builds on three platforms. Installed
  and physical qualification remain separate. Native output completion
  releases its operation guard before replying and has a reserve/disable/stale
  policy integration check. Pytest uses native successful-scratch cleanup
  and one failed-run retention instead of a new helper. Designer Vite 6.4.3 and
  the transitive nanoid patch report zero npm vulnerabilities. Its canonical
  build, 12-case inspected layout audit, and Pages assembly/parity passed.
  The new local experiment JSON freezes the already approved Segment 5/6 plan
  and verifies its file inventory before compatibility Runner assembly. Both
  direct and JSON preparation pass the existing sample/tactile/CSV contract;
  changed-ingredient and stale/incomplete export denial checks pass.
  The JSON action, planner disclosures, and shared Designer/Runner Pretext owner
  pass the inspected 12-case planner audit and 13 rendered text cases. Runner's
  57 browser checks and canonical Pages assembly byte checks pass. Actual
  WebView accessibility qualification remains pending.
- **Next gate:** fence background generation to its source
  revision, add bounded resource preflight, and connect native output execution.

Detailed run artifacts belong in ignored validation folders. Preserve the
pre-sync Git bundle and dirty-file backup until reconciliation is verified.
