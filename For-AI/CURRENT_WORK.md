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
  part packages linked by a group manifest and returns Part 1. The next source
  candidate admits Part 2 only when the adjacent Part 1 package and its sealed
  native result reverify from disk, including after a Runner restart. Installed
  part transition and grouped result completion remain open.
- **Latest completed evidence:** `87d2dd707781de807af984da193738b01bed7143`
  passed all 14 non-skipped
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37195331037),
  including three-platform Core/Desktop and Python/Rust package oracles plus
  Windows/macOS/Linux validation bundles. Local Runner Core tests (25),
  frontend tests (66), formatting, and the canonical frontend build passed.
  The Python/Rust differential covered both pre/post packages and PCM bytes.
  The rendered browser audit used a mocked native bridge, not installed
  execution. Local Runner library tests (141) passed before the Part 2 proof
  change; its focused publish/resume/tamper test then passed.
- **Installed Runner UI evidence:** the Runner-only NSIS validation installer
  from `87d2dd70` has SHA-256
  `d299dd038eea70dff035fdf3f791cebdb073546aafd11d4cc34dbd1ded7ced50`,
  matching its manifest and commit marker. Fresh Windows CI installation
  matched bundled HTML/CSS to canonical source and launched the real WebView.
  The idle Rust snapshot, next-block control, and control, logging, and remote
  tab checks passed; all three screenshots were inspected. Inventory and report
  agree on installed binary SHA-256
  `4564b916e0546b2f9feff23025d3c40d5e016b5e102bbe12865d4913f18f9af4`.
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
