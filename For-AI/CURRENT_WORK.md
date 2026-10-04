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
- **Latest completed evidence:** `8a37ea42e5d0d3a6b1f7116fca489eed183e0625`
  passed all 14 non-skipped
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37201160311),
  including three-platform Core/Desktop and Python/Rust package oracles,
  rendered browser UI, and Windows/macOS/Linux validation bundles. Local
  Runner frontend tests (66), canonical build, repository structure tests (5),
  and diff checks also passed. The Python/Rust differential covered both
  pre/post packages and PCM bytes; native Part 2 proof tests covered restart
  admission and tampered result rejection. Rendered browser tests use a mocked
  native bridge; installed execution is audited separately below.
- **Installed Runner UI evidence:** the Runner-only NSIS validation installer
  from that same revision has SHA-256
  `8c9be2828a24a19076e6ef966d0811721cc6853335ad60e3a4373cc859576ae5`,
  matching its manifest and commit marker. Fresh Windows CI installation
  matched bundled HTML/CSS to canonical source and launched the real WebView;
  inventory and audit agree on installed binary SHA-256
  `85abb506840c29f6864ae37c1bdabf357f31b85aa100795b3ebfd31609ff4364`.
  The [exact-build installed audit](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37201160311)
  submitted participant setup, selected a synthetic Planner JSON profile
  through the native Windows chooser, generated and verified a V1 package,
  compiled the Rust schedule, and prepared native PCM. Its generated 44.1 kHz,
  three-channel WAV had 5,441 frames with tactile samples in the target and
  silence in the other channels and catch/ITI; it reserved no output device.
  The intermediate **Submitted** setup badge and final **Ready** state passed.
  Control, logging, and remote screenshots were inspected at 1028 px with no
  horizontal overflow. This audit did not execute a participant run, physical
  output, recording, or the two-app Full installer.
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
