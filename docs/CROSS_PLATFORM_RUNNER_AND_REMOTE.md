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
- `apps/runner/`: Tauri desktop preview and the shared multi-page browser UI.
- `apps/quest-runner/`: native Kotlin/Meta Spatial SDK immersive shell with a
  Rust `cdylib` through JNI. Tauri is deliberately not the Quest renderer.

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
six local/configuration commands plus four remote-session commands: claim,
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

Local-only startup does not bind a LAN socket. The first explicit **Enable
phone remote** action reserves `0.0.0.0` and launches the companion server; a
bind failure is returned to the UI and cannot crash startup or trigger a
pre-consent firewall prompt. Disable and pairing rotation invalidate controller
authority. Connection cleanup carries a session-local owner token, so an old
socket cannot clear, pause, or relabel a newer session or overwrite the
disabled `local_only` state. After that first opt-in, the process reuses its
listener across disable/re-enable; while disabled, WebSocket/relay ingress stays
fail-closed, and app exit releases the listener.

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

The included LAN relay remains a cleartext laboratory/offline adapter. The
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

The existing PyInstaller Runner and V1 component manifests remain unchanged.
A Tauri shell by itself does not make the installation small while it still
ships the Python/PySide compatibility engine. The current Go bootstrapper is
already lightweight; the substantial size reduction comes only as validated
Python functionality is replaced or moved behind optional compatibility
components. The intended V2 end state is a Python-free default Runner; Python
is retained during migration as the behavioral/scientific oracle and may exist
temporarily as an optional supervised compatibility worker, not as the final
authority.

The migration order is:

1. Freeze versioned contracts and differential fixtures against the Python
   Runner.
2. Port package verification and the session state machine. V1 prepared-package
   verification/adoption is now native; execution scheduling is still open.
   Before promotion, add early manifest/allocation bounds, legacy `~` path
   differential fixtures, summary recovery after WebView reload, and a v2
   content-addressed prepared-asset contract.
3. Add a bounded supervised compatibility worker for still-Python behavior.
4. Port logging and artifact writers with golden-output comparison.
5. Port target-native audio, response, tactile, and acquisition backends.
6. Qualify each Windows, macOS, Linux, phone, and Quest hardware route before
   making scientific timing claims.
7. Add host-native signed installers, updater manifests, rollback policy, and
   platform-specific release inventory before promoting the preview to V2.

Compilation is not timing parity. macOS CoreAudio, Linux PipeWire/JACK/ALSA,
Quest audio/controller haptics, and browser phone scheduling each require their
own physical loopback/onset evidence. Remote participant responses must also
retain sender time, target receipt/acceptance time, clock-sync uncertainty,
transport, and command identity; they must never be silently mixed with local
mouse reaction times.
