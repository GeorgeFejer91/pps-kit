# Module Map

This is the compact navigation map for future agents. Read it after `For-AI/README.md` and before structural edits.

## Current Ownership

- Dashboard backend and Segment 0-6 materialization: `src/peripersonal_space_toolkit/dashboard_app.py`.
- Dashboard backend helper seams: `src/peripersonal_space_toolkit/dashboard_backend/`.
- Browser dashboard/static GitHub Pages surface: `src/peripersonal_space_toolkit/dashboard/`, root `index.html`, `.nojekyll`, `CNAME`.
- Loudness policy, SPL estimate metadata, dB/RMS helpers, final-active-window calibration rules, and standalone loudness-manifest helpers: `src/peripersonal_space_toolkit/loudness.py`.
- Shared stored-profile catalogue, runner memory, acquisition bridge, and output diary helpers: `profile_memory.py`.
- Runtime package preparation and participant playback: `session_runner.py`, `focus_app.py`, `focus_launch.py`, with runner-owned LabRecorder RCS subprocess capture isolated in `labrecorder_capture.py`.
- Focus Mode phone companion: `runner_companion.py` owns the FastAPI/WebSocket token-gated LAN service, HTTP-safe bridge-error handling, QR payload helpers, and token-gated setup/start/pause/resume/continue routes; `focus_app.py` owns the Qt-thread bridge, snapshot/command state, separate mutually exclusive Pause/Resume controls, hidden internal close/stop cleanup, and post-run timer responsiveness while the service is active; `android/runner-companion/` owns the native Kotlin/Compose phone app and its landscape runner-confirmed cue/click timeline visualization.
- Provisional Woojer tactile-drive latency compensation: `tactile_latency.py`, consumed by `session_runner.py` during participant/top-up block WAV preparation.
- Shared runner/dashboard profile memory and output-diary bridge: `runner_diary.py` now owns runner settings and diary helpers; future shared profile-catalogue code should live in a common Python seam consumed by both `dashboard_app.py` and `focus_app.py`, not separately in browser JS or runner UI code.
- Event, timing, and output evidence contracts: `timing_events.py`, `session_events.py`, `output_evidence.py`, `topup.py`.
- Optional LSL sender/receiver command acknowledgement helpers: `lsl_command_ack.py`, with real `pylsl` round-trip validation in `validation_protocols/scripts/run_lsl_command_ack_roundtrip.py`.
- Left-monitor companion emulator window placement: `windows/Set_Companion_Emulation_Layout.ps1` pins the packaged runner and Android emulator to the designated validation display without using mouse control; `focus_app.py` also honors `PPS_FOCUS_VALIDATION_DISPLAY`, `PPS_FOCUS_VALIDATION_RUNNER_WIDTH`, and `PPS_FOCUS_VALIDATION_WINDOW_RECT` so windowed runner validation opens directly on that display.
- Published-study preload recreation gate: `profile_recreation.py`, `assets/preloads/`, `study_templates/`.
- Core paper-audit read API: `peripersonal_space_toolkit.paper_audit`.
- Paper-audit acquisition/refresh tools: `tools/paper_metadata_parser/`.
- Tracked paper-audit memory and ledgers: `For-AI/audiotactile-paper-metadata-audit/`.
- Validation protocols and lab evidence scripts: `validation_protocols/`.

## Refactor Direction

Keep public imports stable while extracting:

- `dashboard_app.py` remains the compatibility facade for `create_app`, `DashboardController`, and `pps-dashboard`.
- Segment manifest validation should move from the backend monolith into manifest/segment modules.
- Runtime launch/session package work should move toward `runtime/` modules.
- Event and marker schemas should move toward `events/` modules.
- Browser JS should split only after backend/API seams are stable, and local packaged plus hosted/static assets must stay synchronized.

## Literature/Paper Audit Rule

The paper audit is a core pipeline, not a side report. It catalogs the needs, profiles, parameters, missing publication details, and toolkit-structure gaps across audio-tactile PPS studies so future implementations can be built from a growing knowledge base. Keep tracked audit files source-pointer-only; keep PDFs, supplements, extracted full text, screenshots, and local bundles ignored.
