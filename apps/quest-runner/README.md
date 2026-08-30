# Optional Experimental PPS Quest Runner Preview

This directory is an optional, experimental native Meta Quest preview. It is a
separate application context and is not the primary PPS Kit product path; the
desktop/browser Runner remains primary. Nothing here changes or qualifies the
existing V1 experiment manifests, packages, or scientific workflow.

The immersive
`QuestRunnerActivity` owns the Meta Spatial SDK lifecycle and renders a Compose
control panel in 3D space. A small Kotlin boundary calls an in-process Rust
`cdylib` through JNI for seven local semantic operations:

- `request_snapshot`
- `start_demo`
- `arm_target`
- `disarm_target`
- `pause`
- `resume`
- `stop`

The target starts disarmed, and `start_demo` cannot arm it implicitly. The local
Spatial panel must invoke `arm_target` first. No WebView, Tauri shell, raw input
injection, or arbitrary native-command surface owns or bypasses the immersive
Activity.

The same Rust authority now owns a canonical BRSP/1 target behind five relay
JNI seam methods: `create_pairing`, `begin_relay`, `handle_relay_frame`,
`poll_relay`, and `end_relay`. Kotlin/OkHttp 4.12 owns only the explicit
WebSocket lifecycle, relay metadata, bounded queuing, and panel refresh. It
does not authenticate, interpret, or dispatch application commands.

`BRSP_REMOTE_ENABLED=true`, but networking is still opt-in at runtime. The
Quest operator must generate a fresh local invitation and press **Connect**;
there is no auto-connect, background authority, deep link, or secret-bearing
WebSocket URL. Each controller peer must complete a new canonical mutual
hello/proof/ready exchange before it owns a five-second target lease.

## Verified upstream pin

The scaffold pins the official Meta Spatial SDK Starter Sample toolchain as
observed on 2026-08-30:

| Component | Pin |
| --- | --- |
| Meta Spatial SDK | `0.13.2` |
| Official sample commit | `a46c632cb94eadce0a521dfefca458e3968b2780` |
| Android Gradle Plugin | `8.11.1` |
| Kotlin | `2.2.0` |
| Gradle | `9.4.1` |
| JDK | `17` |
| Android compile/min/target SDK | `34` |
| Android NDK | `27.0.12077973` |
| Horizon OS manifest min/target | `69` |

Primary sources:

- [Meta Spatial SDK Samples](https://github.com/meta-quest/Meta-Spatial-SDK-Samples/tree/a46c632cb94eadce0a521dfefca458e3968b2780/StarterSample)
- [Meta Spatial SDK 0.13.2 release notes](https://developers.meta.com/horizon/downloads/package/meta-spatial-sdk/0.13.2/)
- [Meta Spatial SDK 0.13.2 plugin documentation](https://developers.meta.com/horizon/documentation/spatial-sdk/spatial-sdk-editor/)
- [Official Starter Sample documentation](https://developers.meta.com/horizon/documentation/spatial-sdk/spatial-sdk-sample-starter/)

The panel is created programmatically, so this preview does not require a
Spatial Editor scene export. The official Spatial Gradle plugin remains pinned
and usage-data collection is disabled in this project.

The sample repository's README and version catalogue still show Kotlin 2.1.0
at the pinned commit, but Meta's newer 0.13.2 release notes explicitly require
Kotlin 2.2. The resolved 0.13.2 Gradle plugin also imports the Kotlin 2.2 BOM;
using 2.1.0 produces a compiler classpath `NoSuchMethodError`, so this scaffold
uses the release-note pin.

## Prerequisites

Install or configure all of the following before an APK build:

1. Android Studio Narwhal 2025.1.1 or newer, or an equivalent command-line
   Android toolchain.
2. JDK 17.
3. Android SDK Platform 34 and matching platform tools.
4. Android NDK `27.0.12077973`.
5. Stable Rust with the Android AArch64 target:

   ```text
   rustup target add aarch64-linux-android
   ```

6. `JAVA_HOME` and `ANDROID_SDK_ROOT` (or `ANDROID_HOME`). Set
   `ANDROID_NDK_HOME`/`ANDROID_NDK_ROOT` when the NDK is not under
   `<sdk>/ndk/27.0.12077973`. `-PppsNdkDir=<absolute-path>` is also accepted.

The official Meta sample lists Windows and macOS as its supported development
hosts. This project has not qualified Linux-hosted Spatial SDK builds.

## Build and test

From this directory on Windows:

```powershell
.\gradlew.bat testDebugUnitTest
.\gradlew.bat assembleDebug
```

On macOS/Linux:

```sh
./gradlew testDebugUnitTest
./gradlew assembleDebug
```

`assembleDebug` automatically builds
`native/pps-quest-core` for `aarch64-linux-android` and packages only
`arm64-v8a`. The APK is written under `app/build/outputs/apk/debug/`.
Gradle's configuration cache is disabled because the native task resolves a
host-specific Cargo executable and NDK clang linker at execution time.

For Kotlin-only UI work, `-PskipRustBuild=true` skips the native build. Debug
builds then use an explicit in-memory Kotlin runner fallback and disable the
remote controls when `libpps_quest_core.so` is absent; the Kotlin layer never
pretends to replace the Rust BRSP authority. Release builds fail closed in an
`error` state when the library is absent.

To substitute a future shared Rust crate, pass
`-PppsRustCoreDir=<path-to-crate>`. It must produce a `cdylib` named
`libpps_quest_core.so` and export the JNI symbols declared by
`JniRunnerCore.kt` and `JniBrspTarget.kt`.

### Current host qualification

The canonical relay slice was qualified on the Windows host with:

```powershell
cargo test -p pps-quest-core
cargo clippy -p pps-quest-core --all-targets -- -D warnings
.\gradlew.bat testDebugUnitTest assembleDebug assembleRelease lint
```

That pass covered 18 Quest-adapter Rust tests, 9 shared-core Rust tests, and 23
JVM tests, including an identical shared
BRSP proof fixture, mutual handshake, scope/privacy enforcement, stale
revision, replay/dedupe, local-only operations, malformed/oversize frames,
lease expiry, missing JNI, Activity pause, peer loss, and reconnect. Android
lint completed with zero errors; the remaining warnings are the intentionally
pinned vendor/toolchain versions, Quest-only ARM64 profile, and debug-only
cleartext lab policy. Both APK variants contain only `arm64-v8a`, package
`libpps_quest_core.so`, and retain all 12 JNI exports. This is host/artifact
qualification only, not an in-headset or timing result.

## Security defaults

- Release cleartext traffic is disabled both in the manifest and network
  security configuration, and its endpoint policy accepts only `wss://`.
- Debug has an explicit source-set-only cleartext network configuration for an
  operator-entered laboratory `ws://` relay. There is no auto-connect and the
  release manifest does not inherit this exception.
- The app requests only `INTERNET` and `ACCESS_NETWORK_STATE`.
- It requests no camera, microphone, storage, location, vibration, hand
  tracking, or all-files permission.
- The only user-authored exported component is the Spatial SDK Activity, and
  there is no deep link or externally callable command endpoint. Spatial SDK
  and AndroidX may merge their own internal service/provider/profile-installer
  components; inspect the merged release manifest whenever dependencies move.
- The local Rust snapshot parser is strict and bounded to 8 KiB. Relay control
  frames are bounded to 16 KiB, state frames to 8 KiB, native JNI results to
  four outbound frames, and OkHttp's reliable queue to 256 KiB. State is
  coalesced newest-only before it enters OkHttp while control stays ordered and
  reliable. Binary frames are rejected.
- Rust generates and validates the exact 32-byte unpadded-base64url pairing
  secret. The invitation keeps it after `#`; it is never placed in the relay
  path or query.
- Rust performs the canonical role-bound HMAC proof over the complete target
  and controller hello envelopes, exact scope/capability negotiation, uint32
  per-lane sequencing, sender epoch checks, expected-revision CAS, and a
  pairing-generation-scoped 128-entry command-ID dedupe cache before dispatching through
  `RunnerCore::dispatch(DispatchOrigin::Remote { ... })`.
- `session.read` gates every snapshot and state publication. A 250 ms state
  heartbeat is separate from the reliable control lane.
- The locally generated invitation explicitly offers `session.read`,
  `session.prepare`, `session.transport`, `session.annotate`, and
  `session.abort`. The Quest adapter exposes only `system.snapshot`,
  `package.prepare_demo`, `setup.submit`, `part.start`, `run.pause`,
  `run.resume`, `run.stop`, and `session.note`. `session.abort` exists only
  because `run.stop` requires that scope; `run.abort` is not exposed.
- `target.arm`, `target.disarm`, and `run.complete_demo` remain target-local.
  Remote start and resume still require the separate local arm gate.
- The authenticated controller lease expires after five seconds without a
  fresh valid control. Expiry, peer loss, socket failure, Activity pause, or a
  local disconnect revokes ownership and pauses a running task; it does not
  abort or disarm it. Reconnect always starts a fresh handshake.
- The panel starts with a cryptographically random 96-bit relay room suffix,
  and pairing rotation requires another fresh room. This prevents an abandoned
  unauthenticated relay role slot from blocking a newly paired controller.

## Laboratory relay workflow

1. Start the desktop PPS runner's LAN relay and companion page on the same
   trusted Wi-Fi network.
2. In a debug Quest build, enter `ws://<desktop-lan-ip>:<port>` and keep the
   generated random room ID (or explicitly replace it with another 8-64
   character value). Release builds require a trusted
   `wss://<relay-origin>` instead.
3. Press **Generate invite**, then **Connect** on Quest. Open the generated
   `http(s)://.../companion/#...` invitation in the phone/laptop browser.
4. Arm the target from the Quest panel before requesting a remote start.

The relay forwards canonical text envelopes and owns no experiment authority.
The Rust reducer on Quest remains authoritative for state, revisions, safety,
and acknowledgements.

## Deliberate limitations

This is a buildable architecture preview, not an experiment-ready application.
It does **not** yet include:

- a bundled trusted production WSS relay, VDO.Ninja/WebRTC transport, or LAN
  discovery;
- experiment package ingestion, asset verification, audio playback, Quest
  controller haptics, participant responses, logging, LSL, or export;
- automatic/background reconnect (reconnect is deliberately local and starts
  a new proof exchange);
- a release signing/distribution pipeline;
- headset installation, physical-device browser interoperability, or Wi-Fi
  partition qualification;
- physical audio, display, controller, tactile, or network timing validation.

No scientific timing or remote-control reliability claim should be made from
this scaffold. The canonical proof/replay/scope/privacy/lease paths have host
Rust and JVM fixture coverage and both APK variants build, but the next
qualification step is a physical Quest plus phone-browser smoke test using a
controlled Wi-Fi partition. Only after that should experiment media timing or
remote reliability be characterized.
