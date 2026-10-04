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
  closed unity-gain, channel-for-channel route for 4–18-channel WAVs. Windows
  output discovery now includes ASIO before WASAPI and admits F32/I32 stream
  formats. Its bounded 256-config inventory retains the three-channel 44.1 kHz
  route even after lower ASIO rates on an 18-output device; physical route
  calibration remains open.
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
  part transition and grouped participant result completion remain open. The
  independent file audit now derives a two-part aggregate from both sealed
  results, exact package hashes, shared setup identity and prepared trial counts.
- **Latest completed evidence:** exact source `3a84b1bb1c93709e0457f96ff52795865868a251`
  passed all 16 non-skipped
  [CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37233421923),
  including three-platform Rust Core/Desktop and Python/Rust package oracles,
  rendered Runner output/participant and Planner segment audits, standalone
  validation bundles, and the Full two-app
  Windows install. The Full validation installer is retained as a downloadable
  [workflow artifact](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37233421923/artifacts/11315461950)
  through 2026-10-11. Its SHA-256 is
  `13660c54edad608c80a24887d79f267640fb9d85a4c59b25ab3252f7328ce783`,
  independently checked against the artifact's `SHA256SUMS.txt`.
  It is unsigned and marked validation-only, not a participant-use release.
- **Installed two-app evidence:** the exact Full installer had zero missing or
  mismatched entries across 21 component inventory items, one compatible
  Shared tree, both shortcuts, and successful clean install, reinstall,
  uninstall, and incompatible-Shared rejection. Both bundled WebViews launched.
  The installed Planner showed all seven segments and its 3D viewer, rendered
  3DTI audio at 44.1 kHz/3 channels/7,938 frames, and exported a JSON profile
  with six inventoried source files and two blocks. The installed
  Runner prepared that actual profile for `P001`, generated a verified
  two-block package (each 3 channels and 7,938 frames), compiled the Rust
  schedule, prepared native PCM, and wrote a durable **partial** event journal
  and 18-column CSV. A separate synthetic profile audit also passed. The
  installed screenshots cover the Planner segments and Runner control, logging,
  and remote tabs; review of all ten saved views and their geometry found no
  horizontal overflow at the installed 1013/1028-pixel widths. The Runner's
  multichannel audio and physical capture controls remain disabled. Its native
  output inventory was empty on the CI host, so
  neither installed audit reserved physical output or completed participant
  acquisition. A separate three-platform synthetic native-result
  fixture reached a complete result manifest; the independent Python validator
  passed its event/CSV hashes and V1 projection on the downloaded Windows
  fixture. A Rust-produced two-part Windows fixture also passed the new group
  audit with 10 event records, six scored trials and four Data_min rows; each
  result matched its prepared package trial count. These are file-contract
  evidence, not installed recordings.
- **Next gates:** select the stable Runner bundle identifier and ASIO SDK
  distribution license path, qualify the
  physical 3-channel route and levels, then exercise the installed native
  single-block and multi-block workflows on compatible calibrated hardware.
  The Rust output callback has no digital audio evidence writer or input capture
  stream yet; the disabled Data Logging audio controls accurately reflect that
  source gap. V1 Python has separate optional digital-output WAV and wired
  loopback paths. Implement and verify those distinct evidence routes without
  treating prepared PCM as a recording or a loopback as measured tactile onset.
  Verify finalized event/CSV results and recording, measured output/response
  timing, full-profile media routes, and any claimed replication. Reinstalling
  the candidate on this PC and public signed release promotion are separate
  gates; CI installation is not evidence for those surfaces.
- **Local constraint:** complete native V2 builds and the Standard tier remain
  unrun under the 15 GiB working allowance. CI supplies native builds while
  local storage is insufficient for another complete build.

Detailed run artifacts stay in ignored validation folders. Preserve the
pre-sync Git bundle and dirty-file backup until reconciliation is verified.
