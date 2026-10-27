# Designer native preparation host

This local preview uses the canonical Designer HTML and the existing planner.
Rust owns file-picker authority, verified portable-profile import, saved drafts,
one bounded generation job and publication. Generation uses `pps-designer-core`
and the existing C++ 3DTI executable. No Python runtime or HTTP fallback is used.

The identifier `org.peripersonalspace.designer.preview` is a **proposed preview
identity**. Bundling is disabled. Signing, installation and distribution require
the final identity and a separately verified renderer/resource package.

## Connected scope

- Offline bundled templates and premade audio; native-picked WAVs; verified
  `.pps-profile` import, portable export and ingredient WAV export through
  native save dialogs. Stationary controls travel as separate bundle assets.
- Explicit native source algorithm opt-in and seed, existing endpoint/polar
  trajectory semantics, and supported loudness policies from the Rust core.
- Revision changes cancel work. The host kills/reaps renderer processes on
  cancellation/timeout; a Windows job object terminates children when its
  lifetime closes. Staging never becomes an available asset before the current
  revision and cancellation fence passes. Later plans are invalidated on commit.
- Frontend references are `native-assets/<digest>.wav` receipts. Neither a saved
  arbitrary path nor a spatialized bundle asset grants dry-source authority.
- Output qualification remains unmeasured. Existing level ceilings and
  calibration validation remain in the core.

The native review action reuses the existing source-block planner, verifies
actual audio/tactile samples and enriches timing, then retains the core's sealed
block and complete participant-order receipts. The UI pages every occurrence
and requires explicit review acceptance. Saved browser flags cannot recreate
this authority; edits and restart require a new native review.

Preparation selects a native output folder, claims one new child directory and
writes the selected participant's immutable parts there. The host verifies the
single package or complete group before exposing an Open folder action. Split
participants hand off `session_group_manifest.json`; paths are never rebased.
Cancellation removes only the job-owned candidate. Prepared files are not
execution or physical qualification evidence. Hosted Segment 6 remains a
descriptive summary.

Stationary controls use the core's explicit V2 opt-in and saved source geometry,
timing and loudness policy. They preserve moving audio and invalidate later
review. Source form collection retains their independent hash/provenance; the
portable exporter never replaces the moving source's browser asset identity.

## Local verification

The coordinator owns the root workspace member and lockfile. Rebuild the
canonical frontend first, then `cargo build -p pps-experiment-designer`.
For debug-only testing, `PPS_DESIGNER_RENDERER` selects the rebuilt native
renderer (with its DLLs). Release builds accept only the packaged renderer.

`cargo test -p pps-experiment-designer --lib` checks owner fencing, path authority
and actual child cancellation. The ignored `actual_renderer` test requires the
renderer and verifies real generated WAV publication plus obsolete-work discard.
The ignored `actual_study5` test uses the retained native fixture selected by
`PPS_STUDY5_FIXTURE` plus the real browser full-plan capture. It verifies 600
reviewed occurrences, two actual participant parts, forged acceptance rejection,
revision cancellation and restart without restored acceptance authority.

`PPS_DESIGNER_TEST_DATA` is a debug-only isolated data directory; it keeps the
window hidden and captures the exact test generation request there. For a
rendered check, launch that debug process with a loopback WebView2 debugging
port and muted audio, then run `frontend/tests/verify-native-webview.mjs` with
`PPS_PLAYWRIGHT_MODULE` and `PPS_DESIGNER_TEST_CDP`. These environment overrides
are unavailable in release behavior. Screenshots/reports belong in ignored
`artifacts/`. Stop the test process afterward.
`verify-native-assembly.mjs` uses an isolated fixture draft with the real Study 5
assets to check a missing comparator, actual control generation, the complete
204-trial/600-occurrence review, explicit acceptance and edit invalidation.
