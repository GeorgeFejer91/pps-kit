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
  publication remain unqualified for participant use.
- **Latest completed evidence:** bounded multichannel assembly source `00bd77d3`
  passed local Rust audio/CPAL/media tests, Clippy, formatting, eleven
  Python/Rust differential tests, and all 14
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37184677260).
  Its Runner-only NSIS package passed a fresh Windows CI install inventory.
  The downloaded validation marker matches the commit and its SHA-256 matches
  the artifact manifest. Installed executable and HTML/CSS hashes were recorded.
  That package was not launched; physical output was not tested.
- **Installed Runner UI evidence:** all 14 normal
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37188235590)
  passed for source `bcfc444e`. The separate Runner-only NSIS validation
  artifact has installer SHA-256
  `4da4b70f175791a668af02e53f4c8d5ed7bde5ddf58ead68c9183e3c3d83bdd3`,
  matching its manifest. Fresh Windows CI installation matched the installed
  HTML/CSS to the canonical compiled files and launched the real WebView/Rust
  bridge. The control, logging and remote tabs passed interaction and horizontal
  overflow checks; their screenshots were inspected. The retained report and
  inventory agree on the installed binary hash and document an idle, unverified,
  disarmed state. No participant execution, physical output, recording, or Full
  installer was verified by this UI audit.
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
