# Current work

Updated: 2026-10-04. Replace at stage transitions; keep historical evidence in
[the implementation record](engineering/validation/docs/implementation-status-2026-09-27.md).

- **Approved goal:** deliver the pps Research Experiment Planner and Runner,
  maintained compartment and JSON contract catalog, one downloadable Full
  Windows installer, and end-to-end visual, installed, media, audio, recording,
  and workflow evidence for the exact release candidate. Continue the 17
  [approved audit items](engineering/validation/docs/unification-and-critical-audit-2026-09-27.md).
  Planner creates/previews looming stimuli and exports JSON ingredients, file
  locations, and assembly rules. Rust/HTML Runner consumes them, executes the
  experiment, and records responses. The target is two standalone Tauri apps
  with bundled local HTML in one Full installer.
- **Method:** use the task-specific [skill inventory](SKILLS.md) and
  Ponytail/YAGNI. The [Tauri Rust developer skill](https://github.com/GeorgeFejer91/tauri-rust-developer-skill)
  governs the native apps. Review every Planner, Runner, and companion shell and
  segment with [Uncodixfy Pretext's accordion stretch reference](https://github.com/GeorgeFejer91/uncodixfy-pretext/blob/main/references/accordion-stretch.md);
  preserve readable no-fit behavior and check rendered and installed WebViews.
  Reuse the 3DTI renderer, 3D viewer, Segment 0–6, current schemas, and
  Python/Rust oracle fixtures.
- **Owning domain:** [experiment runtime](domains/experiment-runtime.md), with
  [UI](domains/design-ui.md) and [release](domains/release-operations.md)
  handoffs. The [workflow](WORKFLOW.md) keeps source, packaging, and release
  evidence separate.
- **Current source:** the native Runner selects and verifies the Planner JSON
  profile, prepares a V1-compatible package, and adopts it through the existing
  native authority. Standard block assembly supports four Python-compatible
  tactile waveform shapes, ITI silence, provisional tactile drive compensation,
  and speaker switching. Its width follows the Python trial maximum with a
  three-channel minimum and an 18-channel bound. The decoded/output path has a
  closed unity-gain, channel-for-channel route for 4–18-channel WAVs.
  Local/phone control shares one actor,
  callback scheduler, and result journal. Source activation and result
  publication remain unqualified for participant use. The candidate now advances
  verified blocks in order, retaining one result journal and requiring a fresh
  output reservation and acknowledgement for each block. Failed in-process
  native profile-package publication rolls back newly linked destination files.
  The bounded producer now stages approved pre/post plans as two verified V1
  part packages linked by a group manifest and returns Part 1. This is source
  behavior only; the installed Part 1-to-Part 2 transition and grouped results
  remain open.
- **Latest completed evidence:** `af15af80315dabab67333cede047bd7469813f75`
  passed all 14 normal
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37193395931),
  including three-platform Core/Desktop and Python/Rust package oracles plus
  Windows/macOS/Linux validation bundles. Local Runner Core tests (25),
  frontend tests (66), formatting, and the canonical frontend build passed.
  The rendered browser audit checked the next-block control at six viewport or
  text-size cases and mocked preparation of block ordinal 1 with four direct
  channels. It used a mocked native bridge, not installed execution.
- **Installed Runner UI evidence:** the Runner-only NSIS validation installer
  from that exact run has SHA-256
  `7fc22ba17817b1e19d291e05a9693299d7413ebe083d3a7d44e1dc5e2f5d2a1f`,
  matching its manifest and commit marker. Fresh Windows CI installation
  matched bundled HTML/CSS to canonical source and launched the real WebView.
  The idle Rust snapshot, next-block control, and control, logging, and remote
  tab checks passed; all three screenshots were inspected. Inventory and report
  agree on installed binary SHA-256
  `0567263b55c211c7c86ac6327cb8d63e348cd7b1b01c32faaf24b95e84c11b2f`.
  No participant execution, physical output, recording, or Full installer was
  verified by this UI audit.
- **Next gates:** qualify each larger-array hardware route and its levels,
  then run the installed native single-block and multi-block workflows on a
  compatible calibrated device; validate event/CSV files and recording; finish
  full-profile media routes; then build and verify the exact two-app Full
  installer. Installed operation, physical
  timing, participant results, and replication each need their own evidence.
- **Local constraint:** complete native V2 builds and the Standard tier remain
  unrun under the 15 GiB working allowance. CI supplies native builds while
  local storage is insufficient for another complete build.

Detailed run artifacts stay in ignored validation folders. Preserve the
pre-sync Git bundle and dirty-file backup until reconciliation is verified.
