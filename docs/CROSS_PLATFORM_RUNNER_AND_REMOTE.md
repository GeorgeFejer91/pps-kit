# Cross-platform Runner and Browser Remote Preview

PPS Kit now contains an incremental next-generation Runner preview. Its primary
path is a Tauri v2 desktop shell plus a no-install browser companion backed by
shared Rust contracts. A native Meta Quest tree is included only as an optional
experimental application context; PPS Kit does not require a headset runtime.
None of these previews replaces the validated Python/PySide Runner used for
current studies.

This is an architecture and software-qualification preview. It is not yet a
publication-qualified replacement for the existing Windows ASIO, LSL,
LabRecorder, wired-loopback, tactile-calibration, top-up, or analysis paths.

## Architecture

```text
browser controller ───┐
local desktop UI ─────┼─> BRSP/1 gateway ─> target authority ─> result + snapshot
optional Quest UI ────┘                            │
                                                  ├─ Rust/Tauri desktop reducer
                                                  ├─ strict browser JS phone reducer
                                                  └─ optional Rust/Kotlin/JNI Quest reducer

experiment packages/media ─> separate verified asset plane
audio/haptics/timing ───────> target-native scheduler and evidence plane
```

The target reducer is the authority. Network clients request named semantic
outcomes; they cannot call arbitrary Rust functions, Android intents, shell
commands, filesystem paths, URLs, DOM events, or synthetic input. Local and
remote controls enter through the same target-local command dispatcher. The
desktop and Quest targets share Rust contracts and reducer code; the browser
phone target implements the same closed contract in strict JavaScript because
a browser cannot load the native Rust crate without an explicit WebAssembly
build. Cross-language differential fixtures remain a promotion gate for that
JavaScript reducer.

The implementation is split into these boundaries:

- `packages/pps-contracts/`: closed action and scope enums plus strict,
  versioned wire and snapshot schemas.
- `packages/pps-brsp/`: transport-neutral BRSP/1 pairing proof, scope
  negotiation, safe epochs, and sequence guards.
- `packages/pps-runner-core/`: pure target-authoritative state reducer with no
  Tauri, Android, UI, filesystem, network, or audio dependency.
- `packages/pps-runner-execution/`: pure sample-schedule compiler, half-open
  cursor, and cumulatively bounded native event ledger. It has no Tauri,
  browser, network, or audio-device dependency.
- `apps/runner/`: Tauri desktop preview and the shared multi-page browser UI.
- `apps/quest-runner/`: native Kotlin/Meta Spatial SDK immersive shell with a
  Rust `cdylib` through JNI. Tauri is deliberately not the Quest renderer.

### RustDesk reference boundary

RustDesk is an architectural reference, not a PPS dependency or wire protocol.
The reviewed source is pinned at
[`03a7fc5992069cc5bc9f7c36b872483dddf4f472`](https://github.com/rustdesk/rustdesk/tree/03a7fc5992069cc5bc9f7c36b872483dddf4f472).
Useful patterns are its separation of rendezvous, direct/relayed connections,
per-session services, platform-specific input adapters, receipt timestamps,
timeouts, and stale-session cleanup. PPS applies those ideas to a much smaller
semantic-control surface: VDO/WebSocket remain transport adapters, one bounded
native authority owner serializes commands, and platform output adapters stay
behind Rust traits.

RustDesk's raw keyboard/mouse protocol is deliberately not adopted. A browser
cannot address every app function or inject generic input; it requests only
closed BRSP actions that `RunnerCore` authorizes. RustDesk also uses unbounded
channels in parts of its connection path, which are unsuitable for experiment
authority. PPS requires bounded queues, explicit queue-full failure, generation
fencing, target-local arming, expected revisions, and target-owned deadman
leases. RustDesk is AGPL-3.0, so no source is copied or vendored into the MIT PPS
Kit; only independently implemented architectural lessons and tests are used.
The current native LAN slice independently applies the bounded-lifecycle lesson:
each handshake read has a 12-second deadline, every WebSocket write has a
two-second deadline behind a 64 KiB maximum socket write buffer, graceful close
has a one-second deadline, and a
connection-local Ping every two seconds requires its exact eight-byte Pong
within three seconds. These are transport-health limits, not BRSP messages or
application-command samples, and they never renew the separate five-second
target-owned controller lease. No RustDesk code, schema, raw-input surface, or
AGPL implementation text was copied or translated.

## Semantic remote-control contract

The current closed action catalogue is:

| Action | Remote scope | Notes |
| --- | --- | --- |
| `system.snapshot` | `session.read` | Read bounded authoritative state. |
| `package.prepare_demo` | `session.prepare` | Deterministic preview package only. |
| `setup.submit` | `session.prepare` | Participant name is redacted unless local sharing is enabled. |
| `part.start` | `session.transport` | Requires target-local arming. |
| `instruction.continue` | `session.transport` | Requires the current opaque gate identifier. |
| `run.pause` / `run.resume` | `session.transport` | Reliable, revision-checked commands. |
| `run.stop` | `session.abort` | Separate high-impact grant. |
| `run.abort` | `session.abort` | Separate high-impact grant. |
| `session.note` | `session.annotate` | Bounded annotation. |
| `target.arm` / `target.disarm` | local only | Cannot be granted to a browser. |
| `run.complete_demo` | local only | Preview helper, not a remote operation. |

Each command body carries a command identifier, scope, explicit action,
arguments, and expected revision. Its canonical BRSP envelope carries the
session, sender identity, fresh unsigned 32-bit sender epoch, and per-lane
unsigned 32-bit sequence. The target checks the granted scope and current
precondition, deduplicates command-body retries even when they arrive in a
fresh envelope, applies the transition once, increments the semantic revision,
increments the preview's bounded audit-event counter for an accepted state
change, and returns an `applied` result plus authoritative state. Durable audit
records are still supplied by the validated V1 runner and remain a V2 migration
gate.

Pairing uses a fresh 32-byte invitation secret held only in the URL fragment,
24-byte nonces, complete canonical target/controller hello transcripts, and
mutual role-bound HMAC-SHA256 proof encoded as unpadded base64url. Capabilities
and scopes are the exact intersection independently checked by both peers.
Control records are bounded to 16 KiB and state records to 8 KiB. Control and
replaceable state have independent unsigned 32-bit half-range sequence spaces.
A five-second target-owned controller lease provides the deadman. Every valid,
fresh canonical controller control refreshes it; the browser controller sends a
canonical `snapshot-request` every two seconds while it holds `session.read`.
There is no private keepalive message. Silence from a half-open connection
expires the lease, revokes that exact controller/session owner, and pauses an
active desktop or browser demo. Snapshot requests, initial snapshots, live
state, and state heartbeats require negotiated `session.read`; command
acknowledgements remain available under their action scope without disclosing
the snapshot.

## Desktop preview

The desktop app uses Tauri v2 and a plain Vite/ES-module frontend. Tauri exposes
seven local/configuration/inspection commands plus four remote-session commands: claim,
renew, dispatch, and revoke. Those four commands are restricted to the bundled
`main` WebView and preserve remote origin, negotiated scopes, the exact owner
token, canonical control sequence, and the native five-second watchdog. VDO
commands never enter the local dispatch path. Its capability grants only Tauri
core defaults and these exact commands; it has no shell, process, filesystem,
HTTP, opener, or updater plugin. The privileged WebView loads bundled assets.
For a WebView-carried VDO session, negotiated `session.read` alone is not enough
to publish desktop state: initial snapshot/state remain suppressed until the
native claim succeeds, every requested snapshot awaits a fresh native renewal,
and publication stops when the native controller ID/deadline no longer matches.

Desktop authority is now serialized by one named native actor thread,
`pps-runner-authority`. It is the sole owner of `RunnerCore`, remote owner and
policy state, the retained verified package and compiled schedule-only plan,
package/run/owner generations, and the bounded `EventLedger`. Async Tauri, LAN,
and WebView/BRSP entrypoints are adapters into its bounded FIFO mailbox; they do
not lock or mutate an independent reducer. The mailbox admits at most 64 queued
requests, limits ordinary work to 56, and reserves the remaining eight slots
for local safety operations. The actor checks the target-owned deadman while
waiting and before dequeuing work, and generation-fences stale run, package, and
remote-owner work.

Only accepted actions that change the semantic revision append a scientific
ledger record. Rejected commands and accepted no-ops retain reducer
dedupe/stamp behavior without consuming that ledger. Ordinary transitions
reserve evidence capacity for safety; if even the safety reserve is exhausted,
pause/revoke still applies fail-safe and latches the native
`evidence_unavailable` condition. Native semantic-request diagnostics now use
a separate 512-trace bounded store with schema
`pps-runner-native-latency-summary.v1`. The no-argument summary is available
only to the bundled `main` window and returns aggregate counts,
dropped whole-trace, dropped stage-update, interrupted, and unfinished counts,
and per-route/per-stage p50, p95, p99, and worst integer microseconds;
individual traces never cross IPC. Evicted traces and traces that could not be
started because the store was contended count as dropped whole traces. A stage
or terminal update lost to contention counts separately as a dropped stage
update. Interrupted and unfinished traces are reported separately and excluded
from route populations and percentile samples. Routes are the closed
`local-tauri`, `lan-websocket`, `webview-vdo`, and `unknown` set. The stages
separate adapter validation, authority admission/dequeue, remote owner/
sequence/scope authorization, and reducer validation. Local routes have no
remote-authorization sample. `reducer-applied` is emitted only from an accepted
reducer transition milestone, never for dedupe, stale revision, invalid
arguments, or an application rejection. This milestone means the candidate
transition was accepted by the reducer; it precedes authoritative ledger commit
and effect initiation and is not evidence of either. Authority-path
instrumentation uses a non-blocking diagnostics lock, so contention loses and
counts the observation instead of delaying or changing a transition.
For remote routes, `reply-ready` follows conversion to the sanitized public
`RemoteApplied` acknowledgement (or bounded generic error), not merely the
inner native reducer result.

Every reported stage is cumulative from native ingress in one process
monotonic clock. For LAN commands, ingress is captured immediately after Axum
yields the complete text frame, while `send-completed` is recorded only after
the corresponding socket `send(...).await` succeeds. This excludes browser,
radio, kernel-to-client delivery, and controller rendering. For local Tauri
commands and WebView-carried VDO commands, ingress begins at the Rust handler
entry after Tauri has deserialized the request and ends at the handler's adapter
handoff; it excludes the originating click, WebView IPC serialization before
the handler, return delivery/rendering, VDO/WebRTC, and remote-host time. Those
browser `performance.now()` and SDK/route RTT measurements remain separate
clock-domain evidence and must never be subtracted from native timestamps.
No release-build or physical-route latency result has yet been recorded, so
this instrumentation is not a low-latency or real-time claim.

The full operator `RunnerSnapshot` is not a remote wire object. Every native
LAN or bundled-WebView remote receipt and publication uses the distinct exact
`pps-runner-public-snapshot.v1` projection. It retains target revision, phase,
part/block progress, allowed actions, readiness, and lease deadline, while
omitting participant/session identifiers, demographics and sharing flags,
package labels, free-form notes, controller identifiers, audit records, pairing
material, paths, and native verification receipts. The desktop WebView keeps
that public projection separate from its full local display state. Native-backed
BRSP targets do not emit an autonomous cached heartbeat: each requested read is
checked against the exact actor-owned controller generation without renewing
the native lease, and command/renewal results carry a freshly projected state.

The sixth local command selects a real `pps-run-session.v1` manifest. It takes
no path argument: the bundled main window asks Rust to open the native operating
system file chooser, and `packages/pps-session-package/` verifies the chosen
manifest and its ordered block assets. For `participant_block_wavs`, it also
checks the recorded Segment 6 hash, source-block CSV provenance and row counts,
and source-trial WAV hashes using the V1 Python Runner's first-failure order.
Resolved paths and digests remain in a non-serializable Rust receipt; the
WebView receives only a path-free identity/block summary. Adopting a package
disarms the target, clears any controller owner, and rotates pairing authority.
The native picker/verifier is single-flight even when the WebView invokes its
command concurrently. Once a real plan is retained, the demo-preparation
action is removed and rejected so native receipt and reducer identity cannot
diverge. Unambiguous foreign-host absolute path syntax fails closed instead of
being joined as a relative path. V1 has no source-host marker, so ambiguous
rooted spellings retain native Python behavior; reliable relocation requires a
future versioned format.
The retained receipt must be reverified at the future execution boundary to
close the filesystem time-of-check/use gap.

The native **Compile Rust schedule inspection** operation already performs that
reverification and compiles the retained block CSVs in manifest order. It
matches curated Python oracle fixtures for event order, explicit-sample versus
seconds precedence, ties-to-even conversion, signed derived samples, and
half-open buffer consumption. The native receipt binds every prepared CSV
digest, and compilation hashes and parses the same bounded byte snapshot, so a
file replacement between reverification and parsing fails closed. The package
manifest, block count, known strings/paths, metadata shape, and cumulative
metadata are bounded before retention. Per-block and package-wide schedules plus the
append-only native ledger have cumulative encoded-byte budgets; exceeding a
bound fails closed. Raw V1 event payloads can contain native paths and never
cross Tauri IPC. The WebView receives only path-free counts and block summaries
explicitly marked `schedule-only`, `unqualified`, and `executable = false`.
This proves compatibility and resource bounds, not playback, response timing,
or scientific execution readiness. Legacy schedules that omit sample rate from
both block metadata and CSV still require the V1 WAV-header fallback before
they can enter native execution. The package verifier now
streams and hash-binds each prepared WAV into a native-only receipt, with a
768 MiB per-file and 8 GiB per-package encoded-byte ceiling. The pure
`pps-runner-audio` crate can then reopen one exact receipt, hash every byte
(including trailing chunks), and decode only PCM16 legacy two-channel
`[tactile, audio]` or canonical three-channel `[left, right, tactile]` data
without resampling. It publishes decoded media only after byte-count and digest
agreement. The bundled main window can then explicitly prepare the first block
through a no-argument native command. Decoding runs on a blocking worker, while
the single authority actor alone captures and rechecks the exact package/run
generation, manifest fingerprint, manifest-order block ordinal, verified WAV
receipt, and compiled-schedule sample rate before replacing its one-block PCM
cache. An exact sequential request returns the existing path-free summary
without decoding again; a different block evicts the prior cache before the
worker can allocate another buffer. The cache is capped at 1,280 MiB, active
run phases deny new preparation, and package/schedule/run replacement makes a
late result inert. The retained candidate now binds both PCM and a
renderer-neutral playback plan: the path-free summary reports
`pcm-and-output-plan-cache`, `outputPlanPrepared = true`, one closed proposed
route, and its scheduled event count. This remains `unqualified` and
non-executable: no platform output device is opened, no remote action or output
arm is added, and real packages remain unarmable. Before this cache can feed
executable output, potentially large final PCM/plan releases must be retired
away from the authority actor; ordinary preflight invalidation may currently
drop up to the bounded cache maximum on that actor.

The device-independent `pps-runner-audio::output` core is the next native
boundary. It accepts only immutable prepared PCM, a full package/run fence, a
closed PPS route, bounded gains, and compact sample-index events. The legacy
source layout `[tactile, audio]` maps to physical `[audio, tactile]`; canonical
three-channel data maps `[left, right, tactile]`, with an explicit four-channel
tactile-mirror variant. Duplicate or ambiguous outputs fail closed. Rendering
uses caller-owned buffers and event slots, advances one `u64` source cursor,
freezes it while paused, zero-fills callback tails, and makes stale controls
inert. Preparation rejects more than 62 metadata events in any accepted
4,096-frame callback window; together with engine-owned `SampleZero` and
`FinalFrameSubmitted`, this caps one callback at 64 event records. Overflow,
an oversized/malformed callback, or an internal invariant fault silences the
entire current buffer and latches a fault. `FinalFrameSubmitted` means only
that the last source frame entered a software callback buffer—not device drain,
DAC onset, physical audio arrival, or tactile onset. No platform stream or
scientific timing qualification exists yet, and a future output owner must
retire/drop the heap-backed engine away from the real-time callback thread.

Local-only startup does not bind a LAN socket. The first explicit **Enable
phone remote** action reserves `0.0.0.0` and launches the companion server; a
bind failure is returned to the UI and cannot crash startup or trigger a
pre-consent firewall prompt. Disable and pairing rotation invalidate controller
authority. Connection cleanup carries a session-local owner token, so an old
socket cannot clear, pause, or relabel a newer session or overwrite the
disabled `local_only` state. After that first opt-in, the process reuses its
listener across disable/re-enable; while disabled, WebSocket/relay ingress stays
fail-closed, and app exit releases the listener.

After mutual BRSP ready, native LAN Ping/Pong only detects a half-open or
nonresponsive socket. Only the exact payload received strictly before its
deadline clears the pending Pong; every desktop/relay inbound frame passes the
same deadline gate before any command dispatch or forwarding, so a ready frame
at or after expiry is inert. A missing Pong closes the socket and revokes only
that socket's generation-fenced owner; the authority actor independently
enforces the five-second semantic deadman and pauses active output. Every
post-claim exit awaits that exact-owner revoke through the actor's reserved
local-safety admission class; guard Drop and the deadman remain cancellation/
crash fallbacks. Socket write failure cannot roll back a command that the
reducer already applied: the connection is closed/revoked and an identical
retry relies on the existing command-ID dedupe result. Dedupe mutation checks
use the candidate's current revision, so a cached Applied after revoke/reclaim
cannot append evidence or advance run/output generations again. The cached
outcome retains its original result revision, while WebView publication is
rebased onto the actor's current public projection so browser state cannot
regress. `send-completed` latency evidence is still recorded only after the
native socket send succeeds. Desktop control remains inline and
one-command-at-a-time, so this hardening adds no hidden command queue.

The separate **Advertise this runner** website-beacon action enables the same
Rust authority without starting the LAN listener. Its private VDO session is
carried by the bundled WebView, while claim/renew/dispatch/revoke remain native;
stopping that beacon revokes its exact owner and returns the authority to the
disabled/local state when the beacon flow enabled it. This avoids an unrelated
`0.0.0.0` bind or firewall prompt for a website-only route.

From the repository root:

```powershell
npm --prefix apps/runner ci
npm --prefix apps/runner run check
cargo test --workspace --all-targets --locked
npm --prefix apps/runner run tauri build -- --debug --no-bundle
```

The desktop UI retains the existing Runner's visual palette and high-level
Experiment Control, Data Logging, and Phone Remote hierarchy. It can inspect
and adopt a genuine verified V1 prepared plan, but that plan is intentionally
not armable yet: only the deterministic compatibility demo has an execution
adapter. The validated Python scheduler and acquisition stack remain the
production Runner until their behavior has been ported behind supervised
adapters and qualified.

CI also produces one host-native packaging-validation artifact per desktop
platform: an unsigned Windows NSIS installer, an ad-hoc/not-notarized macOS DMG,
and an unsigned Linux DEB. They carry explicit validation-only notices and
checksums, generate no updater payload, and are retained only briefly as CI
artifacts. They prove current host packaging mechanics only; they are not signed
production releases, updater channels, or data-collection-qualified installers.

## Browser companion

The same frontend build emits `compiled/companion/index.html` and local bundled
assets, including reviewed, hash-pinned VDO.Ninja 1.5.5 SDK bytes and their MPL
notice. No runtime CDN is required. Loading the page constructs no SDK client
and opens no network connection: a visitor must explicitly press **Browse
public targets**, **Start public beacon**, or connect a private invitation.
Because GitHub Pages cannot set a response-level `frame-ancestors` policy, the
companion also fails closed at startup when it detects an embedded frame: it
strips invitation material, binds no controls or networking, disables every
form control, and asks the visitor to open the page directly. A deployment with
owned response headers should additionally send
`Content-Security-Policy: frame-ancestors 'none'`.

The canonical public copy is
`https://ppskit.qzz.io/experiment-runner/`, with
`https://georgefejer91.github.io/pps-kit/experiment-runner/` as the project-Pages
fallback. Pages assembly copies the compiled companion HTML, browser-only
assets, and pinned VDO.Ninja vendor files byte-for-byte; it does not publish
the Tauri desktop entry or native capabilities.

The browser has two modes:

1. **Controller** authenticates to a desktop, phone, or Quest target and sends
   only actions within the granted scopes.
2. **Phone Experiment** is a browser-owned exploratory target. A local gesture
   arms Web Audio and vibration, another browser may control its semantic run
   state, local participant taps are timestamped into a bounded event log, and
   that JSON log can be downloaded.

Browser audio and vibration are subject to foreground, user-activation,
visibility, device, and operating-system scheduling rules. Phone Experiment
mode is therefore labelled exploratory and must not be treated as physical
onset or publication-grade timing evidence without device-specific measurement.

The hosted page carries a fixed public VDO.Ninja data-only rendezvous namespace.
Any visitor may explicitly browse sanitized, unverified target labels and send
a bounded pairing request. Listings and requests are limited to 2 KiB and never
contain participant state or runner commands. A target must approve locally.
Only after that approval does a `pps.beacon/1` acceptance record deliver a fresh
private VDO room and 32-byte secret to the exact requester-bound WebRTC data
channel. That channel is SCTP/DTLS encrypted and is not broadcast to other room
peers, but the handoff is not durable identity: it trusts VDO.Ninja signaling
and the operator's selection of the unverified requester. The controller still
presses **Connect** and completes mutual BRSP proof and scope negotiation before
any control. Stronger hostile-signaling resistance requires an out-of-band QR
or independently verified key fingerprint; the manual invitation remains the
fallback for that policy.

The private VDO transport uses one reliable ordered BRSP control channel and
one replaceable state channel, with bounded pre-open buffering because either
data channel may arrive first. Automated tests exercise browser-to-browser and
browser-to-Tauri contract flows. Physical phone/browser routes, background and
sleep behavior, direct-versus-relayed ICE paths, and real network partitions
remain attended qualification gates.

Each PPS browser controller admits at most one unacknowledged reliable command.
Additional button presses fail locally before command-ID creation or transport
send, and controller buttons remain disabled until `applied` or a terminal
session recovery. A non-terminal BRSP diagnostic does not reopen the slot, so
a late acknowledgement cannot overlap a second mutation.

The included LAN relay remains a cleartext laboratory/offline adapter. Desktop
and relay upgrades have separate pre-upgrade admission budgets (eight desktop,
32 relay), return HTTP 503 when full, and retain the permit through the bounded
close attempt, so invalid or stalled relay traffic cannot create unlimited
tasks or consume desktop capacity. The relay's reliable direction retains its
fixed 32-message `try_send` queue plus at most one writer-held frame, while its
state direction retains one replaceable `watch` slot. Per-route order stamps
make the single writer send an earlier reliable Ready/Applied before a later
state without letting newer reliable traffic starve that state. Reliable queue
overflow is fail-closed: both endpoints are signaled and the forwarding fence
makes every later frame inert rather than dropping one command and allowing an
overtake. Fatal shutdown is observed before queued/pending output, and every
post-registration diagnostic write failure enters the same exact-connection
slot cleanup, so an initial or later failed writer cannot retain a room role.
The PPS relay profile accepts no `intent`; only target `state` occupies the
replaceable lane, while commands and all other control stay reliable. All relay
socket writes/closes and its transport Ping/Pong use the same finite deadlines
and 64 KiB write-buffer ceiling. This
does not make the relay authenticated, encrypted, production-ready, or command
authority. The
public VDO route depends on VDO.Ninja Internet signaling and external ICE/TURN;
it is not an offline same-Wi-Fi guarantee, an owned rendezvous service, or an
availability SLA. WebRTC signaling/ICE can expose ordinary connection and IP
metadata to the service and selected peer. Approved pairing credentials cross
only the selected encrypted peer channel, while PPS application records stay
on the fresh private data channels. GitHub Pages hosts the permanent static
beacon interface and pinned client bytes, not a WebSocket server and not
command authority.

## Optional Meta Quest application context

`apps/quest-runner/` is an experimental native Meta Spatial SDK Android
application, separate from the primary desktop/browser Runner. Its
`AppSystemActivity` owns the immersive lifecycle and panel; Kotlin owns Android
and Spatial SDK APIs; Rust owns semantic authorization, transitions, and
snapshots. JNI exchanges bounded commands and snapshots rather than per-frame
or per-audio-sample traffic.

Build on a configured Windows host with JDK 17, Android API 34, NDK
`27.0.12077973`, and the Rust `aarch64-linux-android` target:

```powershell
cd apps/quest-runner
.\gradlew.bat testDebugUnitTest assembleDebug
```

The APK is ARM64-only. Cleartext traffic is disabled in the normal manifest;
the app requests only Internet and network-state permissions. The preview has
no camera, microphone, storage, location, or broad device-control permission.
See `apps/quest-runner/README.md` for the pinned Spatial SDK toolchain and exact
remote-preview limitations.

The optional Quest preview enables its canonical BRSP/1 target at build time,
but networking remains opt-in in the headset UI. Rust/JNI rechecks proof,
scopes, remote origin, epoch/sequence/revision, deduplication, read privacy,
local arm, and the target-owned deadman before applying a command. Kotlin owns
only relay lifecycle/framing and bounded UI refresh. Debug builds may use an
explicit cleartext laboratory WebSocket relay; release configuration requires
WSS and keeps cleartext disabled. The repository does not bundle a trusted WSS
relay, and the path has not yet been exercised on a physical headset or phone,
so it remains an experimental application context rather than a qualified PPS
Runner platform.

## Release and migration policy

The existing PyInstaller Runner and V1 component manifests remain unchanged
during migration.
A Tauri shell by itself does not make the installation small while it still
ships the Python/PySide compatibility engine. The current Go bootstrapper is
already lightweight; the substantial size reduction comes only as validated
Python functionality is replaced or moved behind optional compatibility
components. The V2 release is unconditionally Python-free. Python may remain
only in development and CI as a golden/differential oracle while Rust parity is
proved; it must not ship as a worker, sidecar, fallback authority, runtime
dependency, PySide/PyInstaller payload, or control/timing path.

The migration order is:

1. Freeze versioned contracts and differential fixtures against the Python
   Runner.
2. Port package verification and the session state machine. V1 prepared-package
   verification/adoption and non-executable schedule inspection are now native;
   one bounded native authority actor now owns the reducer, package/compiled
   plan, controller, generations, and bounded ledger.
   Before promotion, add early manifest/allocation bounds, legacy `~` path
   differential fixtures, summary recovery after WebView reload, and a v2
   content-addressed prepared-asset contract.
3. Extend that landed bounded native authority owner into the deadline-sensitive
   experiment engine for instruction/start/pause/resume/stop effects. Keep
   network I/O async and keep timed effects out of the WebView and unbounded
   Tauri/Tokio queues.
4. Port target-native audio/output routing, response timestamping, tactile, and
   acquisition boundaries, then qualify them with physical timing evidence.
   Native bounded WAV receipts, a pure content-bound PCM16 decoder, and a
   generation/receipt-fenced one-block actor cache have landed; persistent
   platform output streams, callback scheduling/routing, response ingress, and
   physical qualification remain.
5. Port durable event/LSL evidence, artifact writers, persistence/recovery, and
   the normal post-run review/analysis required by the Runner, using golden
   outputs only as temporary Python-oracle evidence.
6. Extend the landed native semantic-request diagnostics through effect
   initiation once the output owner exists, then qualify it in release builds.
   Current native observations cover adapter ingress/authorization, authority
   admission/dequeue, reducer validation, accepted reducer transition, reply
   readiness, adapter handoff, and—only for LAN WebSocket commands—successful
   socket send completion. Browser performance and SDK RTT remain separate
   clock domains. Report p50, p95, p99, and worst observed independently; Rust
   alone is not latency evidence.
7. Qualify each Windows, macOS, Linux, phone, and Quest hardware route before
   making scientific timing claims.
8. Pass the Python-free Windows gate on a clean installation: adopt and run a
   representative real package, emit required artifacts/evidence, support
   local and browser control, shut down/recover, and complete normal review
   without Python, PySide, PyInstaller, or a Python worker. Then remove the V1
   compatibility packaging from the shipped Runner.
9. Add host-native signed installers, updater manifests, rollback policy, and
   platform-specific release inventory before promoting the preview to V2.

`RunnerCore` remains the native BRSP application-target authority. Local Tauri
and authenticated remote commands must converge on its typed transition path
after origin-specific authorization. VDO/WebSocket/BRSP layers remain adapters,
`RemoteRunnerSnapshot` remains the explicit public projection, and package replacement
must disarm, revoke/rotate authority, and make late owners inert. The PPS
profile is command-only; do not add a latest-intent lane without a genuine
complete-current-value control. A JavaScript application-target reference may
be used as a conformance checklist, but it must not be copied into Tauri or
become a second reducer. Record its revision only after the reference changes
are committed.

Compilation is not timing parity. macOS CoreAudio, Linux PipeWire/JACK/ALSA,
Quest audio/controller haptics, and browser phone scheduling each require their
own physical loopback/onset evidence. Remote participant responses must also
retain sender time, target receipt/acceptance time, clock-sync uncertainty,
transport, and command identity; they must never be silently mixed with local
mouse reaction times.
