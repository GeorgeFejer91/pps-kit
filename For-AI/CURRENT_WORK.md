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
  part packages linked by a group manifest and returns Part 1. The Runner admits
  Part 2 only when the adjacent Part 1 package and its sealed
  native result reverify from disk, including after a Runner restart. Installed
  part transition and grouped result completion remain open.
- **Latest completed evidence:** `c3e42d1200684b7db62a1506dce4dcfe5509ddf6`
  passed all 14 non-skipped
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37198305035),
  including three-platform Core/Desktop and Python/Rust package oracles plus
  Windows/macOS/Linux validation bundles. The product-source checkpoint
  `bc0665cf` also passed local Runner Core tests (25), frontend tests (66),
  formatting, and the canonical frontend build.
  The Python/Rust differential covered both pre/post packages and PCM bytes;
  the native Part 2 result-proof test covered rejection, a completed Part 1
  after process restart, and changed published event bytes.
  The rendered browser audit used a mocked native bridge, not installed
  execution. Local Runner library tests (141) and the focused publish/resume/
  tamper test passed; CI rebuilt and tested the exact proof revision.
- **Installed Runner UI evidence:** the Runner-only NSIS validation installer
  from `c3e42d12` has SHA-256
  `ade21c6e70066994a8563a4b8226a99c20bdb402c83f4f51cf0dcb0e37df8c4d`,
  matching its manifest and commit marker. Fresh Windows CI installation
  matched bundled HTML/CSS to canonical source and launched the real WebView.
  The exact-build installed audit selected a synthetic, silent three-channel
  prepared package through the native Windows file chooser, adopted its Rust
  verification receipt, compiled its schedule, and decoded its PCM into the
  bounded native cache. The output device remained unselected and unreserved.
  The idle and prepared Rust states, next-block control, and control, logging,
  and remote tabs passed; all three prepared-state screenshots were inspected
  at 1028 px without horizontal overflow. Inventory and report agree on
  installed binary SHA-256
  `f953d00fcf8f474c0075c911fc4d17fba955c69721bd3fcf71c300e7dcc09f6d`.
  The three exact-build screenshots are byte-identical to the inspected
  [installed retry](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37198222783)
  images. No participant execution, physical output, recording, or Full
  installer was verified by this UI audit.
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
