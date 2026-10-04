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
  publication remain unqualified for participant use. Failed in-process native
  profile-package publication now rolls back newly linked destination files.
- **Latest completed evidence:** local media tests (5), Clippy, and one-block
  and two-block Python/Rust package differentials passed for the publication
  rollback. All 14 normal
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37190366500)
  passed for source `7591525c`, including three-platform Core/Desktop and
  Python/Rust oracles plus Windows/macOS/Linux validation bundles.
- **Installed Runner UI evidence:** the Runner-only NSIS validation installer
  from that exact run has SHA-256
  `7d88a8db9e52dc6dd1ecf296f450552b607681de959324af825722fc10edba45`,
  matching its manifest and commit marker. Fresh Windows CI installation
  matched bundled HTML/CSS to canonical source and launched the real WebView.
  The idle Rust snapshot and control, logging, and remote tab checks passed;
  all three screenshots were inspected. Inventory and report agree on installed
  binary SHA-256 `d521696bd91a3d1f17ad798fce7cf507b08e011db201d821d45c8b0723e1808b`.
  No participant execution, physical output, recording, or Full installer was
  verified by this UI audit.
- **Next gates:** qualify each larger-array hardware route and its levels,
  then run the installed native
  single-block workflow on a compatible calibrated device; validate event/CSV
  files and recording; extend to full profiles and multiple blocks; then build
  and verify the exact two-app Full installer. Installed operation, physical
  timing, participant results, and replication each need their own evidence.
- **Local constraint:** complete native V2 builds and the Standard tier remain
  unrun under the 15 GiB working allowance. CI supplies native builds while
  local storage is insufficient for another complete build.

Detailed run artifacts stay in ignored validation folders. Preserve the
pre-sync Git bundle and dirty-file backup until reconciliation is verified.
