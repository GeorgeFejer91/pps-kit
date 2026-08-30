# Cross-platform Runner and Remote Preview — 2026-08-30

## Status

This change establishes an incremental, software-qualified candidate Runner:

- the primary path is a Tauri v2 desktop shell plus one no-install browser
  frontend that can act as a controller or exploratory phone-owned target;
- closed Rust contracts, canonical BRSP/1 primitives, and a pure authoritative
  reducer are shared by native targets;
- `apps/quest-runner/` is an optional experimental Meta Quest application
  context, not the primary PPS Kit Runner and not part of V1 manifests;
- the validated Python/PySide Focus Mode remains the production/scientific
  authority until the remaining scheduler, acquisition, artifact, and analysis
  behavior is ported and physically qualified.

## Automated and host evidence

### Exact Rust minimum toolchain

Using the declared Rust 1.88.0 toolchain and the committed workspace lockfile:

- `cargo fmt --all -- --check`: pass;
- `cargo check --workspace --all-targets --all-features --locked`: pass;
- `cargo clippy --workspace --all-targets --all-features --locked -- -D warnings`:
  pass;
- `cargo test --workspace --all-features --locked`: pass.

Unit-test totals were 4 contracts, 5 BRSP, 9 shared core, 9 Tauri desktop,
and 18 Quest-native tests (45 total), with all doc tests passing. Coverage
includes strict messages, mutual proof, scopes, read privacy, revision/epoch and
unsigned-32-bit sequence rules, wrap to zero, principal-scoped deduplication,
local arming, reconnect, stale-owner fencing, authority invalidation, and
target-owned deadman pause/revoke.

### Browser and Tauri desktop

- clean npm install and `npm run check`: 19/19 Node tests plus deterministic
  Vite 6.4.3 production build;
- `npm audit --audit-level=moderate`: zero reported vulnerabilities;
- the only required dependency install script is explicitly approved for the
  exact resolved `esbuild` version;
- Tauri debug no-bundle build: pass on Windows with Rust 1.88.0;
- launched debug executable owned no attributable listening TCP socket before
  explicit remote activation;
- an earlier headed browser/UI pass exercised prepare, setup, local arm, demo
  execution, and completion at phone-sized layout. This is UI/software evidence,
  not physical phone timing evidence.

### Optional Quest application context

The enabled canonical Quest BRSP target passed:

- `testDebugUnitTest`: 23/23 JVM tests;
- debug and unsigned release APK assembly;
- Android lint with zero errors (14 documented toolchain/vendor/profile or
  debug-cleartext advisories);
- release APK inspection: ARM64 only, `libpps_quest_core.so` present, 12 JNI
  exports, release cleartext disabled, and only Internet/network-state plus the
  AndroidX internal non-exported dynamic-receiver permission;
- the Rust-build bypass was separately exercised with a seeded prior library
  to prove a stale `.so` is not packaged.

Final ignored artifacts from this source state:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| debug APK | 88,117,023 | `491B93982534B186F61826CD7D6DC5A493C180D1C84D6FF559DDB1A09789423F` |
| unsigned release APK | 63,493,580 | `4971AFF012BFA211DF2D8786C9129DA27EC4B21100CC4E7A097605068E05570C` |

### Existing repository gates

- Quick repository gate: 30/30 tests, 340 tracked JSON files parsed, release and
  privacy audit passed, and Python sources compiled.
- The broader existing Python suite produced 605 passed, 8 skipped, and one
  failure in `test_publication_network_generator_rebuild_is_byte_deterministic`.
  The failure is the known Windows working-copy CRLF versus generator LF byte
  comparison in a publication-network JSON asset; this change does not touch
  that generator or asset. It is recorded rather than silently rewriting the
  publication artifact.

## Unqualified boundaries

This evidence does not establish:

- feature parity with the validated Python/PySide experiment Runner;
- scientific equivalence for audio sample clocks, ASIO/CoreAudio/Linux audio,
  physical tactile onset, response markers, LSL/XDF, LabRecorder, calibration,
  top-up, artifact writers, or numerical analysis;
- a physical Quest install, Quest-to-phone same-Wi-Fi round trip, headset
  lifecycle/partition behavior, controller interaction, haptics, audio/display
  timing, or network timing;
- a production WSS relay, VDO.Ninja adapter, offline-LAN discovery, signed Quest
  release, desktop installers/updater, or signed/notarized macOS/Linux builds;
- host-native runtime behavior on macOS or Linux before the new CI matrix runs.

The release decision remains incremental: preserve V1 while replacing bounded
Python seams with golden/differential evidence, then qualify each native
platform and physical output route before promotion.
