# PPS Kit Module and Ownership Map

Read this after `For-AI/README.md` and before structural edits.

## Product Applications

### Designer

- Canonical frontend source and compiled offline/online artifact:
  `apps/designer/frontend/` and `apps/designer/frontend/compiled/`.
- Trajectory viewer: `apps/designer/frontend/viewer/`; the frontend build copies
  it into `compiled/viewer/`.
- Native/source launchers: `apps/designer/launchers/`.
- Windows/Linux product definitions: `apps/designer/packaging/`.
- Python service/controller facade:
  `packages/pps-runtime/src/peripersonal_space_toolkit/dashboard_app.py`.
- Native system-WebView shell and `pps-designer`:
  `designer_shell.py`; `pps-dashboard` remains its one-release compatibility
  alias.
- Segment 0-6 public contracts and lineage:
  `peripersonal_space_toolkit/designer_segments/`.

### Experiment Runner

- Native/source launchers: `apps/runner/launchers/`.
- Windows product definition: `apps/runner/packaging/PPSExperimentRunner.spec`.
- Focus Mode product implementation: `focus_app.py`.
- Prepared-experiment/session materialization and runtime:
  `session_runner.py`, `profile_preparation.py`, and `focus_launch.py`.
- Output/event/analysis support needed for normal Runner operation:
  `session_events.py`, `session_analysis.py`, `analysis_review.py`,
  `output_evidence.py`, `timing_events.py`, `topup.py`, and related runtime
  modules.
- The packaged executable is the only participant-facing Runner entrypoint.
  Legacy direct Python/Tk runner execution remains retired.

Candidate V2 boundaries coexist with, but do not replace, that V1 path:

- Tauri desktop and shared browser frontend: `apps/runner/src-tauri/` and
  `apps/runner/frontend/`; deterministic compiled web bytes are in
  `apps/runner/compiled/`.
- Browser discovery/private transport adapters:
  `apps/runner/frontend/src/remote/beacon-contract.js`, `vdo-beacon.js`,
  `vdo-transport.js`, and `websocket-session.js`. Public beacon frames are not
  control authority; private BRSP sessions are.
- Native single-owner authority actor:
  `apps/runner/src-tauri/src/execution_owner.rs`. Its named
  `pps-runner-authority` thread owns `RunnerCore`, remote policy/current owner,
  the retained verified package and compiled plan, package/run/owner
  generations, the bounded prepared-PCM cache, and the bounded `EventLedger`.
  `runtime.rs`, `remote.rs`, and
  Tauri commands are async adapters; the exact WebView claim/renew/dispatch/
  revoke DTOs remain exposed only to the bundled main window by the Tauri
  capability/command manifest.
- Versioned action/state/wire contracts: `packages/pps-contracts/`.
- Transport-neutral BRSP/1 proof and sequence rules: `packages/pps-brsp/`.
- Pure target-authoritative reducer: `packages/pps-runner-core/`.
- Pure read-only V1 prepared-session verifier:
  `packages/pps-session-package/`. Its native receipt owns resolved paths and
  digests but is deliberately non-serializable; only its path-free summary may
  cross Tauri IPC.
- Pure schedule-compatibility and bounded-ledger layer:
  `packages/pps-runner-execution/`. Raw sample events can retain V1 path-bearing
  payloads and stay native; only path-free schedule summaries may cross IPC.
- Optional experimental Quest/Spatial SDK application context and JNI adapter:
  `apps/quest-runner/`.

The desktop WebView and Quest Activity are adapters to the shared Rust reducer
and may not own independent experiment state machines or expose arbitrary
native calls. The browser phone experiment is itself a target and therefore
owns a strict JavaScript reducer mirroring the closed action/state contract; it
still needs Rust-to-JavaScript differential fixtures before promotion. The
validated Python Runner remains the scientific compatibility oracle while
functionality is migrated incrementally. Python is not part of the final V2
module graph: no shipped worker, sidecar, fallback authority, timing path,
PySide, PyInstaller, or interpreter is allowed after the Python-free release
gate passes.

The Tauri prepared-session chooser is a no-argument command restricted to the
bundled main window. Rust owns the operating-system picker, verification, and
receipt retention. Package adoption disarms the reducer and rotates remote
authority, while verified V1 plans remain non-runnable until a native execution
adapter is present. The Python/Rust differential status probe lives in
`For-AI/engineering/tests/test_rust_session_package_differential.py` and runs
as its own Windows/macOS/Linux Runner-preview CI matrix in addition to the Rust
crate matrix. Picker/verification is native single-flight; a retained verified
plan cannot be replaced by the demo action.

The no-argument `inspect_prepared_execution` Tauri command reverifies that
retained receipt, compiles every block in manifest order, and generation-fences
the cached native schedules. The WebView sees only a bounded path-free summary
marked `schedule-only`, `unqualified`, and non-executable. This is an
inspection/conformance boundary, not an audio or experiment execution adapter.
Each prepared CSV is compiled from the exact bounded bytes matched to its
selection-time digest. `pps-session-package` now also retains a native-only
path/SHA-256/encoded-byte receipt for every prepared WAV. The pure
`packages/pps-runner-audio/` crate verifies that exact bounded byte stream and
decodes only PCM16 legacy two-channel `[tactile, audio]` or canonical
three-channel `[left, right, tactile]` data into a non-serializable immutable
block. It has no Tauri, network, device, or experiment-state dependency.
The Tauri actor captures a manifest-order block receipt plus package/run
generation, performs decoding outside its mailbox, and accepts the immutable
result only while fingerprint, generations, ordinal, receipt, and compiled
sample rate still match. Its one-block/1,280 MiB cache returns exact sequential
hits without decoding, evicts a different block before another allocation,
and exposes only a `pcm-and-output-plan-cache`, `outputPlanPrepared = true`,
closed proposed route/event-count, `unqualified`, non-executable summary to the
bundled main window. The local no-argument gesture is absent from remote actions
and the companion page. No platform output backend or output arm is integrated
with this actor, so
real plans remain unarmable and unqualified. Before executable output,
potentially large final PCM/plan releases must move off the authority actor;
current invalidation can drop up to the bounded cache maximum there.
Legacy schedules without a metadata/CSV sample rate still need the V1
WAV-header fallback before this boundary may feed native execution.
The crate's pure `output` module now provides a device-free, non-serializable
playback plan, closed 2/3/4-channel PPS routes, a generation-fenced render
engine, caller-owned output/event buffers, 4,096-frame and 64-total-event
callback ceilings, sample-zero and final-frame-submitted records, pause cursor
freeze, tail zero-fill, and fail-closed callback faults. This is not a device
backend: a future executable adapter must connect the reservation owner and
perform prepare/reserve/arm, timestamp mapping, evidence draining, and
off-callback engine destruction.
Its Python differential probe remains CI-only while parity is being proven.

- Reservation-only native device adapter:
  `packages/pps-runner-audio-cpal/`. CPAL 0.18.2 is pinned with default
  features disabled. One named owner thread lazily owns Host/Device/Stream and
  exposes capped inventory, service-bound exact F32 selection, silence warm-up,
  status/fault, release, and shutdown through bounded native Rust queues. It
  has no Tauri, BRSP, filesystem, serde, Python, RunnerCore, experiment-media,
  arm, or executable-output dependency. Windows WASAPI, macOS CoreAudio
  (minimum macOS 14.2), and Linux ALSA are the compiled backends; hardware
  smoke/timing qualification and actor integration remain open. Selected
  channels are capped at four and callbacks/fixed buffers at 4,096 frames.

All desktop authority requests enter one bounded FIFO mailbox with capacity 64:
ordinary work is capped at 56 so eight slots remain available to local safety
operations. The actor owns deadman expiry and stale-owner/package/run generation
fencing; transport lifecycle threads do not own another semantic watchdog or
reducer. `remote.rs` separately owns finite socket read/write/close deadlines,
strict-before-deadline exact-payload Ping/Pong health, and independent
pre-upgrade permit pools (eight desktop, 32 relay), with the underlying socket
write buffer capped at 64 KiB. Accepted TCP sockets request `TCP_NODELAY`
before Axum handling; configuration failure is a saturating diagnostic only,
and no latency benefit is claimed without release A/B evidence. Inbound frames are deadline-fenced before
semantic work. Those transport frames cannot renew remote authority or enter
command diagnostics. Post-claim exits await exact-owner safety-reserve cleanup.
Desktop commands remain inline with no application queue; the laboratory relay
owns a fixed 32-message reliable queue, at most one writer-held frame, and one
replaceable latest-state slot. Per-route order stamps prevent cross-lane
overtake, while reliable overflow closes both ends, preempts pending output,
and fences later traffic. Post-registration write failure removes the exact
role/room slot. The closed PPS profile rejects `intent`; only target `state`
uses the replaceable lane.
Remote dedupe after lost acknowledgement/reclaim tests candidate current
revision, emits no duplicate evidence/run generation, and attaches the current
actor public projection to the cached outcome.
Only accepted dispatches that change semantic revision append to the scientific
ledger. Rejected commands and accepted no-ops do not consume that capacity.
Ordinary commits reserve evidence space for safety, and pause/revoke remains
fail-safe if evidence is exhausted while latching `evidence_unavailable`.
Native semantic request evidence now lives in
`apps/runner/src-tauri/src/latency_diagnostics.rs`: a 512-trace bounded,
local-only store with opaque internal trace IDs and aggregate schema
`pps-runner-native-latency-summary.v2`. It reports completed, dropped whole-
trace, dropped stage-update, interrupted, and unfinished counts plus per-route/
stage p50/p95/p99/worst integer microseconds from one process monotonic clock;
interrupted and unfinished traces do not populate route percentiles. Local
Tauri and WebView-VDO measurements stop at the Rust handler handoff; LAN command
measurements begin when Axum yields a text frame and may end only after the
reply socket send completes. Browser
`performance.now()`, SDK RTT, WebRTC, remote-host, and physical effect timing
are separate evidence domains. Adapter validation, remote authority
authorization, reducer validation, and an accepted reducer transition are
distinct milestones. The
accepted-transition milestone precedes ledger commit and effect initiation;
diagnostic contention drops evidence without blocking or mutating authority.
Each route also reports authority queue wait from admission/dequeue markers on
the same completed trace; missing marker pairs are omitted rather than inferred
from aggregate stage percentiles. A separate bounded atomic aggregate reports
ordinary and safety latest-observed depths, successful-admission depth
percentiles, high-water marks, and queue-full rejects. Counts saturate,
shutdown records both latest-observed depths as zero, and pressure observations
never participate in mailbox admission. The strict aggregate remains a
no-argument, bundled-main-window-only
diagnostic and contains no command IDs, arguments, errors, identities, paths,
or secrets.
No release-build or physical-route latency result is recorded yet. Verified
real V1 packages remain schedule-inspection-only and non-executable until
native audio/output and evidence boundaries are implemented and qualified.

Remote state uses `runtime.rs`'s exact `RemoteRunnerSnapshot` projection with
schema `pps-runner-public-snapshot.v1`, not the full operator
`RunnerSnapshot`. `remote.rs` may publish it only after an actor-linearized
exact-owner/generation/read-scope check. The desktop BRSP target keeps the
public snapshot separate from local UI state and disables autonomous cached
heartbeats, so package/config revocation makes old readers inert before later
state is serialized.

Android/phone execution is not a V1 Runner module. The earlier Python/Kotlin
phone source, bridges, tests, protocols, and CLIs remain under
`For-AI/experiments/android-companion/`. `companion_v1_disabled.py` provides
only safe disabled defaults required by the desktop product while those
experimental controls remain absent. The newer Quest candidate is isolated at
`apps/quest-runner/` as an optional application-context proof, not a primary
PPS Kit Runner module, and must not be confused with V1 support or timing
qualification.

## Shared Runtime and Resources

- Python import source:
  `packages/pps-runtime/src/peripersonal_space_toolkit/`.
- Stable import name: `peripersonal_space_toolkit`.
- Runtime path ownership: `runtime_paths.py` exposes `product_root()`,
  `resource_root()`, `designer_frontend_root()`, and `writable_root()`.
  `repo_root()` is a one-release compatibility alias; frozen applications honor
  `PPS_TOOLKIT_ROOT`.
- Approved application/resources source: `packages/pps-resources/assets/`.
- Immutable built-in profiles: `packages/pps-resources/study_templates/`.
- Product examples: `packages/pps-resources/configs/`.
- Deidentified public sample data: `packages/pps-resources/data/sample/`.
- Logical serialized/installed paths remain `assets/...`,
  `study_templates/...`, `configs/...`, and `data/sample/...`.
- Pinned product dependencies/licenses: `third_party/`.

Key scientific modules:

- design model, validation, profile serialization: `design.py`, `templates.py`,
  `profile_bundle.py`, `profile_recreation.py`
- stimulus generation/spatial rendering: `render_backend.py`, `spatial.py`,
  `loudness.py`, `audio_routing.py`
- trial/block scheduling: `trial_filmstrip.py`, `participant_orders.py`,
  `designer_segments/`
- decoding/analysis: `decoder.py`, `analysis.py`, `analysis_review.py`
- calibration and acquisition evidence: `tactile_calibration/`,
  `latency_validation.py`, `output_evidence.py`, `labrecorder_capture.py`

## Distribution

- Component schema/manifests: `distributions/manifests/`.
- Parameterized Go downloader source: `distributions/downloader/`.
- Scripts executed on an installed PC: `distributions/windows-support/`.
- Designer leaf component owns Designer-only files and depends on Shared.
- Runner leaf component owns Runner-only files and depends on Shared.
- Shared owns approved common files exactly once.
- Full composes Designer + Runner + one Shared and creates two shortcuts; no
  central hub is introduced.

Release assembly code and tests are internal:
`For-AI/engineering/release/` and `For-AI/engineering/tests/`.

## Website

- Tracked Pages inputs: `website/`, the canonical compiled Designer, and the
  allowlisted compiled Runner companion page/assets.
- Canonical domain source: `website/CNAME`.
- Pages assembly: `For-AI/engineering/automation/build_pages.mjs`.
- GitHub-required thin wrapper: `.github/workflows/pages.yml`.
- Assembly copies the exact Designer `compiled/` bytes, the exact Runner
  companion HTML plus `companion.js`, `qr-code.js`, `style.css`, and the pinned
  VDO.Ninja 1.5.5 SDK/license/notice files, and
  approved public catalogues into ignored `dist/pages/`, including root
  `CNAME`. The Tauri desktop entry is not a Pages asset.
- Preserve `/`, `/documentation`, `/download`, `/experiment-runner/`,
  `ppskit.qzz.io`, and the
  `georgefejer91.github.io/pps-kit/` fallback.

## Internal Engineering

- CI/Pages implementation: `For-AI/engineering/automation/`.
- Executable build/setup: `For-AI/engineering/build/`.
- Release assembly, inventories, protocols, audits:
  `For-AI/engineering/release/`.
- Generators/maintenance tools: `For-AI/engineering/tooling/`.
- Test suite: `For-AI/engineering/tests/`.
- Software/UI/audio/hardware validation:
  `For-AI/engineering/validation/`.
- Diagnostics/reference captures: `For-AI/engineering/diagnostics/`.
- Migration ledgers/allowlists: `For-AI/engineering/migration/`.

GitHub workflows must remain minimal wrappers because GitHub requires their
location. Their substantive logic belongs under `For-AI/engineering/automation/`.
The thin `.github/workflows/runner-next.yml` wrapper runs
`check_runner_next.ps1`: transport-neutral Rust crates, including the V1
prepared-session verifier, are checked on Windows, macOS, and Linux, while the
canonical browser companion is tested and compiled
on Node 22. The same workflow creates short-retention validation-only bundles:
unsigned Windows NSIS and Linux DEB artifacts plus an ad-hoc/not-notarized macOS
DMG, each with checksums and an explicit non-release notice and without updater
artifacts. These software gates do not constitute platform hardware/timing
qualification, production signing/notarization, an updater channel, or a
Python-free V2 release.

## Internal Research

- Literature audits, source networks, screening, evidence ledgers:
  `For-AI/research/literature/`.
- Broad citation-network source and builder:
  `For-AI/research/literature/publication-network/` and
  `For-AI/research/literature/tools/build_publication_network_asset.mjs`.
- Approved public projection copied into the Designer:
  `apps/designer/frontend/publication_network.v3.json`.
- Calibration exploration: `For-AI/research/calibration/`.
- BRM/manuscript work: `For-AI/research/publication/`.
- Woojer and other research-only hardware work: `For-AI/research/hardware/`.

Research screening and full evidence ledgers are not product preload assets.
Only the reduced approved catalogue, inventory, and recreation-status projection
remain under `packages/pps-resources/assets/preloads/`.

## Tests and Structural Enforcement

- `test_repository_structure.py`: root allowlist, tracked-path classification,
  component ownership, exclusion rules, and no `For-AI/` distribution entries.
- `test_package_inventory.py`: independent Shared/Designer/Runner/Full
  inventories and exact composition.
- `test_release_audit.py`: public/private boundary and stale product paths.
- Designer frontend tests plus Vite build validate the canonical compiled UI.
- Runner smoke/response-marker/Protocol 12 tests validate prepared packages and
  Segment 0-6 handoff without claiming participant or hardware evidence.
