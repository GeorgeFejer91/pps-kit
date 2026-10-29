# PPS Kit completion review and multi-agent plan

## Approved implementation extension — 2026-10-27

The user approved implementation of the expanded publication-ready plan.
This section supersedes the earlier setup-only scope and wave assignments;
the source review below remains the finding/evidence inventory.

Subsequent user direction on 2026-10-27: proceed without new calibrations and
assume hardware operation for now. This defers physical calibration work for
the current delivery; it does not turn an assumption into measured timing or
behavioral replication evidence. Installed/software, catalogue and provenance
gates remain required. Retain unqualified physical labels until real measurements
support stronger claims.

Implementation now has verified single-/multi-block native activation,
the hosted persistence/preview/participant fixes, experiment-level mapper,
bounded Rust source generation and corrected 3DTI bridge. Native portable
import verifies inventories and media hashes in a temporary directory, then
publishes and rebinds all four authoring audio groups; original bundle records
remain unchanged alongside a local rebinding receipt. A real nine-asset browser
export passes this offline path. Premade native generation receipts also survive
the existing profile design unchanged, with exact UTF-8/hash/WAV checks before
export and native adoption. Actual browser export, offline re-export and native
import pass; this preserves provenance without asserting source equivalence.
Pages assembly now includes only referenced
spoken assets and their checked manifests. Native immutable participant/part
assembly, ordered instruction/block execution and durable group receipts now
have software evidence. Installed journeys remain separate. The native preview
explicitly excludes V1 LSL/LabRecorder capture; the existing V1 evidence does
not transfer to the Rust preview. CURRENT_WORK remains
the current acceptance checklist; later review findings below are historical
starting conditions, not claims that these implementations are absent.

### Product contract

- First release: audiotactile PPS, Windows, online preparation/preview with
  premade assets, and installed native acquisition. Broader modalities,
  browser research acquisition, macOS/Linux qualification and a new freehand
  spline editor are deferred.
- One canonical HTML Designer and existing viewer, with explicit hosted and
  Tauri adapters. Native errors never silently switch the application to
  hosted mode. Retain endpoint-based polar/Cartesian trajectories, including
  existing angular interpolation, holds and stationary modes.
- Generation, validation, imports, levels, tactile assembly, resource checks,
  jobs and transactional publication move to Rust. Python is an oracle in
  development/CI only, not a shipped fallback. Retain the existing C++ 3DTI
  spatial engine behind a corrected bounded dry-audio interface.
- Preserve editable portable `.pps-profile` bundles and local immutable
  experiment/session formats. Native import must extract, verify and rebind
  assets before success; never invent online native absolute paths.
- Review the current 94-publication corpus, candidate/boundary records and
  experiment splits; perform a bounded foundational-paradigm check, then
  freeze the inclusion inventory. Complete the existing 11-contract review
  with experiment identity, source/page pointers and derivation formulas.
  Keep expanded diagnostic matrices secondary.
- Audited gaps may be published: not reported, explicitly absent/not
  applicable, substitution required, contradiction, or inaccessible after
  documented attempts. Unreviewed blanks/defaults/composite values are not
  verified extraction. Missing evidence withholds replication-ready status.
- Generate public review data from the existing component-gated resolver:
  citation network → review projection → frontend. Preserve stable IDs,
  source authority and build direction; no second database or circular build.
  Separate parameter review, template availability and tested native capability.
- Apply Ponytail, existing Pretext, accessibility and measured-performance
  guidance. MobX guidance governs state-boundary assessment; this release
  retains current state owners without a broad library/framework migration.

### Parallel ownership and handoffs

| Owner | Exclusive work | Consumed / produced boundary |
| --- | --- | --- |
| Coordinator/runtime integrator | Runner Rust actor/core, root Cargo files, shared contracts, integration and current checklist | Verified single-block activation then manifest-order completion; integrates dependency/schema changes serially |
| Scientific catalogue worker | Literature sources/review generators, focused tests, generated network/review JSON | Existing study IDs and 11-contract resolver → sanitized `pps-publication-study-reviews.v1` projection; no native-qualification inference |
| Rust generation worker | `packages/pps-designer-core`, 3DTI wrapper, focused PCM/QC fixtures; later profile assembly | Validated design/immutable source inventory/seed → bounded dry audio and motion → spatial audio → levels/tactile/QC/provenance |
| UI/desktop worker | Existing Designer/Runner HTML frontend, mapper and tests; new Designer Tauri host | Shared Designer façade → explicit adapter; versioned generation requests and revision-bound jobs; public review projection → paper/study/preset UI |

Use one coordinator plus at most three workers and managed worktrees.
Independent implementations are authorized by the approved plan, overriding
the generic skill's serial default. Do not spawn nested coordinators. Rotate
a worker into independent review when a checkpoint finishes; share evidence
rather than running duplicate broad review/test loops.

Wave 1: scientific extraction/projection, frontend defect/mapper work and
Rust generation proceed concurrently; coordinator completes A1 using an
existing verified package. Wave 2: generation/profile assembly connects to
the Tauri host while the actor gains complete block progression and science
continues. Wave 3: close catalogue and UI verification, build/install exact
Windows artifacts, qualify advertised routes, then promote verified outputs.

Preflight ownership decisions: science owns both public data JSON files;
UI alone owns frontend JS/HTML/CSS; coordinator alone owns root dependency
files and Runner actor. Generation never writes the actor, and UI never
duplicates scientific generation. Workers may temporarily enable their new
workspace member for isolated tests; root-file changes are integrated once.
All scope/evidence remains in this plan and CURRENT_WORK, rather than the
generic skills' separate session/test/planning ledgers.

### Acceptance and critical checks

1. Every included publication has an experiment inventory or explicit access
   blocker; every experiment's 11 contracts has a reviewed disposition.
   Presets require resolved necessary evidence and software/route verification.
2. Find paper → inspect study values/limitations → choose correct preset.
   Counts, links and distinct review/template/native labels agree with data.
3. Hosted preset selection → preview → save/reload → portable export includes
   all instruction/media assets. Stale replies and storage failure preserve
   recoverable draft state. Editing a generation-only parameter invalidates
   the premade preview rather than misrepresenting it.
4. Rust outputs satisfy actual waveform and metadata checks: exact sample
   counts, timing/channel maps, explicit seeded algorithms and existing
   numerical tolerances, including applicable ±0.02 dB loudness checks.
   Current C++ continuous-only generation, hidden normalization/attenuation,
   stationary motion and channel/hash defects must be corrected. Incorrect
   legacy behavior is not the scientific oracle.
5. A clean Windows install with no Python imports an online bundle offline,
   customizes its trajectory, generates, reviews the immutable schedule,
   executes every supported block and yields independently verified results.
6. Corruption, missing renderer/HRTF, excessive allocation, low storage,
   cancellation, crash and stale revisions cannot publish partial output or
   advance review. Preserve native callback/journal and authorization fences.
7. Actual browser/WebView controls pass keyboard/focus/names, resizing, long
   labels and zoom checks. Canonical frontend and Pages bytes agree; verify
   deployed routes after promotion. Builds do not prove installed behavior.
8. Each advertised physical route passes its declared timing/calibration
   requirements. Simulation, installation and catalogue completeness never
   stand in for physical onset or behavioral replication.

Runtime compatibility ruling: a proposed new seeded RNG is an explicit V2
generator, never an implicit replacement for NumPy-source profiles. Request,
provenance and fixtures must carry its algorithm version. Legacy compatibility
stays unsupported until demonstrated or deliberately customized; regenerated
catalogue evidence is required before promotion. This keeps a small first
kernel from making a false scientific-equivalence claim.

Source completion, deployed Pages, downloadable packages and scientific
qualification each require their own evidence. The overall goal stays open
until all applicable gates pass.

Reviewed source: `e53a3621ec22697e9748792048e1fff98bfb33d9` (2026-10-27).
Three independent read-only reviews covered runtime/data, authoring/UI, and
science/release. The coordinator checked the main boundaries and consolidated
the findings. This is a source review and completion plan, not an installed or
physical qualification report. Current progress belongs solely to
[CURRENT_WORK.md](../../../CURRENT_WORK.md).

**Goal:** complete the existing Designer → immutable experiment profile →
native Runner → inspectable results workflow, then deliver a reproducible
installed candidate and qualify the specific profiles/platforms/routes that
the release actually claims to support.

**Architecture:** retain the existing renderer, Segment 0–6, Python oracle,
Rust actor, callback scheduler and journal. HTML owns interaction; native code
owns privileged files, execution, clocks and durable results. Preserve V1
compatibility while V2 earns its own evidence. No framework rewrite, new
planner, blanket MobX adoption, transport expansion or default XR work.

**Scope and specification:** the user's 2026-10-27 request extends the
[17-item audit](unification-and-critical-audit-2026-09-27.md) with a current
critical review, installed agent baseline, domain work packages and a durable
finish goal. Earlier implementation evidence remains in
[implementation status](implementation-status-2026-09-27.md). The task delivered
the setup/review/plan; product fixes and release qualification are open.

## What already works and must survive

The project has substantial safety and compatibility foundations: immutable
ingredients, bounded generation/jobs, shared Pretext measurement, one native
authority, callback-confirmed controls, durable Start/Resume intent, immediate
Pause/Stop/Abort, package/run fences, response scoring, paired event/CSV output,
and native completion receipts. Replacing these would create migration risk.
The remaining work is to connect incomplete paths, fix observed interface
defects and close evidence gaps.

## Finish criteria

1. **Software candidate:** a real Designer export imports and materializes
   without manual JSON edits, previews the approved schedule, executes every
   supported block, captures responses, and produces independently verified
   results that the existing analysis/review path can read. Missing assets,
   cancellation, stale state, device loss and interruption have usable outcomes.
2. **Supported scope:** name the profiles, platforms, output/input routes and
   optional LSL/phone features actually supported. The first vertical slice is
   one Windows native route; it does not establish support on every CI host.
   Every advertised route must pass its own acceptance matrix before release.
3. **Usability:** representative tasks pass keyboard, accessible-name, focus,
   zoom, long-label, resize and recovery checks in the actual browser/WebView.
   Bounded utility panels preserve readable full text and their no-scroll
   contract; unbounded records have deliberate paging/detail behavior.
4. **Reproducibility:** complete Standard validation, owning Rust/frontend/Go
   checks, component/privacy checks, and canonical frontend/Pages parity pass
   on the selected revision. Release dependencies/tools are pinned and recorded.
5. **Installed evidence:** fresh artifacts from that revision have hashes,
   component inventories, clean-install and installed-path reports. Operator
   instructions match those packages; expired CI artifacts are not a deliverable.
6. **Research qualification:** physical output/input timing and applicable
   calibration are measured for the named route. Before measurement, declare
   endpoints, sample/load conditions, timing-error/jitter/drift tolerances and
   loss budgets from that profile's requirements; compare results with those
   bounds to produce a pass/fail verdict. Do not invent universal thresholds.
   Software simulation, physical
   onset, perception and behavioral replication remain different claims.
   A new participant study is required only for a claimed behavioral result;
   this plan does not invent one as a generic software completion gate.
7. **Publication:** candidate source completion does not publish installers,
   sign binaries or promote public downloads. Apply the existing release
   authorization and evidence gates to the concrete verified artifact.

## Domain clusters and suggested work packages

P1 blocks reliable use or a defensible release. P2 is required polish or
reliability work for the supported scope. **Reproduced** below means a bounded
in-memory check using the extracted source function, not a browser test.
Line anchors describe the reviewed revision and may move during implementation.

### A. Native execution and complete experiment handoff

| ID / priority | Evidence and consequence | Smallest useful change and acceptance |
| --- | --- | --- |
| A1 / P1 | **Missing capability.** `prepare_native_block` sets `package_execution_ready = false`; `TargetArm` rejects it. Only demo preparation enables that flag. See [core](../../../../packages/pps-runner-core/src/lib.rs), lines 335–359, 748–757 and 940, and [adoption](../../../../apps/runner/src-tauri/src/execution_owner.rs), 2264–2283. | Add an explicit native activation transition through the current actor, verified media/reservation and journal receipts. A real single-block package must run and complete via normal IPC. Reject stale reservations, replacement packages, failed journals and revoked grants; retain pending-start cancellation and immediate safety controls. Never close this item by just setting the flag. |
| A2 / P1 | **Missing capability.** Designer exports `pps-experiment-profile.v1`; assembly exists in [Python](../../../../packages/pps-runtime/src/peripersonal_space_toolkit/experiment_profile.py), 86–140, while [Rust](../../../../packages/pps-session-package/src/lib.rs), 21 and 441–442, accepts `pps-run-session.v1` only. | Add bounded native profile import/materialization into the existing prepared-session contract. Match Python participant/block order, samples, instructions, hashes and provenance. Reject changed/missing ingredients, oversized plans, participant mismatch and inadequate storage; cancellation must not publish a complete package. |
| A3 / P1 | **Missing capability.** The public [audio preparation command](../../../../apps/runner/src-tauri/src/lib.rs), 233–241, selects block 0; [completion](../../../../apps/runner/src-tauri/src/execution_owner.rs), 644–653, requires exactly one block. | Extend the existing actor to manifest-order progression and whole-session completion. Run a three-block fixture including instructions/breaks, closed response windows and interrupted boundaries; first-block completion must never certify the whole experiment. Keep global result indices and generation fences correct. |

Dependencies: A1 establishes the runnable vertical slice. A2 can develop
against the existing package contract in parallel. A3 follows A1 and consumes
A2 without assigning two agents to the actor. Keep all `execution_owner.rs`
and core transition integration with one runtime owner.

### B. Designer consistency, persistence and portability

| ID / priority | Evidence and consequence | Smallest useful change and acceptance |
| --- | --- | --- |
| B1 / P1 | **Reproduced.** [Order preview](../../../../apps/designer/frontend/app.js), 7868–7889, debounces request creation but adopts every response. Reversed responses restore stale state. | Fence adoption by request, project and edit generation. Invalidate pending previews on reopen/save/finalization. Reverse replies and edit/switch projects mid-request; the latest design and accepted schedule must survive. |
| B2 / P1 | **Reproduced.** [Bundle export](../../../../apps/designer/frontend/designer_main.js), 109–115, collects custom/prestimulus assets only; [instruction import](../../../../apps/designer/frontend/app.js), 8737–8742, stores audio in instruction slots. An instruction-only fixture exports no audio. | Include instruction assets through the existing inventory/remapping contract and preserve their identity through normalization. Test hosted import → save/reload → bundle export → native import, plus missing assets and hash mismatch. Avoid a second asset manifest format. |
| B3 / P2 | **Reproduced.** [Finalization](../../../../apps/designer/frontend/app.js), 7927–7931, marks memory finalized before IndexedDB save. Injected quota failure leaves an unsaved locked draft; similar transitions occur near 6939. | Persist a proposed snapshot before adopting finalized UI state. Check quota and transaction failures during continue/accept/finalize; retain the editable draft and a usable draft-export recovery path. |

One Designer agent owns these edits and their regressions sequentially because
they overlap `app.js`. Reuse its source/frontend tests and browser audit; do
not assign separate agents to accessibility and persistence in the same file.

### C. Runner operator and participant workflow

| ID / priority | Evidence and consequence | Smallest useful change and acceptance |
| --- | --- | --- |
| C1 / P1 | **Reproduced.** [Snapshot rendering](../../../../apps/runner/frontend/src/desktop-app.js), 283–287, replaces every unfocused participant field and the sharing checkbox; polling runs each second at 1217–1220. Moving focus can erase an unfinished form. | Separate the form draft from confirmed native state until submit/reset succeeds. Enter all fields across multiple polls/native events; failed submit must retain edits, successful submit/reset must deliberately reconcile them. |
| C2 / P1 | **Missing journey.** [Runner adapter](../../../../apps/runner/frontend/src/api/tauri-runner-adapter.js), 34 onward, exposes prepared-session inspection, not profile assembly. [Desktop UI](../../../../apps/runner/frontend/src/desktop-app.js), 148 onward, is built around that seam. | After A2's contract is fixed, connect profile selection, local participant materialization, immutable schedule review, output/calibration setup, execution and result review. Exercise the complete real-export journey with missing audio, cancellation, multiple blocks and interrupted results. Keep Start disabled when native readiness is absent. |

C1 is independently fixable now. C2 depends on native contracts, not a visual
redesign. The Runner frontend owner must not edit the native actor to bypass
its gates.

### D. Results, acquisition streams and interruption recovery

| ID / priority | Evidence and consequence | Smallest useful change and acceptance |
| --- | --- | --- |
| D1 / P1 for LSL-supported scope | **Missing capability.** [Core](../../../../packages/pps-runner-core/src/lib.rs), 208, initializes LSL readiness false; no Rust outlet was found. V1 owns rich/numeric streams in [timing_events.py](../../../../packages/pps-runtime/src/peripersonal_space_toolkit/timing_events.py), 738 onward. | Add one bounded native event-to-LSL adapter where the chosen release promises LSL. Consume existing authoritative events outside audio callbacks. Verify V1 schema/code parity, actual inlet/recorder receipt, session grouping, absent library/outlet and backlog/loss handling. If excluded from a candidate, label that limitation explicitly rather than implying parity. |
| D2 / P2 | **Missing recovery workflow.** [Journal](../../../../apps/runner/src-tauri/src/event_journal.rs), 116 and 586 onward, creates fresh attempts and publishes manifest last; [startup](../../../../apps/runner/src-tauri/src/runtime.rs), 377, creates fresh authority. [Validator](../scripts/validate_native_results.py), 45 onward, requires a completed manifest. | Expose a read-only assessment of complete/interrupted/orphaned attempts and their common durable event/CSV prefix. Kill the process around append/sync/data-link/manifest-link boundaries, then classify on restart. Never replay playback, overwrite old files or certify partial trials. Check unsupported hard-link filesystems explicitly. |
| D3 / P1 evidence gate | **Unqualified timing, not a demonstrated scoring defect.** [Response ingress](../../../../apps/runner/src-tauri/src/execution_owner.rs), 451 and 2415, timestamps native IPC arrival. [Audio evidence](../../../../apps/runner/src-tauri/src/native_playback.rs), 318 onward, records software submission/callback observations. | Preserve differential scoring tests, then measure installed input/output endpoints on named devices/routes. Record sample counts, loss, p50/p95/p99/worst, load, driver/OS and calibration. Do not infer physical onset from CPAL predictions or WebView clocks. |

An evidence worker may own journal/LSL modules and fixtures. Actor wiring is
integrated serially by the runtime owner. Physical D3 requires A1–A3 and the
installed artifact gate; it cannot be closed by an autonomous source test.

### E. Phone control and transport qualification

| ID / priority | Evidence and consequence | Smallest useful change and acceptance |
| --- | --- | --- |
| E1 / P2, release gate when advertised | **Unverified route.** [Runtime](../../../../apps/runner/src-tauri/src/runtime.rs), 1172 and 1214, advertises HTTP LAN preview and `production_transport_qualified: false`. Existing scopes, dedupe, stale-owner and safety rules already exist. | Qualify one existing securely delivered companion route against the installed actor: command → native application/callback → new snapshot. Test real Android/iOS only where claimed, screen lock/resume, lost acknowledgements, expiry/revocation, observer denial, network loss and direct/relay conditions. Document the actual control-loss policy. Keep discovery inert and participant details local; add no speculative login or transport. |

### F. Accessibility and measured performance

| ID / priority | Evidence and consequence | Smallest useful change and acceptance |
| --- | --- | --- |
| F1 / P2 | **Source-confirmed semantics gaps; AT behavior untested.** Designer condition/jitter labels at [app.js](../../../../apps/designer/frontend/app.js), 5466 and 5612, are unassociated; the instruction input at 6379 is unnamed. Runner [section buttons](../../../../apps/runner/frontend/index.html), 27–34, use selection state without a coherent tab/panel relationship. | Associate stable names with dynamic row/slot controls and choose a coherent tab or ordinary-navigation pattern. Verify names, keyboard order, selection announcements, focus after rerender and dialog restoration in actual browser/WebView, together with the existing Pretext zoom/layout matrix. |
| F2 / P2 | **Scaling risk confirmed; target slowdown unmeasured.** [Variant counting](../../../../apps/designer/frontend/app.js), 5471, 5813, 6648–6668 and 9430, materializes the Cartesian product repeatedly. A bounded six-by-six example allocated 46,656 arrays per call. | Use arithmetic counts and enumerate only a bounded needed preview. Test count/order parity, overflow and generation limits. Profile representative WebViews before assigning latency/allocation budgets; replace source-string assertions with behavior checks. |

Apply the installed accessibility/performance companions to each owning UI
task. MobX is not justified by these findings: fencing, draft ownership,
persistence and bounded computation fix the concrete defects in the current
stack. Reconsider state tooling only if an observed residual problem needs it.

### G. Validation, build reproducibility and packaging

| ID / priority | Evidence and consequence | Smallest useful change and acceptance |
| --- | --- | --- |
| G1 / P1 | **Coverage gap.** Only [Runner](../../../../.github/workflows/runner-next.yml) and [Pages](../../../../.github/workflows/pages.yml) workflows exist. Runner Python jobs at 134–138 cover four oracle files, not V1 Standard, Go downloader or all release/privacy checks. | Reuse [check_all.ps1](../../automation/check_all.ps1), existing component tests and `go test ./...` under the downloader. Run complete Standard on the selected revision; add proportionate path-triggered CI gates for shipped Python, resources and distributions. No new testing framework. |
| G2 / P2 | **Reproducibility risk.** [Setup](../../build/windows/Setup_Windows_App.ps1), 18–19, upgrades pip and resolves ranged dependencies; [downloader build](../../build/windows/Build_PPS_Downloader.ps1), 49, uses `rsrc@latest`. | Pin the tested release dependency environment and resource tool, while retaining useful development ranges. Rebuild from a clean environment, retain resolved versions/hashes, and rerun scientific fixtures. Do not upgrade unrelated product dependencies to match skills. |
| G3 / P1 | **Installed evidence missing.** [CI 36353428304](https://github.com/GeorgeFejer91/pps-kit/actions/runs/36353428304) passed 14 jobs for `97d69fd4`, but its current artifact list contains three synthetic fixtures and no installers. Bundles used seven-day retention at workflow line 270. | Rebuild the selected integrated revision. Retain artifact/component hashes, toolchain and installed-path evidence; verify operation without a source checkout. For maintained V1 packages, test Designer-only, Runner-only and Full with exactly one Shared. Candidate artifacts need an explicit retention policy distinct from release publication. |

The former local storage blocker is no longer observed (about 65.5 GiB free
at review start), but the complete Standard tier has not thereby passed.

### H. Release instructions and operator documentation

| ID / priority | Evidence and consequence | Smallest useful change and acceptance |
| --- | --- | --- |
| H1 / P1 | **Reproduced parameter defect.** [Download instructions](../../../../docs/PPS_DOWNLOADS.md), 76, and [release protocol](../../release/protocols/release_build_protocol.md), 29, use `-ZenodoPayloadUrl`; [build script](../../build/windows/Build_PPS_Distribution.ps1), 3, accepts `-PayloadBaseUrl`. A side-effect-free parameter-binding check leaves the base empty, producing placeholder URLs at line 57. | Update examples to current parameters and validate required release URLs before publication. Assert the documented invocation binds the supplied URL and cannot emit `REPLACE_WITH_RECORD` in a publishable manifest. |
| H2 / P2 | **Stale install/operator contract.** [Fresh-PC protocol](../../release/protocols/fresh_pc_verification_protocol.md), 54–60, expects retired launchers and For-AI content. [WINDOWS_APP.md](../../../../docs/WINDOWS_APP.md), 76–87, advertises default Android behavior although [focus_app.py](../../../../packages/pps-runtime/src/peripersonal_space_toolkit/focus_app.py), 8694 and 9330, disables/hides it. All docs ship through Shared. | Rewrite the existing guides around current component manifests and actual V1/V2/experimental behavior. Follow each installed entrypoint through setup, handoff, results and recovery; check shipped links against installed contents and assert For-AI exclusion. Preserve historical reports as historical, not current procedures. |

### I. Scientific fidelity and recoverable claims

| ID / priority | Evidence and consequence | Smallest useful change and acceptance |
| --- | --- | --- |
| I1 / P1 for qualification claims | **Evidence gap.** [Pipeline ledger](../../../research/literature/preload-ledgers/audiotactile_full_pipeline_validation.json), 7677, 7710 and 7713, records 17 emulated pipelines and zero human/physical observations. Ten report paths in [expected-outcome coverage](../../../research/literature/preload-ledgers/audiotactile_expected_outcome_coverage.json), 34 onward, are absent locally. This does not disprove historical work, but cannot re-establish blanket qualification. | Reconcile current ledgers, README counts and profile labels. Retain a compact evidence index with source revision, report hash/location, profile, apparatus/route, measured endpoint and supported claim. Recover or rerun software reports; distinguish reported parameters, derived defaults, substitutions and unknowns. Keep private data outside Git. |
| I2 / P1 release gate | **Cross-route transfer is unsupported.** V2 uses default CPAL hosts; [cross-platform guide](../../../../docs/CROSS_PLATFORM_RUNNER_AND_REMOTE.md), 335 onward, names WASAPI/CoreAudio/ALSA and excludes ASIO. V1 route history cannot qualify V2 automatically. | Select and measure each advertised native route using the existing calibration protocols. Electrical timing, tactile mechanical onset/perception and behavioral replication must have separate verdicts. Publish only the supported scope, with remaining routes clearly labeled. |

## Multi-agent execution plan

Use one coordinator plus at most three workers in this harness. Reuse managed
worktrees for implementation isolation. Each worker receives a bounded task,
owned paths, stable input/output contract and acceptance cases. No nested
orchestrator, shared actor edits, automatic merge, or duplicate goal ledger.

| Wave | Worker assignments | Integration / exit gate |
| --- | --- | --- |
| 0 — setup/review | Coordinator installs the reviewed baseline; three independent read-only domain reviews | Delivered by this task. Metadata/runtime smoke checks, evidence-linked plan and active goal recorded. Product remains unfinished. |
| 1 — trustworthy base | Runtime: A1. UI: B1–B3 then C1. Validation/release: G1–G2 and H1–H2. | Coordinator fixes the release support matrix and checks each coherent checkpoint. Source regressions must pass; UI worker owns both frontends sequentially during this wave. Native activation stays on its own branch until its evidence is complete. |
| 2 — complete the journey | Runtime integrator: A3, actor wiring. Profile worker: A2 in profile/package owners. UI worker: C2 after the agreed adapter contract exists. | One real exported profile runs every block and yields independently validated output. Python/Rust equivalence and native lifecycle/error checks pass. Freeze result and profile contracts for the next wave. |
| 3 — reliability and polish | Evidence worker: D1/D2, with actor edits integrated by runtime owner. UI worker: F1/F2. Science/docs worker: I1 and the supported-scope records. | Interrupted attempts remain inspectable; advertised acquisition streams are tested. Real browser/WebView verification and measured performance evidence replace source-only assumptions. |
| 4 — installed and qualified | Release worker: G3. Remote worker: E1 after the installed candidate exists. Qualification owner: D3/I2 with the operator and required devices. | Exact-revision clean installs and complete runs; phone and physical evidence for every advertised route. Unsupported or unavailable gates stay open. Release publication is a separate final action. |

Ownership rules: the runtime integrator alone changes `execution_owner.rs`
and core state transitions. The profile worker owns profile/package assembly;
the evidence worker owns journal/LSL modules. UI workers have exclusive
ownership of the frontend tree assigned in that wave, including its tests.
The coordinator serializes shared schema/fixture updates, rebuilds canonical
compiled assets at integration, verifies Pages parity, and maintains For-AI.
Rotate workers when a task finishes; do not create a fourth worker for a
cross-cutting concern that can be reviewed in the next wave.

For every behavioral work package: first capture the failure/required outcome
in an owning regression, implement through the named owner, run the focused
check, obtain independent review, then integrate and run the applicable broader
gate. Keep one concise evidence record per task. A reviewer can reject a task
without reopening unrelated finished work. Do not claim whole-product completion
from an individual task's successful tests.

## Verification commands and review focus

Reuse the repository's existing command owners:

- `powershell -NoProfile -File For-AI/engineering/automation/check_all.ps1 -Tier Standard`
- Applicable Core/Desktop/Browser modes of `For-AI/engineering/automation/check_runner_next.ps1`.
- `npm --prefix apps/designer/frontend run build` and `npm --prefix apps/runner run check`.
- Existing Designer, participant and local-output rendered audit scripts under
  `For-AI/engineering/validation/scripts/`; inspect screenshots and real controls.
- `node --test For-AI/engineering/automation/build_pages.test.mjs`, Pages assembly,
  and the public byte audit after a changed production UI deployment.
- `go test ./...` from `distributions/downloader/`, plus existing package inventory,
  repository-structure and release/privacy tests.

Highest-risk input classes to carry into the owning task's checks are reversed
async replies (B1), lost local persistence (B3), partial media inventories (B2/A2),
interruption at durability boundaries (D2), and stale authorization or device
state at activation (A1/E1). Hardware tests require declared endpoints and
actual devices; mock bridges cannot supply that evidence.

## Current evidence and limits

Four UI failures were reproduced in isolated source-function checks; the
obsolete packaging argument was reproduced with a side-effect-free binding
check. The local, ignored `artifacts/completion-review-2026-10-27/ui_reproductions.cjs`
retains the four UI demonstrations; it asserts the reviewed failures and is
not a future passing regression suite. Native/profile gaps were confirmed by caller and state-transition
inspection. No product code was changed in this review. No full Standard run,
installed application run, physical calibration, phone qualification or new
participant study was performed. Historical passing CI is retained as historical
evidence; it is not a substitute for the new plan's acceptance gates.

For this guidance checkpoint, `test_repository_structure.py` and
`test_release_audit.py` passed (5 tests), 106 local guidance links resolved,
and `git diff --check` passed. Installed baseline verification covered 42
new/updated skill entrypoints, six unchanged supporting skills, 35 role TOMLs,
runtime-reference resolution and GSD identity/discovery smoke checks. Live
Codex settings and hooks matched their pre-install hashes. These checks do not
claim execution coverage of every installed workflow.
