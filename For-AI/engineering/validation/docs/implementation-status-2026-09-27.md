# Approved implementation status

Reviewed 2026-11-06. Historical source evidence below remains revision-scoped.
Current evidence for the 17 approved
[audit items](unification-and-critical-audit-2026-09-27.md).
Each status applies to its stated surface, not to the whole product.

| Item | Implemented / observed surface | Remaining gate |
| --- | --- | --- |
| 1 | VERIFIED: locked Core/Desktop fmt, Clippy and tests on three CI platforms | Retain these checks through further execution work |
| 2 | PARTIAL: refreshed editable setup, complete initial run and focused repairs/rechecks | Five evidence checks still fail; guarded Standard retry stopped on low disk |
| 3 | PARTIAL: one compact source/package/capability record; conservative readiness | Complete native adapter and measured evidence |
| 4 | VERIFIED: shared profile/limits/scoring/text/job owners; concise For-AI routing; one native actor/scheduler/file worker | Extract only seams changed by further work |
| 5 | VERIFIED browser source: planner disclosures/JSON action, phone Pair/state/action flow, participant response, local output picker and inline notifications | Installed UI inspection |
| 6 | PARTIAL: actual Pretext, explicit no-fit, complete labels, keyboard input, narrow/enlarged text and spacing | Actual WebViews and full accessibility qualification |
| 7 | PARTIAL: frozen approved Segment 5/6 CSV plan, inventory hashes, review revision/lineage fences | Full scheduling UI and native profile assembly |
| 8 | VERIFIED: plan/resource preflight, source/cancel/publication fences, shared job completion and rollback | Qualify additional generation routes if selected |
| 9 | PARTIAL: exact CPAL port, local output preflight, callback-confirmed controls, local input, shared V1 scoring/CSV and receipt-gated result publication | Activation, full-profile execution and an installed experiment; candidate remains non-executable |
| 10 | PARTIAL: shared Rust/browser contracts; JSON to existing compatibility assembler; sample/tactile/response/CSV oracle checks | Native JSON assembly and complete execution capability |
| 11 | PARTIAL: authenticated local/phone commands use one dispatch/control owner, shared scope fixture and fresh-state gate | Complete real-package execution |
| 12 | PARTIAL: retry/input fences, durable intent versus callback confirmation, bounded deadlines, per-run journal and exclusive hashed result publication | Installed filesystems, recovery and complete execution |
| 13 | PARTIAL: secure hosted companion, inert discovery, existing authenticated VDO route | Physical phone direct/relay/network-loss qualification |
| 14 | PARTIAL: suspension/resume, no replay, stale-state denial, disarmed phone outputs and pending-activation cancellation | Physical Safari/Chrome lock and BFCache cases |
| 15 | VERIFIED source policy: local setup, observer scope, participant-free public projection and fresh invitations | Physical expiry/revocation; remembered phones remain unselected |
| 16 | VERIFIED locally: both Vite 6.4.5/source-map-js 1.2.2 locks, clean installs/builds and zero-advisory audits | Retain locked byte checks and matching CI |
| 17 | PARTIAL: exact-revision CI validation packages; source/Pages checks | Installed packages, measured output/response/calibration and supported routes |

## Local validation on 2026-11-06

Source fixes were pushed on `main`: `ba088bb9` (LF browser inputs), `3baff2dd`
(immediate accepted-block regeneration denial, with the worker guard retained),
`e2676481` (portable CSS/guidance/path/SVG validation) and `0208ca0d` (two targeted
frontend dependency patches). The latter changes only Vite 6.4.3 → 6.4.5 and
source-map-js 1.2.1 → 1.2.2; unrelated dependency versions/platform metadata and
the locked Pretext dependency were preserved. The corresponding advisories are
[Vite/launch-editor](https://github.com/advisories/GHSA-587h-7wmj-h5pm) and
[source-map-js](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).

| Gate | Observed evidence / result |
| --- | --- |
| Quick | VERIFIED: compilation, 345 JSON parses, release/privacy audit, 30 tests and whitespace checks |
| Native Core | VERIFIED locally on Rust 1.88: locked fmt/check/Clippy and 127 tests/doctests; debug symbols/incremental builds disabled to limit scratch |
| Python/native parity | VERIFIED: all three response, prepared-package and timing differential tests passed on Rust 1.88 |
| Focused runtime | VERIFIED: 55 session/diary/response checks, two block regressions, eight job/resource checks, two prepared-profile/loopback software smokes, one profile-local package regression |
| Frontends | VERIFIED: clean locked npm installs, Designer build, Runner build/65 tests, 21 contract checks, both npm audits at zero advisories |
| Browser/Pages | VERIFIED: 12 Designer, six participant, six output and 15 text/lifecycle rendered cases; inspected representative screenshots; two Pages assembly tests and canonical compiled-byte parity |
| Downloader | VERIFIED: `go test ./...` on checksum-verified Go 1.22.12 |
| Public parity | VERIFIED after the `0208ca0d` deployment: 470 files byte-identical; `/`, `/documentation`, `/download`, `/experiment-runner/` returned 200 |
| Full Standard | NON-GREEN/BLOCKED: initial full result 573 passed, 19 failed, 37 setup errors, 10 skipped; a fresh guarded retry stopped below 192 MiB free |
| Local Desktop/install/physical gates | NOT RUN: insufficient working storage for the remaining build/install matrix; no installed-path, phone or physical-route qualification performed |

Fourteen initial failures and all 37 setup errors passed owning rechecks. CSS
checks now accept equivalent minified media-query whitespace without dropping
declaration checks; in-memory removal of action hiding or reduced motion still
fails. The profile-local regression now checks the actual file through the
existing extended-path conversion: a 264-character Windows path existed while
unprefixed `Path.exists()` returned false. The generation regression now returns
HTTP 400 before queuing accepted blocks and retains the existing worker recheck.

Five unchanged evidence checks reproduce independently of disk exhaustion:

- `test_manual_reviews_are_schema_valid_and_source_pointer_only`: the Canzoneri
  tool-use review has an undeclared confidence label/field status and four review
  attempts against the required five.
- `test_publication_network_asset_has_the_exact_decision_landscape_scope`:
  the committed catalogue status disagrees with its current coverage input.
- `test_publication_network_generator_rebuild_is_byte_deterministic`:
  the generator's expected runnable count is 15; current inputs derive 16.
- `test_builder_reports_authoritative_counts`: structured orientation reviews
  derive 8 against an expected 7.
- `test_orientation_and_visualization_reviews_remain_unconfounded`: combined
  orientation rows derive 10 against an expected 8.

These require reconciliation in the owning scientific records/derived catalogue;
this validation checkpoint does not change the evidence or relax those checks.
Focused successes cannot be added together to claim a complete Standard pass.
The first run reached zero free disk; generated-cache compression and normal
test cleanup recovered space. Start a further complete run with the documented
approximately 15 GiB allowance. Logs, JSON findings, screenshots and temporary
tools remain under ignored `artifacts/validation-2026-11-06*`; a test-generated
115-line-offset schema refresh was restored rather than promoted as a source edit.

The backend [CI run](https://github.com/GeorgeFejer91/pps-kit/actions/runs/42272027608)
for `3baff2dd` passed Core, Desktop and Python/Rust oracle jobs on Windows,
macOS and Linux, plus Browser and optional Quest jobs. Validation bundles and
newer dependency-checkpoint CI retain their separately observed states at handoff.
The [dependency-checkpoint CI](https://github.com/GeorgeFejer91/pps-kit/actions/runs/42274159186)
was still in progress at this record: its Browser, all three Core and macOS
Desktop jobs had passed; Windows/Linux Desktop and downstream jobs were pending.
Its [Pages deployment](https://github.com/GeorgeFejer91/pps-kit/actions/runs/42274159124)
completed successfully, followed by the passing 470-file public audit.
The newer frontend tooling rebuild produced identical canonical compiled bytes.
None of these checks establishes installed operation, physical timing or a
published behavioral effect.

## Historical source evidence

- Native control/input product source: `43566f52cdb2835ce629b18da8fe5da592a3e2af`.
  [Validation run](https://github.com/GeorgeFejer91/pps-kit/actions/runs/36351078594)
  passes all 14 source/oracle/browser/optional-Quest/validation-package jobs, including Core and
  Desktop checks on Windows, macOS and Linux: 23 shared-core and 140 desktop
  tests per host. The three validation installers were built, not installed here.
  Documentation-only synchronization does not change these product bytes.
- Output-setup UI source: `97d69fd448b2a3bb92331f3a377e84a54bd006b9`.
  [Its exact-source CI](https://github.com/GeorgeFejer91/pps-kit/actions/runs/36353428304)
  has completed: all 14 source/oracle/browser/optional-Quest/validation-package
  jobs passed (GitHub job statuses checked 2026-10-27). The three validation
  installers were built, not installed here.
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
  succeeded; the 2026-09-27 parity check passed all 470 files and four main routes.
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
files, event/CSV projection and substituted or malformed evidence. First closure
covers a whole single-block package, closed response windows and an elapsed final
software submission estimate. Interrupted/missing trials cannot complete.

Unsupported hard-link filesystems fail closed. Partial/pending/orphan files remain;
no final data are overwritten or automatically removed. Power-loss recovery,
directory durability, device drain and physical onset require separate evidence.
Callback observations, sample positions and CPAL driver predictions are explicitly
unqualified. Preparation does not enable execution or qualify a device route.
Native activation, whole profiles/multiple blocks, complete local validation,
installed inspection and calibrated physical acquisition remain outstanding.
The storage shortage returned on 2026-11-06. The latest local run and remaining
gates are recorded above; the 2026-10-27 free-space observation is historical.

No installed application change, participant acquisition, scientific replication,
physical onset or newly qualified route is claimed by this record.
