# Current work

Updated: 2026-10-04. Replace at stage transitions; do not append command logs.

- **Approved goal:** deliver the complete pps Research Planner/Runner suite,
  a maintained compartment and JSON contract catalog, one Full Windows installer, and
  end-to-end visual, installed, media, audio, recording, and workflow evidence
  against the exact release candidate. Continue the 17 approved
  [audit items](engineering/validation/docs/unification-and-critical-audit-2026-09-27.md).
  Use Ponytail and existing owners. Planner creates/previews looming stimuli
  and exports JSON ingredients/file/assembly profiles. Rust/HTML Runner consumes
  them, executes experiments and records the specified data; phone controls
  use the same native authority. Scoped proposals already have approval. The
  desktop packaging target is two standalone Tauri/Rust apps with bundled HTML
  and one Full installer that adds Experiment Planner and Experiment Runner.
  After clean-path verification, use it to reinstall both apps on this PC.
  GitHub Pages does not provide their PC-connected GUI.
  See [the packaging plan](packaging/README.md).
- **Implementation method:** use the [skill inventory](SKILLS.md) and
  Ponytail/YAGNI. The GitHub-sourced Tauri Rust developer skill governs both
  native apps; Uncodixfy Pretext's accordion stretch mode is reviewed for each
  Planner Segment 0–6 and Runner/companion UI segment, with readable no-fit
  behavior and rendered/WebView checks.
- **Domain:** [experiment runtime](domains/experiment-runtime.md), with UI and
  release handoffs. Reuse 3DTI, the 3D viewer, Segment 0–6, current schemas,
  bounded jobs, native ownership and Python/Rust oracle fixtures.
- **Source stage:** JSON export/compatibility assembly, native inventory,
  approved participant order selection, standard-route block PCM assembly and
  V1-compatible prepared CSV/manifest publication in the media crate,
  bounded generation, shared Pretext,
  locked dependency patches and phone recovery are implemented.
  The Runner main window now selects a local Planner JSON profile and output
  folder through native dialogs, prepares a standard-route V1 package on a
  blocking Rust worker, and adopts it through the existing verified-package
  authority. The WebView receives only the path-free summary. Native execution
  has one actor, one callback scheduler and one journal worker.
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
  The separate native Runner source candidate `41f192d3` passed all 14 exact-SHA
  CI jobs, including the Windows NSIS validation bundle. That installer was
  hash-checked, installed in isolation, and opened; its UI verified a synthetic
  V1 package, compiled its schedule, and prepared one native PCM block. Device
  inventory found no configuration matching that synthetic three-channel block.
  A newer UI/readiness source checkpoint `04719681` passed all 14 exact-SHA CI
  jobs and produced a hash-checked Windows NSIS validation bundle; it has not
  been installed or visually checked from its package. The native JSON
  inventory and participant-plan source checkpoint `1fe2c645` passed all 14
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37170957558).
  Its Windows NSIS validation artifact has an exact-commit marker and matching
  SHA-256 `cadd7c3e9c4199c4af6f3bf7598b194a2a985136fe9018fcb1b869ddb17550b1`;
  it has not been installed. Rust selects the approved participant block and
  trial order from the verified local profile and CSVs. The later standard-route
  PCM assembly source checkpoint `ceb12d02` passed all 14
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37173235934),
  including Windows/Linux/macOS Python/Rust oracle checks. Its Windows NSIS
  Runner-only validation artifact has the exact-commit marker and matching
  SHA-256 `c966496f70ef45b3f9e350812fc8fb10b96d320b9e7d6e512b79fe7d1fd17af4`.
  It has not been installed, and the new media crate is not wired into that
  Runner executable. The later standard-route package source checkpoint
  `7d59dece` passed all 14 [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37175498741),
  including the three platform Python/Rust oracles and validation bundles.
  Its Windows NSIS Runner-only artifact has the exact-commit marker and matching
  SHA-256 `1e0b97ca9a1946c18ccc1197a14b6e8114f794e1eedd16cbaf8773162af14c5b`.
  It has not been installed. The later native adoption source checkpoint
  `07c93b27` passed all 14 [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37176982714).
  Its Windows NSIS Runner-only artifact has the exact-commit marker and matching
  SHA-256 `b4beead5e364596f8a86bf17b1288e507f5e3a158ee7b7bdae79e5913853c470`.
  It has not been installed or visually checked. The later native storage
  preflight checkpoint `d0b2ebc5` passed all 14
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37177890540).
  Its Windows NSIS Runner-only artifact has the exact-commit marker and matching
  SHA-256 `34b1b95eb7dfb0c08289fddcf530fd6341c2bed37bcc13e2424da7776f143bf4`.
  It has not been installed. The later Runner profile layout checkpoint
  `2326fe70` passed all 14
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37179265515).
  Its remote compiled-browser audit captured six narrow, desktop and enlarged
  text cases with a mocked native bridge; both local profile actions used
  path-free IPC. The downloaded Windows NSIS Runner-only artifact has the
  matching commit marker and SHA-256
  `f19b22d80c13bf77a226e5da2a75dfa290b3fe8c8401b96942cc0088bd610cb1`.
  It has not been installed on this PC. The later installer-inventory checkpoint
  `0f22443c` passed all 14
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37180140321).
  Its Runner-only NSIS package installed silently into a fresh Windows CI path;
  the installed executable and canonical HTML/CSS resource hashes were checked.
  The downloaded installer matches its commit marker and SHA-256
  `2e06ec20be240bfc185bb07aae6a425ecadadf74eeaac06610518f852946243f`.
  No installed WebView was launched in that CI check. Advanced media transforms
  and installed native execution from the JSON profile remain incomplete.
- **Next gate:** extend native media assembly to the approved advanced routes
  through the Python oracle, then complete an installed native single-block
  run with a checked,
  compatible and calibrated output route, then validate its event/CSV files and
  recording. Extend the same owner to full profiles/multiple blocks. The native
  activation path exists in source but remains unqualified; no participant run or
  physical timing evidence is claimed. Build the two-app V2 Full installer and
  verify that exact package separately before release.
- **Local constraint:** complete native V2 builds and the Standard tier remain
  unrun under the 15 GiB working allowance. CI supplies native V2 builds; local
  storage is presently insufficient for another native build without cleanup.

Detailed run artifacts stay in ignored validation folders. Preserve the pre-sync
Git bundle and dirty-file backup until reconciliation is verified.
