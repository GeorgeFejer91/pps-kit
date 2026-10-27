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
  `.pps-profile` import and portable export through native save dialogs.
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

Participant assembly and immutable run-order acceptance are a subsequent
connection to the core's sealed preview APIs. Hosted Segment 6 remains a
descriptive summary. This checkpoint does not qualify a complete native run.

## Local verification

The coordinator owns the root workspace member and lockfile. Rebuild the
canonical frontend first, then `cargo build -p pps-experiment-designer`.
For debug-only testing, `PPS_DESIGNER_RENDERER` selects the rebuilt native
renderer (with its DLLs). Release builds accept only the packaged renderer.

`cargo test -p pps-experiment-designer --lib` checks owner fencing, path authority
and actual child cancellation. The ignored `actual_renderer` test requires the
renderer and verifies real generated WAV publication plus obsolete-work discard.

`PPS_DESIGNER_TEST_DATA` is a debug-only isolated data directory; it keeps the
window hidden and captures the exact test generation request there. For a
rendered check, launch that debug process with a loopback WebView2 debugging
port and muted audio, then run `frontend/tests/verify-native-webview.mjs` with
`PPS_PLAYWRIGHT_MODULE` and `PPS_DESIGNER_TEST_CDP`. These environment overrides
are unavailable in release behavior. Screenshots/reports belong in ignored
`artifacts/`. Stop the test process afterward.
