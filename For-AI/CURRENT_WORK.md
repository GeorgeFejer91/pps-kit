# Current work

Reviewed: 2026-10-29. Overall completion goal: **OPEN**.
This file owns the active checklist. Replace current state; retain detailed logs
in ignored artifacts and historical checkpoints in Git.

## Objective and release boundaries

Finish the approved [completion plan](engineering/validation/docs/completion-review-2026-10-27.md):
audited audiotactile catalogue and citation mapper, reliable hosted preparation,
Python-free Windows Rust/Tauri Designer and complete native Runner/results,
verified public Pages and downloadable installers. The user explicitly authorized
installer publication and fresh installed checks on 2026-10-28, renewed this
unfinished scope on 2026-10-29, and requested the Uncodixfy Pretext skill mirror
and stretch-accordion geometry throughout the UI.

- Hardware operation is **assumed** at the user's request; new calibrations are
  deferred. Never describe physical timing or behavioral replication as measured.
- Retain the committed preview identities `org.peripersonalspace.designer.preview`
  and `org.peripersonalspace.runner.preview`; publish an unsigned x64 preview.
- Online Designer prepares and previews premade assets; custom generation uses
  native Rust and the bundled C++ 3DTI renderer. Python is a development oracle.
- Preserve one canonical HTML frontend, existing viewer, explicit hosted/native
  adapters, Segment 0–6 and immutable profile/session contracts. Native failure
  never silently falls back to hosted generation.
- Native preview excludes V1 LSL/LabRecorder/XDF capture, analog loopback,
  automatic missed-trial top-up, automatic interrupted-acquisition resume and
  the V1 analysis UI. V1 evidence does not qualify the native preview.
- Broader modalities, browser participant acquisition, macOS/Linux qualification,
  a new freehand spline editor and a broad MobX migration remain deferred.
- One coordinator and at most three workers, exclusive ownership and managed
  worktrees. No nested coordinators or simultaneous shared-ledger editors.

## Current source and authoritative evidence

Designer and native backend source remain at `ff72fa98b2cf94aaf4368b2f910ef35f7fef7f63`.
The latest packaged candidate is `df347168302362718bbd9093fe5e95d780e32b72`.
The subsequent Runner correction removes its fixed body minimum, checks usable
client width and verifies settled focus paint; a new exact package run is required.
Both canonical frontends reproduce committed bytes; Pages assembly/parity passes.

- [Source CI at ff72fa98](https://github.com/GeorgeFejer91/pps-kit/actions/runs/40780012977)
  passes all 14 jobs. Windows Standard: 762 passed, nine assessed scope skips,
  one Python deprecation warning, 1,949.10 s. Eight skips are Android companion/
  administration outside this release; one needs ignored PubMed abstracts.
- [Candidate at ff72fa98](https://github.com/GeorgeFejer91/pps-kit/actions/runs/40780005491)
  builds both installers and passes exact installed payload checks, actual
  Designer generation/preview, genuine OS-browser acknowledgement, mapper
  Cancel/Confirm and Runner startup. Installed payloads have no Python runtime
  and run with system-only PATH. Designer has 495 verified files; Runner has 18.
- That candidate also captures all 30 presets and passes all 25 eligible native
  test-host pipelines: 4,740 source rows/61 source blocks become 27 executed
  parts, 73 block occurrences, 127 media stages, 46 gates and 5,148 scored and
  independently audited dataset rows. Every part verifies complete PCM,
  saved occurrences, schedules, response identities/outcomes/RTs and manifest joins.
  Scoring partitions into 3,948 unique synthetic responses, 762 correct withholding
  outcomes and 438 deliberate omissions. V1-compatible `Hit` includes correct
  withholding; do not interpret its total as detection hits or behavioral accuracy.
- The same job **fails** hosted mapper navigation waiting for `load`, before the
  hosted export-to-native bridge executes. It is not a passing release candidate.
  Preserve immutable artifact `12859129071` and its failed run. Downloaded files
  under `artifacts/cloud-candidate-ff72fa98/` pass independent source/hash/count
  review; its hosted bridge report is absent.
- The mapper timeout remains unreproduced. Test-only follow-up `8672b65b`,
  integrated as `df347168`, closes completed browser contexts, records bounded
  navigation/request/dialog diagnostics and preserves the original error when
  screenshot capture fails. All 30-second navigation/action waits remain.
  Its actual Chromium 151 hosted workflow passes all 15 groups, including
  the 94-publication mapper and finalized 204-row portable export/binding.
- [Fresh full Windows candidate](https://github.com/GeorgeFejer91/pps-kit/actions/runs/40798632119)
  at `df347168` **passes** (job `123201093597`), including installed checks,
  the full hosted-to-native bridge and all-30-preset sweep. Immutable artifact
  `12866912190` is 1,100,336,880 bytes, archive SHA256
  `848af5100bbb75e1204af579713d75ee5120b40a8c12966aee3c5bb89cd79654`.
  Its local download is running into `artifacts/cloud-candidate-df347168/`.
  [Final packaged WebView matrices](https://github.com/GeorgeFejer91/pps-kit/actions/runs/40802910296)
  report success against those exact installers. Independent screenshot review
  nevertheless found Runner's 320px horizontal scrollbar: body minimum width
  is 320px while classic scrollbars leave 305px. Its assertion compared against
  `innerWidth`, falsely passing the 15px overflow. **Publication is held** until
  the shrinkable-body/client-width correction is packaged and actually verified.
  Strengthen the focus check to await a completed, nontransparent indicator too.
- [Ordinary source CI at df347168](https://github.com/GeorgeFejer91/pps-kit/actions/runs/40798639709)
  passes all 14 jobs. Superseded metadata/retention-only runs `40796542939` and
  `40798178682` were cancelled to release capacity; neither is a pass.

The representative hosted-to-native bridge previously passes locally through
production import, full native review/accept/preparation and existing Runner
execution: nine verified embedded assets, exact design after asset rebasing,
corrupt-WAV rejection preserving prior authority/revision, 204 source rows/six
blocks, two distinct 204-row/six-block parts, five instruction slots each,
20/19 stages, 10/11 gates, 2,991 events and 408 scored/dataset rows with a durable
group receipt. This is software evidence with synthetic responses and a simulated
sample clock, not installed picker/acquisition or physical-timing evidence.
The fresh Windows job must repeat it on its own hash-bound export.

Current implementation includes stale-preview fences, transactional save/import
handling, instruction-audio export, participant-draft preservation, verified
portable import/materialization, explicit generation provenance, corrected 3DTI
policies, real intertrial silence, ordered instructions/blocks/parts, durable
journals/group receipts and read-only recovery. Relevant contracts and detailed
source evidence live in the [implementation record](engineering/validation/docs/implementation-status-2026-09-27.md)
and [runtime domain](domains/experiment-runtime.md).

The native dialog plugin previously replaced synchronous `window.confirm` with
an async Promise and could discard before approval. The shared Rust-file-dialog
adapter now retains native pickers without plugin JS overrides or generic dialog
IPC. All five Designer discard/reopen guards require literal `true`. Sixty JS
checks, both GUI-free native adapter checks and strict Clippy pass; ff72's actual
installed Cancel/Confirm checks pass. External links use bounded HTTP(S) native
OS handoff; same-window mapper loading retains the existing draft guard.

## Catalogue and software scope

The frozen corpus has **94 publications, 178 study/context rows and 1,958 reviewed
11-contract dispositions**. Every publication has an assessed experiment inventory
or documented access blocker; there are no unassessed/composite placeholders.
The 94 entries comprise 74 Methods-backed inventories (59 current primary,
eight retained primary, seven author-version records awaiting final comparison),
19 documented access blockers and one project-lineage record. A bounded antecedent
check found 11 of 12 selected papers; Occelli 2010 remains an outside-map omission
candidate. Do not claim exhaustive literature coverage or silently change membership.

There are **30 presets: 28 published and two local**. Twenty-five are configuration-
eligible software plans. These five guards have zero accepted rows/blocks,
`native_complete_block_plan_required` and native execution `not_run`:

- `ferri_2015_artificial_looming_valence`
- `ferri_2015_ecological_looming_valence`
- `serino_2007_blind_cane_users`
- `taffou_2014_cynophobic_rear_looming`
- `teneggi_2013_social_face_pps`

Those five do not produce usable experiment files as shipped. Thirty presets
are not 94 runnable studies. Templates cover 16 publications/21 study rows;
four published templates have citation-only rather than study-specific mapping.
Reviewed-source completeness, template availability, native test-host completion
and native acquisition qualification are distinct. All catalogue native
qualification fields remain `not_assessed`; the mapper explicitly explains this.

Retain source/count conflicts for Matsuda, Noel, Barumerli and Roussel; do not
replace reported values with defaults. Noel walking's reported 1,000–1,500 ms
range lacks distribution/anchor: the explicit uniform whole-ms after-audio
realization is a reviewed toolkit customization. Native noise uses the versioned
V2 algorithm, not NumPy parity. Comparator generation and customization must
remain explicit; successful software execution never establishes paper equivalence.

## UI and installed verification

The exact installed Uncodixfy Pretext snapshot, license and geometry references
are mirrored in [skills/uncodixfy-pretext](skills/uncodixfy-pretext/SKILL.md), with
hashes in `UPSTREAM.json`. Locked Pretext 0.0.8 is unchanged. Outside-in geometry
covers both app shells, nested bounded groups and text/action cells. Unbounded
records use explicit paging/detail or document flow; preserve readable no-fit,
keyboard/focus, text-spacing, reduced-motion and zoom behavior.

Hosted checks include Runner's 80 JS checks/210 rendered cases, Designer's full
workflow and compact/classic-scrollbar/About/label matrices. Actual WebView
follow-up `40751499138` passes Runner's six cases, 42 views and 18 keyboard checks;
Designer found two geometry defects now fixed in source. Repeat **both** packaged
six-case matrices on the new successful candidate. CDP CSS viewport/zoom evidence
does not establish OS-window dragging or assistive-technology qualification.

Earlier native automation failed before initialization with `failed to write
kernel assets` (os error 3). On 2026-10-29 the documented CUA runtime initializes
and returns actual app/window inventory again; no PPS window is currently open.
Final-package OS-picker interaction remains untested. Preserve existing local
app data and drafts; do not redirect or erase an existing user profile to pass CI.
A clean Windows installation without an existing WebView2 runtime is also
unassessed. The installers include verified offline WebView2 setup, but this PC
and hosted Windows images already have a runtime.

Automatic review rejected the earlier **local exact-payload Runner verification/
launch command** as `blocked by policy`; nothing in it executed. Do not retry or
use another local launch route to bypass that rejection. Fresh disposable Windows
CI is the approved safer alternative. The new CUA availability does not revoke
that boundary. Local installed binaries have not been updated by source commits.

## Active completion checklist

- [x] M0 — Installed baseline/routes and evidence-linked completion plan.
- [x] M1 — Hosted authoring/participant fixes, public review projection and
  validation/build baseline.
- [x] M2 — Real single-block native authority activation with silent synthetic
  software fixture; preserve separate installed/physical gates.
- [x] M2G — Frozen generation contracts, Rust generation and corrected 3DTI
  dry-source bridge; explicit versioned algorithms and provenance.
- [ ] M3 — Final hosted export → offline native import → custom generation →
  accepted schedule → every saved block/part → independently audited results.
  Source/native test-host checks pass; fresh joined CI and complete installed
  interaction remain open.
- [ ] M4 — Supported acquisition/recovery, accessibility/performance and evidence
  gates. Catalogue, mapper/source semantics and complete preset software sweep
  pass; final installed WebView matrices/acquisition evidence remain open.
- [ ] M5 — Exact final Windows installers and advertised route verification
  without Python/checkout paths. Hardware is assumed; new calibration is deferred.
  Keep OS-picker, clean missing-WebView and installed full-journey gaps explicit.
- [ ] M6 — Publish verified installers, hashes, corresponding renderer source and
  scoped reports; anonymously download/hash-check every asset; promote and verify
  canonical Pages. Do not close the overall goal solely for an intermediate port.

## Publication state and next actions

Integration branch: `codex/pps-publication-integration`, previously pushed through
`df347168`. Worker checkpoints `0af822b8` and `7f3c2525` are now integrated:
80 JS tests, 210 classic-scrollbar rendered cases, six focused cases/42 views/
12 keyboard checks, canonical build and both Pages parity checks pass. Narrow
views now measure 305/305 with no horizontal scrollbar; Age has a real settled
3px focus ring. Backend, scientific inputs and shared contracts remain frozen.
Rebuild and repeat actual installed checks before release. The generated df347168
public reports remain intermediate and must not be published as the final release.
[PR #2](https://github.com/GeorgeFejer91/pps-kit/pull/2) is draft/open/unmerged;
its description now reflects the current scope and pending gates. Primary checkout
`main` was last observed at `ae8a4aa4`; preserve other chats' changes.
`native-preview-v0.1.0` remains an **asset-free draft prerelease**, targeting ff72
until the final candidate is verified. No Pages/download promotion has occurred.

1. Inspect GitHub for a live candidate/source run at the new Runner-fix branch
   HEAD and reuse it; dispatch the existing full Windows job only if absent.
   The df347168 runs are terminal successes with the independently found UI gap.
   Retain diagnostics and repair proven causes; never fabricate a passing gate.
2. After the complete candidate succeeds, dispatch the existing packaged-layout
   follow-up with its exact run ID; download immutable candidate/layout artifacts.
   Verify source attribution, all installer/source hashes, installed reports,
   fresh hosted bridge, all 30 captures/25 pipelines and both actual layout matrices.
3. Regenerate strict public JSON/CSV through the existing preset-population
   exporter. Keep source-hash/freshness and multipart receipt checks intact.
   The ignored `artifacts/assemble_public_installed_report.py` assembles the
   separate sanitized installed report only after actual evidence passes.
4. Stage eight public assets: two installers, renderer-source ZIP, immutable
   candidate manifest, software JSON/CSV, installed report and SHA256SUMS covering
   all seven non-checksum files. Never mutate the build manifest to claim later
   installed/publication status, and never upload raw journals/private captures.
5. Publish the authorized preview, then independently anonymously download/hash
   all eight assets. Only then commit the seven held publication docs/download
   changes and current evidence; make PR ready and merge without rewriting history.
6. Assemble/promote canonical Pages and verify all public bytes plus `/`,
   `/documentation`, `/download`, `/experiment-runner/`, CNAME and GitHub fallback.
   Keep source, installed software, public assets and physical qualification distinct.

Seven publication files remain intentionally unstaged until assets exist:
`README.md`, `docs/PPS_DOWNLOADS.md`, `docs/NATIVE_WINDOWS_PREVIEW.md`,
`docs/WINDOWS_APP.md`, `docs/GITHUB_PAGES_DASHBOARD.md`,
`For-AI/download_package_inventory.md`, `website/download/index.html`.

## Workspace preservation

Four superseded worker worktrees are recoverably archived, including dirty source.
Their ignored artifacts were hash-verified in the existing local Proton folder;
cloud upload completion is unverified. The Proton client repeatedly created Git
metadata name clashes; exact refs/index were recovered, conflict originals and
pre-sync/dirty backups retained, and Git connectivity verified. Keep that client
stopped until its conflict is resolved. On 2026-10-29 it restarted and again lost
the integration ref/index and renamed the UI worktree registration and config.
After stopping it, original metadata was backed up, exact remote-verified active
refs and the original config/registration restored, and missing indices rebuilt
without changing working files. Four invalid conflict refs are preserved outside
Git's ref namespace; connectivity checks pass. All eight pending documentation
edits remain intact. Keep the additional recovery evidence in ignored artifacts.
The integration and two managed UI/runtime
checkouts remain active. Large builds belong on CI because local space is limited.

The user approved deletion of this integration checkout's `target/debug/incremental`
cache only, but automatic review still
rejected it as `blocked by policy`. Do not retry that deletion through another
shell/tool/path. No such cache deletion occurred. Historical intermediate build,
layout and failed-attempt details remain in this file's Git history, including
checkpoint `f3aec0f1`, and the linked implementation/domain records.
