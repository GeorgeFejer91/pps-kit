# Approved implementation status

Updated 2026-10-04. Current evidence for the 17 approved
[audit items](unification-and-critical-audit-2026-09-27.md).
Each status applies to its stated surface, not to the whole product.

| Item | Implemented / observed surface | Remaining gate |
| --- | --- | --- |
| 1 | VERIFIED: locked Core/Desktop fmt, Clippy and tests on three CI platforms | Retain these checks through further execution work |
| 2 | PARTIAL: migrated validators, fresh editable setup, bounded fixtures and retained scratch evidence | Complete Standard tier needs more storage |
| 3 | PARTIAL: one compact source/package/capability record; conservative readiness | Complete native adapter and measured evidence |
| 4 | VERIFIED: shared profile/limits/scoring/text/job owners; concise For-AI routing; one native actor/scheduler/file worker | Extract only seams changed by further work |
| 5 | VERIFIED browser source: planner disclosures/JSON action, phone Pair/state/action flow, participant response, local output picker and inline notifications; native Runner installed UI opened and its control, logging and remote panels were inspected | Full V2 Planner install and complete installed flows |
| 6 | PARTIAL: actual Pretext, explicit no-fit, complete labels, keyboard input, narrow/enlarged text and spacing; installed Windows Runner WebView tab screenshots and horizontal geometry | Planner/companion installed WebViews and full accessibility qualification |
| 7 | PARTIAL: frozen approved Segment 5/6 CSV plan, inventory hashes, review revision/lineage fences | Full scheduling UI and native profile assembly |
| 8 | VERIFIED: plan/resource preflight, source/cancel/publication fences, shared job completion and rollback | Qualify additional generation routes if selected |
| 9 | PARTIAL: exact CPAL port, fenced sequential block activation in source, one run journal and package-total result count, local output preflight, closed unity-gain direct route for 4–18-channel WAVs, callback-confirmed controls, local input, shared V1 scoring/CSV and receipt-gated result publication | Compatible calibrated hardware route, installed multi-block playback/results, full-profile execution and qualification |
| 10 | PARTIAL: shared Rust/browser contracts; JSON to existing compatibility assembler; Rust JSON inventory and participant block/trial selection; content-bound PCM16 trial decoding, bounded 3–18-channel block assembly, four tactile waveform shapes and speaker switching, and V1 prepared CSV/manifest; native main-window profile/folder selection, predecode storage preflight and existing Runner package adoption; Python PCM/row comparison and sample/tactile/response/CSV oracle checks | Installed adoption, complete profile execution and qualified physical routes |
| 11 | PARTIAL: authenticated local/phone commands use one dispatch/control owner, shared scope fixture and fresh-state gate | Complete real-package execution |
| 12 | PARTIAL: retry/input fences, durable intent versus callback confirmation, bounded deadlines, per-run journal and exclusive hashed result publication | Installed filesystems, recovery and complete execution |
| 13 | PARTIAL: secure hosted companion, inert discovery, existing authenticated VDO route | Physical phone direct/relay/network-loss qualification |
| 14 | PARTIAL: suspension/resume, no replay, stale-state denial, disarmed phone outputs and pending-activation cancellation | Physical Safari/Chrome lock and BFCache cases |
| 15 | VERIFIED source policy: local setup, observer scope, participant-free public projection and fresh invitations | Physical expiry/revocation; remembered phones remain unselected |
| 16 | VERIFIED: locked Designer Vite 6.4.3/nanoid patch; both npm audits report zero advisories | Retain locked byte checks |
| 17 | PARTIAL: exact-revision CI validation packages; isolated Windows NSIS Runner install and package/schedule/PCM preparation; fresh install inventory, frontend resource hashes, and real installed Runner WebView/native snapshot/tab audit; source/Pages checks | Two-app Full installer, installed complete run, measured output/response/calibration and supported routes |

## Current source evidence

- Two-part Planner-profile source candidate: the native producer follows the
  existing Python `pps-runner-part-split.v1` and `pps-run-session-group.v1`
  boundaries for approved pre/post plans. It returns Part 1 for Runner adoption,
  keeps Part 2 as a separate verified package, and rolls back a failed Part 2
  publication without touching unrelated files. The Python/Rust differential
  compares both parts' PCM bytes and prepared row identities; Python can load
  both manifests. Local media/session-package tests, Clippy, and catalog checks
  passed. Commit `87d2dd707781de807af984da193738b01bed7143` passed all 14
  non-skipped [CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37195331037).
  Its exact Windows validation installer has SHA-256
  `d299dd038eea70dff035fdf3f791cebdb073546aafd11d4cc34dbd1ded7ced50`;
  the installed idle WebView audit passed with binary SHA-256
  `4564b916e0546b2f9feff23025d3c40d5e016b5e102bbe12865d4913f18f9af4`.
  The next source candidate verifies a sealed native Part 1 result before
  adopting its sibling Part 2, including after restart; a local publish/resume/
  tamper test passed. Installed part transition, result-group completion, hardware output,
  recording and the two-app Full installer are not established by this source
  evidence.
- Sequential native-block and next-block UI source checkpoint
  `af15af80315dabab67333cede047bd7469813f75` passed all 14 normal
  [CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37193395931):
  Core/Desktop and Python/Rust package oracles on Windows, macOS and Linux,
  the rendered browser audit, and three validation bundles. Local Runner Core
  tests (25), frontend tests (66), formatting, and canonical frontend build
  passed. The candidate advances verified blocks in ordinal order, keeps one
  result journal, requires a fresh native output reservation and local
  acknowledgement for each block, and only finalizes after the last block with
  the package's total trial count. The main-window-only no-argument IPC chooses
  the next block in Rust. The rendered audit measured the new control at six
  viewport or text-size cases and mocked block ordinal 1 with four direct
  channels; it did not execute physical playback.
  The downloaded unsigned Runner-only Windows NSIS validation installer has a
  matching source marker and SHA-256
  `7fc22ba17817b1e19d291e05a9693299d7413ebe083d3a7d44e1dc5e2f5d2a1f`,
  equal to its manifest. A fresh Windows CI install recorded executable
  SHA-256 `0567263b55c211c7c86ac6327cb8d63e348cd7b1b01c32faaf24b95e84c11b2f`;
  installed HTML/CSS hashes match canonical source. The real installed WebView
  returned the Rust idle snapshot and displayed the next-block control. Its
  control, logging and remote tabs passed horizontal geometry at 1028 CSS px;
  all three screenshots were inspected. Inventory and report agree on audit
  SHA-256 `0dd6484b6aba35e9f7a7dbd5e4f92195a4c7a759fc5bf117ec163d07d198bba2`.
  This is an idle UI/bridge check. Installed multi-block execution, participant
  results, recording, calibrated output, physical timing, the Planner Tauri app,
  and a two-app Full installer remain unverified.
- Exact-source package-publication and installed Runner-only WebView checkpoint
  `7591525c7381dafe0590597d4b1c8659edbc1656` passed all 14 normal
  [CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37190366500),
  including three-platform Core/Desktop and Python/Rust V1 package oracles and
  the Windows NSIS fresh install/WebView audit. Local media tests (5), Clippy,
  and one-block/two-block package differentials passed. A new publication guard
  removes only files linked by a failed in-process package publication; its
  test covers rollback, an unrelated file, success, and no overwrite. The
  downloaded unsigned Runner-only validation installer has a matching commit
  marker and SHA-256
  `7d88a8db9e52dc6dd1ecf296f450552b607681de959324af825722fc10edba45`,
  equal to `SHA256SUMS.txt`. Windows CI installed executable SHA-256
  `d521696bd91a3d1f17ad798fce7cf507b08e011db201d821d45c8b0723e1808b`;
  installed HTML/CSS match the canonical compiled bytes. Inventory and the
  separate screenshot/report artifact agree on audit SHA-256
  `7018d7c585e5b8ecb8621aea125fdb5ed429359da53767eaf13ba79639f8c503`.
  The installed WebView returned the real Rust idle snapshot and passed
  control/logging/remote tab clicks and horizontal geometry at 1028 CSS px.
  All three exact-run screenshots were inspected. The control and remote views
  scroll with the document. This was an idle UI/bridge check: no package
  activation, participant response, physical output, recording, Planner app,
  or Full two-app installer was qualified.
- Installed Runner-only WebView checkpoint: the Windows NSIS validation artifact
  from `893ada652716f0159fc0b301d28902653bb6b1ec` has a matching
  `VALIDATION_ONLY.txt` marker and measured installer SHA-256
  `23ed5a86c121de8513d1c9f9020a329c6ff1b7e7320e91b32a66b6b7bf7ce80e`,
  equal to its manifest. Windows CI installed it fresh, recorded installed
  binary/HTML/CSS hashes, and matched frontend bytes to the canonical build.
  The first [full CI attempt](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37187006243)
  passed the build and inventory but failed the WebView audit because
  Playwright reported `about:blank` while the CDP target had the Tauri origin.
  An [audit-only retry](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37188087715)
  used the same installer and audit script `9f7aefd4`. It verified the real
  `pps-runner-authority-snapshot.v1` Rust bridge in idle state, an unverified
  package, disarmed local output and disabled response. Playwright clicked the
  Experiment Control, Data Logging and Phone Remote tabs in the installed
  WebView; retained screenshots were inspected and document no horizontal page
  overflow at 1028 CSS px. The control and remote views use host document
  scrolling for longer content. The installed executable SHA-256 was
  `1e1c523b5475b4a5ee4d52d91f99ee58d6ad6fc23a407aa66f2b637d7bdb28d3`.
  The audit used an app-specific, temporary HKLM WebView2 debugging policy on
  the elevated ephemeral Windows runner and restored it after execution.
  Neither this UI audit nor the original installer inventory executed a
  participant run, physical output, recording, or the two-app Full installer.
- Bounded multichannel native source checkpoint
  `00bd77d30b13f0a84f45649640e9201093bd07c3` resolves the closed
  unity-gain 4–18-channel output route, then assembles 3–18-channel block WAVs
  according to the maximum approved trial output width. Rust audio, CPAL and
  media tests/Clippy passed locally. Eleven Python/Rust differential tests
  compared PCM byte for byte and V1 CSV fields, including speaker targets on
  channels 8 and 16 and a separate tactile target on channel 17. All 14
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37184677260)
  passed across Windows, macOS and Linux. The earlier direct-route commit
  `dadedbc9` failed desktop compilation because a new error variant lacked a
  Runner mapping; this checkpoint includes that correction. The downloaded
  Runner-only Windows NSIS validation package has the matching source marker
  and measured SHA-256 matching its manifest:
  `e985eafadff10813671334b4f88e5f047fbbf61afd57961a7a1c2d35550cfa49`.
  Windows CI recorded fresh-installed executable, HTML and CSS hashes. No
  installed WebView, physical output, recording, participant run or two-app
  Full installer was qualified by this artifact.
- Native three-channel speaker switching source checkpoint
  `c014d75feabf2081a24c4612032cc3559f56f47e` reproduces the Python
  segment-boundary, gain, source-channel and tactile-preservation behavior in
  Rust block WAVs and V1 CSV metadata. Eleven local Python/Rust differential
  tests and Rust media tests/Clippy passed. All 14
  [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37183464651)
  passed, including three-platform Python/Rust oracles and validation bundles.
  The downloaded Runner-only Windows NSIS validation package carries the exact
  source marker; its measured SHA-256 matches the manifest:
  `61861e5c8348fcee2c250b9f80abc8bd3d9f397af02ae0c1e285fb764640c827`.
  Fresh Windows CI installation recorded executable, HTML and CSS hashes in
  `INSTALL_INVENTORY.txt`. That check launched no installed WebView and
  qualified no physical output or recording.
- Native tactile waveform source checkpoint
  `5685fc10c2f87f305019a77222fa77d16413dc9d` synthesizes sawtooth,
  sine, square, and biphasic square pulse-train shapes on channels 1–3. Local
  Rust media tests, Clippy, formatting, and nine Python/Rust profile
  differentials passed; fixtures compared block PCM byte for byte, including
  source padding, trial extension, tactile drive advance, and prepared CSV
  metadata. All 14 [exact-SHA CI jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37182084204)
  passed, including Windows/macOS/Linux Python/Rust V1 oracles and three
  validation bundles. The downloaded Windows Runner-only NSIS artifact has an
  exact-commit validation marker and matching SHA-256 manifest; measured
  SHA-256 is `3cf01ca66f2b9bc1eade6831ad766fbae1787509043265e5de3b9cf49ae82c3a`.
  Its Windows CI fresh-install inventory recorded the installed executable,
  HTML and CSS hashes. No installed WebView was launched in that check, and no
  physical output, recording, or participant execution was qualified.
- Windows Runner-only installed-inventory CI checkpoint
  `0f22443cb356567c34e6c1ce3703a46950784fa2` passed all 14
  [exact-SHA jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37180140321).
  Its NSIS validation installer ran silently in a fresh Windows CI directory.
  The installed `pps-experiment-runner.exe` existed, and the installed
  `web/index.html` and `web/assets/style.css` SHA-256 values matched the
  canonical compiled source files. The retained `INSTALL_INVENTORY.txt` records
  these hashes and explicitly states that no WebView was launched or physical
  output qualified. The downloaded NSIS artifact has the exact commit marker
  and a measured hash matching its SHA-256 manifest:
  `2e06ec20be240bfc185bb07aae6a425ecadadf74eeaac06610518f852946243f`.
  This is a Runner-only CI install check, not the two-app Full installer or an
  installed workflow on this PC. Native profile execution and results remain.
- Runner profile-control rendered checkpoint
  `2326fe7073b4dd1dcd88ee4bf96adbbf8b9ee11d` added a remote browser
  audit of the canonical compiled HTML and fixed verified block-row wrapping
  at narrow widths. The audit exercised native-dialog cancellation and a
  path-free eight-block summary with a mocked Tauri bridge, then captured six
  narrow, desktop, and 32 px enlarged-text screenshots. Its retained report
  confirms no panel/button or page horizontal overflow and no nested block-list
  scrollbar in those cases. Local 66 frontend tests and canonical build passed.
  [Exact-SHA CI](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37179265515)
  passed all 14 jobs, including the rendered audit, three-platform Rust and
  Python/Rust oracles, and Windows/macOS/Linux validation bundles. The
  downloaded Windows NSIS Runner-only artifact has a matching commit marker;
  its measured SHA-256 matches the manifest:
  `f19b22d80c13bf77a226e5da2a75dfa290b3fe8c8401b96942cc0088bd610cb1`.
  Browser screenshots use a mocked native boundary. This artifact has not been
  installed, and neither installed WebView operation nor physical output or
  recording is qualified.
- Native block storage preflight checkpoint
  `d0b2ebc56c8da93f242a634f45f68eefb8e3e1ef` checks the selected
  filesystem's available bytes before decoding a trial or creating its WAV.
  It uses each approved block's bounded PCM estimate plus a threefold reserve
  and 8 MiB margin; low or unverifiable storage returns a sanitized native
  error. Local media tests, Clippy, locked check/metadata, formatting, and
  seven Python/Rust profile differentials passed. Its
  [exact-SHA CI](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37177890540)
  passed all 14 jobs. The downloaded Windows NSIS Runner-only validation
  artifact has a matching commit marker and SHA-256 manifest; measured hash:
  `34b1b95eb7dfb0c08289fddcf530fd6341c2bed37bcc13e2424da7776f143bf4`.
  It is unsigned and has not been installed or visually checked.
- Native Planner JSON adoption source checkpoint
  `07c93b27653dacbe4531b9c52c54413faecbbe93` links the existing
  standard-route media crate to the Runner through a main-window-only,
  no-path-argument Tauri command. Native dialogs select the JSON and output
  folder; the blocking worker rechecks the inventory and writes a V1 package;
  the existing verified-package authority adopts the native receipt. The
  bundled Runner UI exposes the action after participant setup, measures its
  two full labels with shared Pretext, and keeps the ordered block list in host
  document flow. Local fmt, 66 frontend tests, canonical frontend build, and
  locked Cargo metadata passed. [Exact-SHA CI](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37176982714)
  passed all 14 jobs, including Core, Desktop, Python/Rust V1 oracles on all
  three platforms and the three validation bundles. The downloaded Windows
  NSIS Runner-only artifact's commit marker matches this source and its
  SHA-256 matches the manifest:
  `b4beead5e364596f8a86bf17b1288e507f5e3a158ee7b7bdae79e5913853c470`.
  It is unsigned, validation-only, uninstalled and not visually checked;
  storage preflight, advanced transforms, full native execution, recording and
  physical qualification remain.
- Standard-route native package source now writes all of one approved
  participant's single-phase blocks as V1 CSV/WAV files and publishes the
  canonical manifest after staged and final verification/schedule compilation.
  Local `pps-experiment-media` Clippy/check/tests, `pps-session-package` tests,
  and seven Python/Rust differential tests pass, including populated V1 row
  fields, byte-identical PCM, and a two-block order fixture. The source
  checkpoint is `7d59dece351cff8060b2e5c105de773e6c714e47`.
  [Exact-SHA CI](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37175498741)
  passed all 14 jobs: Rust Core, Tauri Desktop, Python/Rust V1 oracles on
  Windows/macOS/Linux, Browser, Quest preview, and three validation bundles.
  The downloaded Windows NSIS Runner-only artifact has a matching commit marker
  and verified SHA-256
  `1e0b97ca9a1946c18ccc1197a14b6e8114f794e1eedd16cbaf8773162af14c5b`.
  The media crate is not linked into that Runner executable. Installed adoption,
  compatible output selection, recording, and physical qualification remain.
- Native standard-route profile media source checkpoint:
  `ceb12d02f1ad3d6bc66c24b01bc37931abd7bd47`.
  [Its exact-SHA CI](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37173235934)
  passed all 14 jobs, including Rust Core, desktop, and Python/Rust profile
  oracles on Windows, macOS, and Linux plus three validation bundle builds.
  Local Rust Core fmt/Clippy/tests and five focused Python differential tests
  passed. A synthetic two/three-channel PCM16 fixture matched Python block
  PCM byte for byte, including ITI padding, filename-derived tactile onset,
  and provisional drive advance; active tactile synthesis and speaker switching
  reject.
  The downloaded Windows NSIS Runner-only validation artifact has an exact
  commit marker and a verified SHA-256 of
  `c966496f70ef45b3f9e350812fc8fb10b96d320b9e7d6e512b79fe7d1fd17af4`.
  It has not been installed. The new media crate is not linked to that Runner
  binary; prepared CSV/manifest creation, full transforms, installed playback,
  recording, and participant data collection remain unverified.
- Earlier native participant-plan source checkpoint:
  `1fe2c645cdcf98e727b2deb8949a77f1a3bf1e76`.
  [Its exact-SHA CI](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37170957558)
  passed all 14 jobs, including the Python/Rust profile/order oracle on Windows,
  macOS and Linux and all three validation bundle builds. Local checks passed
  13 Rust integration and three compile-fail documentation tests, Clippy,
  formatting, five focused Python handoff/compatibility tests, and five
  component-manifest/contract-catalog structure tests. The downloaded Windows
  NSIS validation artifact's exact-commit marker and SHA-256 manifest matched
  its actual SHA-256
  `cadd7c3e9c4199c4af6f3bf7598b194a2a985136fe9018fcb1b869ddb17550b1`.
  Rust now selects one participant's existing Segment 6 block order and stable
  Segment 5 trial-index order from rechecked profile/setup/CSV bytes. Its plan
  is native-only and provisional: trial audio must be rehashed during media
  assembly. This exact package has not been installed, visually checked, or
  used for playback, recording or participant data collection. Native JSON
  media assembly and complete execution are still absent.
- Earlier native JSON inventory preflight source checkpoint:
  `9015f12d35f50a19be106f7483a49764fcea792d`.
  [Its exact-SHA CI](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37169370392)
  passed all 14 jobs, including the three Python/Rust V1 oracle jobs with the
  new Planner-exported JSON profile differential cases and the three validation
  package builds. Local profile tests passed (2), as did bounded generation
  and dashboard-job checks (4 each); the Rust session-package tests, Clippy
  and formatting passed. The downloaded Windows NSIS validation artifact's
  exact-commit marker and SHA-256 manifest matched its actual SHA-256
  `55f0ca5782d554663de37e81d3f48d13a0d5273d4ad1a02ac75ce77f430ff3da`.
  This adds bounded, read-only Rust verification of the Planner's local JSON
  ingredient inventory. It does not native-assemble or execute the profile.
  This exact package has not been installed, visually checked, or used for
  playback, recording, or participant data collection.
- Earlier Runner UI/readiness source checkpoint: `0471968181b8569ac1ac9d1689025cd03c10b08e`.
  [Its exact-SHA CI](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37167989483)
  passed all 14 jobs. It corrects stale native-readiness copy and wraps enlarged
  package detail text. Local checks passed 65 frontend tests, canonical build,
  six rendered output layouts/control cases, 24 Rust Core tests, two Pages
  assembly checks. CI also rejected generated-asset drift. The Windows NSIS
  validation artifact matches SHA-256
  `cdb10373d7e373d48096ce22df7243be49c443ecd75b6c275c036f1845f7a052`.
  Its marker records this exact commit, unsigned/validation-only distribution,
  and unqualified scientific status. This newer artifact has not been installed
  or visually checked from its package.
- Native single-block activation source: `41f192d39a66b7cc4f7221cd20b8e40853e149c3`.
  [Its exact-SHA CI](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37166255621)
  passed all 14 jobs, including Rust Core and Tauri Desktop on three operating
  systems, browser, Python/Rust V1 oracle, and Windows NSIS validation bundle.
  Local frontend checks passed 65 tests, canonical build and six output-layout
  cases. The NSIS file matched its SHA-256 manifest
  (`bdcb9be409a534b55c2d453a8c15fbd867cc112641c6d66aa9d8d64cb31cf1ff`).
  An isolated clean-path install launched the bundled Windows WebView. In that
  installed app, a fresh synthetic V1 package passed verification, Rust schedule
  compilation and first-block PCM preparation (661 frames, 44.1 kHz, three
  channels). Device inventory offered no matching three-channel configuration.
  Data Logging showed no durable scientific log or physical capture readiness;
  Phone Remote remained disabled/local-only. No route was reserved, no playback
  started and no participant result was recorded. The bundle is marked
  `single_block_native_candidate_unqualified` and remains validation-only.
- Native control/input product source: `43566f52cdb2835ce629b18da8fe5da592a3e2af`.
  [Validation run](https://github.com/GeorgeFejer91/pps-kit/actions/runs/36351078594)
  passes all 14 source/oracle/browser/optional-Quest/validation-package jobs, including Core and
  Desktop checks on Windows, macOS and Linux: 23 shared-core and 140 desktop
  tests per host. The three validation installers were built, not installed here.
  Documentation-only synchronization does not change these product bytes.
- Output-setup UI source: `97d69fd448b2a3bb92331f3a377e84a54bd006b9`.
  [Its exact-source CI](https://github.com/GeorgeFejer91/pps-kit/actions/runs/36353428304)
  passed. The preceding UI candidate
  [passed all 11 source/oracle/browser/optional-Quest jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/36352863787).
  The final repair clears the UI media summary when Rust retires its cache on
  release/disable; the audit enforces fresh audio preparation before another
  reservation. Native backend files remain unchanged from the verified controls.
  Local checks pass: 65 frontend checks, canonical build, two
  Pages assembly checks, six output layouts/control cases, six participant
  layouts/input cases and 15 shared text/lifecycle cases. Both native UI audits
  use a mocked bridge. The output audit covers exact channel/rate selection,
  large decimal generations, stale inventory, disable versus late replies,
  lost acknowledgement without replay, known idle/disarm state and fresh choice
  after suspension.
  Notifications remain in document flow at enlarged sizes. These are compiled
  controls/error checks, not installed acquisition or physical route evidence.
- Planner/profile checks: 53 owning design/profile/job checks and 15 actual
  package assembly checks include direct/JSON equivalence, stale review/input,
  low-storage, failed renderer and cancel/publication race denials. Existing
  3DTI and the 3D viewer remain the stimulus owners; Python remains the oracle.
- The native-controls synchronization `517e155a813f97d35a6008eab1101da4da135cfb`
  [passed all 14 jobs](https://github.com/GeorgeFejer91/pps-kit/actions/runs/36351705620).
  Its three validation installers were built, not installed here. The current
  output UI [Pages deployment](https://github.com/GeorgeFejer91/pps-kit/actions/runs/36353428303)
  succeeded; fresh parity passes all 470 files and four main routes.
  Repeat hosted parity after each changed UI deployment.
  Pages uses the canonical compiled companion assets; text inputs use LF.

## Native contract and limits

Controls report intent separately from application. Start/Resume wait for the
synced event prefix; a matching callback acknowledgement confirms playback.
Pause bypasses that durability wait and cancels pending activation. Stop, Abort,
disarm, revocation and media retirement neutralize the same native port. Ports,
journals and completion receipts retain package/run/sequence fences and deadlines.
The participant button sends only bounded choice/normalized pointer content;
native ingress supplies clock, ID and block. Main-window-only broadcasts cannot
be emitted by the UI. Older snapshots or missing capture readiness cannot enable
input. Browser/remote commands cannot manufacture native completion.

The same bounded worker freezes and syncs events/18-column Data_min CSV,
exclusively publishes final names, checks hashes and writes the result manifest
last. The native receipt must match the frozen package/run/count/sequence before
completion. Independent Python validation checks actual synthetic Rust worker
files, event/CSV projection and substituted or malformed evidence. The native
source candidate advances verified blocks in order, retaining one run journal
and requiring a fresh silent output reservation and local acknowledgement for
each block. Final publication uses the compiled package's total trial count,
closed response windows and an elapsed final software submission estimate.
Interrupted/missing trials cannot complete.

Unsupported hard-link filesystems fail closed. Partial/pending/orphan files remain;
no final data are overwritten or automatically removed. Power-loss recovery,
directory durability, device drain and physical onset require separate evidence.
Callback observations, sample positions and CPAL driver predictions are explicitly
unqualified. Preparation does not enable execution or qualify a device route.
Sequential activation is present in source. A complete installed multi-block
experiment, more local build storage and calibrated physical acquisition remain
outstanding. The installed preview changed only an
isolated validation path. No participant acquisition, scientific replication,
physical onset or newly qualified route is claimed by this record.
