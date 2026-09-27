# Current work

Updated: 2026-09-27. Replace at a meaningful task/stage transition; do not
append command logs or machine-specific paths.

- **Domain:** experiment runtime, with design/UI and release handoffs.
- **Outcome:** implement all 17 approved [audit items](engineering/validation/docs/unification-and-critical-audit-2026-09-27.md)
  using Ponytail and existing centralized owners. Designer creates/previews
  spatial stimuli and exports JSON ingredients/file/assembly profiles; Runner
  reads them, executes experiments, and records data. The existing 3DTI adapter,
  3D viewer, schemas, and profile pipeline are the starting point.
- **Stage:** baseline repair, followed by independently verified implementation
  checkpoints, local UI previews, source promotion, packaged candidates, and
  measured qualification. The audit is approved; do not ask again to implement
  its scoped proposals. Physical evidence cannot be replaced by software tests.
- **Baseline:** source is synchronized at `8daf723`; one local/public branch and
  one registered worktree remain. Candidate native output is non-executable and
  unqualified. Existing native gates fail; full-suite testing exceeded local
  storage. An alternate build/test location or additional free space is requested.
- **Evidence:** prior synchronization and test evidence is retained in the audit.
  Centralized validator-source and owning coverage checks passed: 18 tests,
  with one existing unavailable-local-source skip. Rust formatting now passes;
  compilation/Clippy remain pending storage availability. Pytest uses its native
  successful-scratch cleanup and one failed-run retention instead of a new helper.
- **Next gate:** restore Rust checks, centralize validator source paths, fix the
  Designer development dependency chain, and complete reproducible validation.
  Then simplify the planner/profile flow and connect one native Runner path.

Detailed run artifacts belong in ignored validation folders. Preserve the
pre-sync Git bundle and dirty-file backup until reconciliation is verified.
